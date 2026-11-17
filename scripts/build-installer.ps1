# Builds the Windows installer (NSIS, per-user, no admin rights needed).
#
# Stages what the installed app needs next to its executable into build\bundle:
#   sidecar\  the Python sidecar without tests and evaluations
#   packs\    the bundled phrase packs
#   python\   the official embeddable Python (the sidecar core needs only the standard library)
# and then runs `tauri build` with src-tauri\tauri.bundle.conf.json on top of the normal config.
# ChromaDB is not bundled; the phrase search then falls back to plain text matching.
#
# Result: src-tauri\target\release\bundle\nsis\AI Translate_<version>_x64-setup.exe

param(
    [string]$PythonVersion = "3.12.10",
    [string]$PythonSha256 = "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $root "build\bundle"
$cache = Join-Path $root "build\cache"

function Need($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { throw "Need `"$name`" on PATH." }
}
Need node
Need cargo
if (Get-Process ai-translate -ErrorAction SilentlyContinue) {
    throw "AI Translate is running; close it first (the build replaces its executable)."
}

Write-Host "Staging into $stage"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage, $cache | Out-Null

# Sidecar without tests, evaluations and caches
$sidecarTarget = Join-Path $stage "sidecar"
New-Item -ItemType Directory -Force $sidecarTarget | Out-Null
Get-ChildItem (Join-Path $root "sidecar") -Filter *.py -File | Copy-Item -Destination $sidecarTarget
Copy-Item -Recurse (Join-Path $root "packs") (Join-Path $stage "packs")

# Embeddable Python
$zipName = "python-$PythonVersion-embed-amd64.zip"
$zip = Join-Path $cache $zipName
if (-not (Test-Path $zip)) {
    Write-Host "Downloading $zipName"
    & "$env:SystemRoot\System32\curl.exe" --fail --location --silent --show-error --proto =https `
        --output $zip "https://www.python.org/ftp/python/$PythonVersion/$zipName"
    if ($LASTEXITCODE -ne 0) { throw "Download of $zipName failed." }
}
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
Write-Host "$zipName sha256 $hash"
if ($PythonSha256 -and $hash -ne $PythonSha256.ToLower()) { throw "Checksum of $zipName does not match." }

$pythonTarget = Join-Path $stage "python"
Expand-Archive -Path $zip -DestinationPath $pythonTarget
# The embeddable Python runs isolated: only the paths in the ._pth file are searched.
# The sidecar imports its sibling modules, so its folder must be listed.
$pth = Get-ChildItem $pythonTarget -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) { throw "No ._pth file in the embeddable Python." }
$lines = Get-Content $pth.FullName | Where-Object { $_ -notmatch '^\s*#?\s*import site' }
$lines += "..\sidecar"
Set-Content -Path $pth.FullName -Value $lines -Encoding ascii

# Quick check that the staged sidecar starts with the staged Python
$probe = '{"cmd":"shutdown"}' | & (Join-Path $pythonTarget "python.exe") -X utf8 (Join-Path $sidecarTarget "main.py") `
    --app-dir $stage --config (Join-Path $cache "probe-config.json")
if ($LASTEXITCODE -ne 0) { throw "The staged sidecar did not start." }
Write-Host "Staged sidecar starts: $(@($probe).Count) line(s) of output"

Push-Location $root
try {
    npx tauri build --config src-tauri/tauri.bundle.conf.json
    if ($LASTEXITCODE -ne 0) { throw "tauri build failed." }
} finally {
    Pop-Location
}
Get-ChildItem (Join-Path $root "src-tauri\target\release\bundle\nsis") -Filter *.exe |
    ForEach-Object { "{0}  {1:N1} MB  sha256 {2}" -f $_.FullName, ($_.Length / 1MB), (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower() }
