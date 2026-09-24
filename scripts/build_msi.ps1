param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Version = & $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$ToolPath = Join-Path $ProjectRoot "build/wix"
if (-not (Test-Path "$ToolPath/wix.exe")) {
    dotnet tool install wix --version 6.0.2 --tool-path $ToolPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& "$ToolPath/wix.exe" build packaging/windows/gesaula.wxs `
    -arch x64 -d "Version=$Version" -o "dist/windows/gesaula_${Version}_x64.msi"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Instalador creado en dist/windows/gesaula_${Version}_x64.msi"
