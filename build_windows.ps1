param(
    [string]$Python = (Join-Path $PSScriptRoot '.venv\Scripts\python.exe')
)

$ErrorActionPreference = 'Stop'
try {
    if ($env:OS -ne 'Windows_NT') { throw 'Build this application on Windows 10/11.' }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw 'Python environment not found. Create .venv, then install requirements-build.txt.'
    }
    $Python = (Resolve-Path -LiteralPath $Python).Path
    & $Python -c "import sys, struct; assert sys.version_info >= (3,11), 'Python 3.11+ required'; assert struct.calcsize('P') == 8, 'Use 64-bit Python'; import PySide6, openai, PyInstaller; print('Building with Python', sys.version.split()[0], '/ PyInstaller', PyInstaller.__version__)"
    if ($LASTEXITCODE -ne 0) { throw 'Install dependencies with: .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt' }
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'The Python environment has conflicting dependencies.' }
    & $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $PSScriptRoot 'dist') --workpath (Join-Path $PSScriptRoot 'build') (Join-Path $PSScriptRoot 'ChibiMate.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed. See the build output above.' }
    $executable = Join-Path $PSScriptRoot 'dist\ChibiMate\ChibiMate.exe'
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw 'Build finished without producing ChibiMate.exe.' }
    Write-Host "Build complete: $executable"
    Write-Host 'Distribute the entire dist\ChibiMate folder, including _internal.'
    exit 0
}
catch {
    [Console]::Error.WriteLine("ChibiMate build failed: $($_.Exception.Message)")
    exit 1
}
