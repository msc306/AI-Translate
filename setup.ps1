# Sets up Turing Translate for development on Windows.
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File setup.ps1
# Add -NoMemory to skip ChromaDB (the semantic phrase search).
param([switch]$NoMemory)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Need($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host "Fehlt: $name. $hint" -ForegroundColor Red
        exit 1
    }
}

Need "node"  "Installieren: https://nodejs.org"
Need "cargo" "Installieren: https://rustup.rs"
Need "uv"    "Installieren: https://docs.astral.sh/uv/"

Write-Host "1/3 Python-Umgebung (.venv) ..."
if (-not (Test-Path ".venv\Scripts\python.exe")) { uv venv --python 3.12 .venv }
if (-not $NoMemory) { uv pip install --python .venv\Scripts\python.exe -r requirements-optional.txt }

Write-Host "2/3 Node-Pakete ..."
npm install

Write-Host "3/3 Modelle ..."
New-Item -ItemType Directory -Force models | Out-Null
$found = @(Get-ChildItem models -Filter *.gguf -ErrorAction SilentlyContinue)
if ($found.Count -eq 0) {
    Write-Host "Noch kein lokales Modell in .\models. GGUF-Dateien dort ablegen oder spaeter in den" -ForegroundColor Yellow
    Write-Host "Einstellungen ueber 'Durchsuchen' waehlen. Modelle aus LM Studio werden automatisch gefunden." -ForegroundColor Yellow
}
if (-not (Get-Command "nvidia-smi" -ErrorAction SilentlyContinue)) {
    Write-Host "Hinweis: nvidia-smi nicht gefunden. Lokale Modelle brauchen eine NVIDIA-Grafikkarte;" -ForegroundColor Yellow
    Write-Host "die Anbieter im Internet funktionieren auch ohne." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Fertig. Starten mit:  npm run dev" -ForegroundColor Green
