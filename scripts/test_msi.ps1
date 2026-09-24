$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Packages = @(Get-ChildItem "dist/windows/*.msi")
if ($Packages.Count -ne 1) { throw "Se esperaba un único instalador MSI." }
$Package = $Packages[0].FullName
$InstalledExe = Join-Path $env:ProgramFiles "gesaula/gesaula.exe"

try {
    $Process = Start-Process msiexec.exe -ArgumentList @(
        "/i", "`"$Package`"", "/qn", "/norestart", "/L*v", "build/msi-install.log"
    ) -Wait -PassThru
    if ($Process.ExitCode -notin @(0, 3010)) {
        Get-Content "build/msi-install.log" -Tail 80
        throw "Falló la instalación: $($Process.ExitCode)"
    }
    if (-not (Test-Path $InstalledExe)) { throw "No se instaló gesaula.exe." }
    if ((Get-FileHash $InstalledExe).Hash -ne (Get-FileHash "dist/windows/gesaula.exe").Hash) {
        throw "El ejecutable instalado no coincide con el generado."
    }
} finally {
    $Process = Start-Process msiexec.exe -ArgumentList @(
        "/x", "`"$Package`"", "/qn", "/norestart", "/L*v", "build/msi-uninstall.log"
    ) -Wait -PassThru
    if ($Process.ExitCode -notin @(0, 3010)) {
        Get-Content "build/msi-uninstall.log" -Tail 80
        throw "Falló la desinstalación: $($Process.ExitCode)"
    }
}
if (Test-Path $InstalledExe) { throw "No se eliminó el ejecutable instalado." }
