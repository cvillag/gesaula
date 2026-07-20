param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m pip install . nuitka zstandard pillow
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

New-Item -ItemType Directory -Force -Path "build" | Out-Null
New-Item -ItemType Directory -Force -Path "dist\windows" | Out-Null

& $Python -c "from PIL import Image; Image.open('src/gesaula/icons/logo512.png').save('build/gesaula.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python -m nuitka `
    src/gesaula/main.py `
    --mode=onefile `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --windows-icon-from-ico=build/gesaula.ico `
    --include-data-dir=src/gesaula/icons=gesaula/icons `
    --noinclude-qt-translations `
    --output-dir=dist/windows `
    --output-filename=gesaula.exe `
    --assume-yes-for-downloads

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Ejecutable creado en dist/windows/gesaula.exe"
