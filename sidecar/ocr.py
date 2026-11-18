"""Reads text from an image with the OCR engine that ships with the operating system.

Windows: the engine (Windows.Media.Ocr) is only reachable through WinRT, so a short PowerShell
script does the call. macOS: Apple's Vision framework, called from a JavaScript for Automation
script through `osascript` and its Objective-C bridge. Both keep the sidecar on the standard
library. The image comes from a file or straight from the clipboard, which is where a screenshot lands.
"""
import base64
import json
import os
import re
import statistics
import subprocess
import tempfile
from pathlib import Path

import platform_info
from i18n import tr

NO_WINDOW = platform_info.no_window_flag()  # CREATE_NO_WINDOW on Windows, 0 elsewhere
OSASCRIPT = "/usr/bin/osascript"
TIMEOUT_SECONDS = 40

# German source texts; OcrError translates them when it is raised.
MESSAGES = {
    "unsupported": "Die Texterkennung aus Bildern gibt es nur unter Windows und macOS.",
    "no_image": "In der Zwischenablage liegt weder Text noch ein Bild.",
    "no_file": "Die Bilddatei wurde nicht gefunden.",
    "no_language": "In Windows ist keine Sprache für die Texterkennung installiert "
                   "(Einstellungen → Zeit und Sprache → Sprache → Optionale Sprachfeatures).",
    "empty": "Im Bild wurde kein Text erkannt.",
    "failed": "Die Texterkennung ist fehlgeschlagen.",
}


class OcrError(Exception):
    def __init__(self, code: str, detail: str = ""):
        message = tr(MESSAGES.get(code, MESSAGES["failed"]))
        super().__init__(f"{message} ({detail})" if detail and code == "failed" else message)
        self.code = code


# Parameters arrive in environment variables; the answer leaves as base64 so that no console
# code page can damage it.
SCRIPT = r"""
$ErrorActionPreference = 'Stop'
function Reply($obj) {
  $json = $obj | ConvertTo-Json -Depth 5 -Compress
  [Console]::Out.Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))
}
try {
  $path = $env:TT_OCR_PATH
  if ($env:TT_OCR_CLIPBOARD -eq '1') {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $image = [System.Windows.Forms.Clipboard]::GetImage()
    if ($image) {
      $image.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
      $image.Dispose()
    } else {
      $hit = $null
      foreach ($file in [System.Windows.Forms.Clipboard]::GetFileDropList()) {
        if ($file -match '\.(png|jpe?g|bmp|gif|tiff?)$') { $hit = $file; break }
      }
      if (-not $hit) { Reply @{ error = 'no_image' }; exit 0 }
      $path = $hit
    }
  }
  if (-not (Test-Path -LiteralPath $path)) { Reply @{ error = 'no_file' }; exit 0 }

  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
  $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
  $null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
  $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
  $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime]
  $null = [Windows.Graphics.Imaging.BitmapTransform, Windows.Graphics, ContentType = WindowsRuntime]
  $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
  function Await($operation, $type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($operation))
    $null = $task.Wait(-1)
    $task.Result
  }

  $available = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages)
  $engine = $null
  $matched = $false
  if ($env:TT_OCR_LANG) {
    $want = $env:TT_OCR_LANG.ToLower()
    $language = $available | Where-Object {
      $tag = $_.LanguageTag.ToLower(); $tag -eq $want -or $tag.StartsWith($want + '-') } | Select-Object -First 1
    if ($language) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language); $matched = $true }
  }
  if (-not $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
  if (-not $engine -and $available.Count) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($available[0]) }
  if (-not $engine) { Reply @{ error = 'no_language' }; exit 0 }

  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync((Resolve-Path -LiteralPath $path).ProviderPath)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])

  # Screen text is small for the recogniser: enlarge small images, shrink oversized ones.
  $limit = [double][Windows.Media.Ocr.OcrEngine]::MaxImageDimension
  $longest = [double][Math]::Max($decoder.PixelWidth, $decoder.PixelHeight)
  $scale = 1.0
  if ($longest -gt $limit) { $scale = $limit / $longest }
  elseif ($longest -lt 2600) { $scale = [Math]::Min(2.0, $limit / $longest) }
  $transform = New-Object Windows.Graphics.Imaging.BitmapTransform
  $transform.ScaledWidth = [uint32][Math]::Max(1, [Math]::Floor($decoder.PixelWidth * $scale))
  $transform.ScaledHeight = [uint32][Math]::Max(1, [Math]::Floor($decoder.PixelHeight * $scale))
  $transform.InterpolationMode = [Windows.Graphics.Imaging.BitmapInterpolationMode]::Fant
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync(
      [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
      [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied,
      $transform,
      [Windows.Graphics.Imaging.ExifOrientationMode]::RespectExifOrientation,
      [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $stream.Dispose()

  $lines = @()
  foreach ($line in $result.Lines) {
    $left = [double]::MaxValue; $top = [double]::MaxValue; $right = 0.0; $bottom = 0.0
    foreach ($word in $line.Words) {
      $box = $word.BoundingRect
      $left = [Math]::Min($left, $box.X); $top = [Math]::Min($top, $box.Y)
      $right = [Math]::Max($right, $box.X + $box.Width); $bottom = [Math]::Max($bottom, $box.Y + $box.Height)
    }
    $lines += @{ text = $line.Text; x = [int]$left; y = [int]$top; w = [int]($right - $left); h = [int]($bottom - $top) }
  }
  Reply @{ lines = $lines; lang = $engine.RecognizerLanguage.LanguageTag; matched = $matched
           available = @($available | ForEach-Object { $_.LanguageTag }) }
} catch {
  Reply @{ error = 'failed'; detail = $_.Exception.Message }
}
"""

# macOS: Vision through the JavaScript for Automation bridge. Same contract as SCRIPT: parameters in
# TT_OCR_* environment variables, the answer as base64 JSON. Boxes stay in Vision's normalized,
# bottom-left based coordinates together with the pixel size; Python converts them (vision_box).
# Numeric values instead of enum names, since Vision ships no BridgeSupport file:
# recognitionLevel 0 = accurate.
MAC_SCRIPT = r"""
ObjC.import('Foundation');
ObjC.import('AppKit');
ObjC.import('Vision');

function reply(obj) {
  var text = $.NSString.alloc.initWithUTF8String(JSON.stringify(obj));
  return text.dataUsingEncoding($.NSUTF8StringEncoding).base64EncodedStringWithOptions(0).js;
}

function setting(name) {
  var value = $.NSProcessInfo.processInfo.environment.objectForKey(name);
  return (value.isNil()) ? '' : value.js;
}

function run() {
  try {
    var path = setting('TT_OCR_PATH');
    var data = null;
    if (setting('TT_OCR_CLIPBOARD') === '1') {
      var board = $.NSPasteboard.generalPasteboard;
      data = board.dataForType('public.png');
      if (data.isNil()) { data = board.dataForType('public.tiff'); }
      if (data.isNil()) {
        data = null;
        var url = board.stringForType('public.file-url');
        if (url.isNil()) { return reply({error: 'no_image'}); }
        var file = $.NSURL.URLWithString(url).path.js;
        if (!/\.(png|jpe?g|bmp|gif|tiff?|heic)$/i.test(file)) { return reply({error: 'no_image'}); }
        path = file;
      }
    }
    if (data === null) {
      if (!path || !$.NSFileManager.defaultManager.fileExistsAtPath(path)) { return reply({error: 'no_file'}); }
      data = $.NSData.dataWithContentsOfFile(path);
      if (data.isNil()) { return reply({error: 'no_file'}); }
    }
    var width = 0, height = 0;
    var bitmap = $.NSBitmapImageRep.imageRepWithData(data);
    if (!bitmap.isNil()) { width = bitmap.pixelsWide; height = bitmap.pixelsHigh; }

    var request = $.VNRecognizeTextRequest.alloc.init;
    request.setRecognitionLevel(0);
    request.setUsesLanguageCorrection(true);
    var available = [];
    try {
      var error = Ref();
      var supported = request.supportedRecognitionLanguagesAndReturnError(error);
      if (supported && !supported.isNil()) { available = ObjC.deepUnwrap(supported) || []; }
    } catch (ignored) {}
    var want = setting('TT_OCR_LANG').toLowerCase();
    var used = '', matched = false;
    if (want) {
      for (var i = 0; i < available.length; i++) {
        var tag = String(available[i]).toLowerCase();
        if (tag === want || tag.indexOf(want + '-') === 0) { used = available[i]; break; }
      }
    }
    if (used) {
      request.setRecognitionLanguages($([used]));
      matched = true;
    } else if (request.respondsToSelector('setAutomaticallyDetectsLanguage:')) {
      request.setAutomaticallyDetectsLanguage(true);
    }

    var handler = $.VNImageRequestHandler.alloc.initWithDataOptions(data, $({}));
    var failure = Ref();
    if (!handler.performRequestsError($([request]), failure)) {
      var reason = (failure[0] && !failure[0].isNil()) ? failure[0].localizedDescription.js : 'Vision';
      return reply({error: 'failed', detail: reason});
    }
    var results = request.results;
    var lines = [];
    for (var n = 0; n < results.count; n++) {
      var observation = results.objectAtIndex(n);
      var candidates = observation.topCandidates(1);
      if (candidates.count === 0) { continue; }
      var box = observation.boundingBox;
      lines.push({text: candidates.objectAtIndex(0).string.js, bx: box.origin.x, by: box.origin.y,
                  bw: box.size.width, bh: box.size.height});
    }
    return reply({lines: lines, width: width, height: height, lang: used, matched: matched,
                  available: available});
  } catch (e) {
    return reply({error: 'failed', detail: String(e)});
  }
}
"""

# Size assumed for the image when Vision's boxes arrive without one (only proportions matter then).
_FALLBACK_SIZE = 2000


def vision_box(box: dict, width: int, height: int) -> dict:
    """A Vision bounding box (normalized 0..1, origin bottom left) as pixel box with origin top left.

    `box` has bx, by, bw, bh; the result has x, y, w, h like the Windows recogniser's lines.
    """
    width = int(width) or _FALLBACK_SIZE
    height = int(height) or _FALLBACK_SIZE
    bx, by = float(box.get("bx", 0)), float(box.get("by", 0))
    bw, bh = float(box.get("bw", 0)), float(box.get("bh", 0))
    return {"x": int(round(bx * width)), "y": int(round((1.0 - by - bh) * height)),
            "w": int(round(bw * width)), "h": int(round(bh * height))}


def mac_lines(answer: dict) -> list:
    """The lines of a MAC_SCRIPT answer in the shape layout_text expects."""
    width, height = answer.get("width") or 0, answer.get("height") or 0
    return [{"text": line.get("text", ""), **vision_box(line, width, height)} for line in answer.get("lines") or []]


# Scripts written without spaces between words: the recogniser separates every character.
_CJK = r"぀-ヿ㐀-䶿一-鿿＀-￯　-〿"
_CJK_GAP = re.compile(f"(?<=[{_CJK}]) +(?=[{_CJK}])")


def _join_labels(rows: list) -> list:
    """Put a short fragment ("A.", "Name:", a number) into the line it stands beside.

    The recogniser reports such labels as a column of their own, so they would end up far from
    their text. Two long lines side by side are left alone: those are columns of prose.
    """
    def short(row):
        return row["w"] <= 6 * row["h"]

    def beside(a, b):
        middle = a["y"] + a["h"] / 2
        return b["y"] <= middle <= b["y"] + b["h"] and (b["x"] >= a["x"] + a["w"] or a["x"] >= b["x"] + b["w"])

    def distance(a, b):
        return max(b["x"] - (a["x"] + a["w"]), a["x"] - (b["x"] + b["w"]))

    changed = True
    while changed:
        changed = False
        for label in rows:
            if not short(label):
                continue
            partners = [row for row in rows if row is not label and beside(label, row)]
            if not partners:
                continue
            partner = min(partners, key=lambda row: distance(label, row))
            first, second = (label, partner) if label["x"] < partner["x"] else (partner, label)
            bottom = max(label["y"] + label["h"], partner["y"] + partner["h"])
            right = max(label["x"] + label["w"], partner["x"] + partner["w"])
            partner["text"] = f"{str(first['text']).strip()} {str(second['text']).strip()}"
            partner["x"], partner["y"] = min(label["x"], partner["x"]), min(label["y"], partner["y"])
            partner["w"], partner["h"] = right - partner["x"], bottom - partner["y"]
            rows = [row for row in rows if row is not label]
            changed = True
            break
    return rows


def layout_text(lines: list, lang: str = "") -> str:
    """Join recognised lines into text: wrapped lines flow together, paragraphs and lists stay apart."""
    rows = _join_labels([dict(row) for row in lines if str(row.get("text") or "").strip()])
    if not rows:
        return ""
    cjk = lang.lower().split("-")[0] in ("zh", "ja")
    height = statistics.median(max(1, int(row.get("h") or 1)) for row in rows)

    paragraphs = [[rows[0]]]
    for prev, cur in zip(rows, rows[1:]):
        gap = cur["y"] - (prev["y"] + prev["h"])
        if gap > 0.7 * height or cur["y"] < prev["y"] - height:  # blank space, or a jump to a new column
            paragraphs.append([])
        paragraphs[-1].append(cur)

    blocks = []
    for paragraph in paragraphs:
        left = min(row["x"] for row in paragraph)
        right = max(row["x"] + row["w"] for row in paragraph)
        span = right - left
        prose = span >= 15 * height  # short lines are labels, menu items or list entries
        text = str(paragraph[0]["text"]).strip()
        for prev, cur in zip(paragraph, paragraph[1:]):
            full = prose and prev["x"] + prev["w"] >= right - 0.12 * span
            text += ("" if cjk else " ") if full else "\n"
            text += str(cur["text"]).strip()
        blocks.append(_CJK_GAP.sub("", text) if cjk else text)
    return "\n\n".join(blocks)


def read_image(path: str = "", clipboard: bool = False, lang: str = "") -> dict:
    """Recognise the text of an image file or of the image in the clipboard.

    Returns {"text", "lang", "matched", "available"}; `matched` says whether the requested
    language was installed. Raises OcrError with a message for the user.
    """
    system = platform_info.system()
    if system == "macos":
        return _read_image_mac(path, clipboard, lang)
    if system != "windows":
        raise OcrError("unsupported")
    with tempfile.TemporaryDirectory(prefix="ai-translate-ocr-") as work:
        env = {**os.environ,
               "TT_OCR_PATH": str(Path(work) / "clipboard.png") if clipboard else str(path),
               "TT_OCR_CLIPBOARD": "1" if clipboard else "0",
               "TT_OCR_LANG": "" if lang in ("", "auto") else lang}
        encoded = base64.b64encode(SCRIPT.encode("utf-16-le")).decode("ascii")
        try:
            done = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", encoded],
                stdin=subprocess.DEVNULL, capture_output=True, env=env, timeout=TIMEOUT_SECONDS,
                creationflags=NO_WINDOW)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise OcrError("failed", type(err).__name__)
    try:
        answer = json.loads(base64.b64decode(done.stdout.strip()).decode("utf-8"))
    except ValueError:
        raise OcrError("failed", f"Code {done.returncode}")
    if answer.get("error"):
        raise OcrError(answer["error"], str(answer.get("detail") or ""))
    used = str(answer.get("lang") or "")
    text = layout_text(answer.get("lines") or [], used)
    if not text.strip():
        raise OcrError("empty")
    return {"text": text, "lang": used, "matched": bool(answer.get("matched")),
            "available": list(answer.get("available") or [])}


def _read_image_mac(path: str, clipboard: bool, lang: str) -> dict:
    """macOS: Vision via osascript. `lang` is empty when Vision chose the language itself."""
    env = {**os.environ,
           "TT_OCR_PATH": "" if clipboard else str(path),
           "TT_OCR_CLIPBOARD": "1" if clipboard else "0",
           "TT_OCR_LANG": "" if lang in ("", "auto") else lang}
    try:
        done = subprocess.run([OSASCRIPT, "-l", "JavaScript", "-e", MAC_SCRIPT], stdin=subprocess.DEVNULL,
                              capture_output=True, env=env, timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise OcrError("failed", type(err).__name__)
    try:
        answer = json.loads(base64.b64decode(done.stdout.strip()).decode("utf-8"))
    except ValueError:
        detail = done.stderr.decode("utf-8", "replace").strip().splitlines()
        raise OcrError("failed", detail[-1] if detail else f"Code {done.returncode}")
    if answer.get("error"):
        raise OcrError(answer["error"], str(answer.get("detail") or ""))
    used = str(answer.get("lang") or "")
    text = layout_text(mac_lines(answer), used)
    if not text.strip():
        raise OcrError("empty")
    return {"text": text, "lang": used, "matched": bool(answer.get("matched")),
            "available": list(answer.get("available") or [])}
