param(
    [string]$PythonBin = "python",
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$SpecFile = Join-Path $RepoRoot "BlackHorseSoundDesigner.spec"
$DistDir = Join-Path $RepoRoot "dist"
$OneDir = Join-Path $DistDir "BlackHorseSoundDesigner"
$IssFile = Join-Path $RepoRoot "installer\BlackHorseSoundDesigner.iss"

if (-not (Test-Path $SpecFile)) {
    throw "Spec file not found: $SpecFile"
}

if (-not (Test-Path $IssFile)) {
    throw "Inno Setup script not found: $IssFile"
}

Write-Host "[1/4] Checking PyInstaller..."
& $PythonBin -c "import PyInstaller" | Out-Null

Write-Host "[2/4] Building app with PyInstaller..."
& $PythonBin -m PyInstaller --noconfirm --clean $SpecFile

if (-not (Test-Path $OneDir)) {
    throw "PyInstaller output not found: $OneDir"
}

Write-Host "[3/4] Checking Inno Setup (iscc)..."
$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    throw "Inno Setup compiler (iscc) not found. Install Inno Setup and ensure iscc is in PATH."
}

$version = "0.1.0"
$pyproject = Join-Path $RepoRoot "pyproject.toml"
if (Test-Path $pyproject) {
    $content = Get-Content $pyproject -Raw
    $m = [regex]::Match($content, 'version\s*=\s*"([^"]+)"')
    if ($m.Success) {
        $version = $m.Groups[1].Value
    }
}

Write-Host "[4/4] Building installer EXE..."
& $iscc.Source "/DSourceDir=$OneDir" "/DMyAppVersion=$version" $IssFile

Write-Host "Done."
Write-Host "Installer output directory: $DistDir"
Write-Host "Look for: BlackHorseSoundDesigner-Setup-$version.exe"
