"""Reads text from an image with the OCR engine that ships with Windows.

The engine (Windows.Media.Ocr) is only reachable through WinRT, so a short PowerShell script
does the call. That keeps the sidecar on the standard library. The image comes from a file or
straight from the clipboard, which is where a screenshot lands.
"""
import base64
import json
import os
import re
import statistics
import subprocess
import tempfile
from pathlib import Path

from i18n import tr

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
TIMEOUT_SECONDS = 40

# German source texts; OcrError translates them when it is raised.
MESSAGES = {
    "unsupported": "Die Texterkennung aus Bildern gibt es nur unter Windows.",
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
    if os.name != "nt":
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
