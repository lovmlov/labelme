param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$BuildRoot = $PSScriptRoot
$TaskRoot = Split-Path -Parent $BuildRoot
# Keep the fork's checkout out of Python's import search path. Only the
# installed, pinned v7.9.1 distribution must enter the frozen application.
Set-Location $BuildRoot

function Invoke-Python {
    & python @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed: $args" }
}

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
    throw 'This build must run on Windows x64.'
}
Invoke-Python -c 'import struct,sys; assert sys.platform == "win32"; assert struct.calcsize("P") == 8; assert sys.version_info[:2] == (3,12), sys.version'
if (-not (Test-Path "$TaskRoot\labelme-src\pyproject.toml")) {
    & git clone --depth 1 --branch v7.9.1 https://github.com/wkentaro/labelme.git "$TaskRoot\labelme-src"
    if ($LASTEXITCODE -ne 0) { throw 'Could not clone upstream v7.9.1.' }
}
$ActualCommit = (& git -C "$TaskRoot\labelme-src" rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $ActualCommit -ne 'd179c2353dcf35a29809797b2702dba8d794b84e') {
    throw "Unexpected upstream commit: $ActualCommit"
}
if (-not $SkipInstall) {
    Invoke-Python -m pip install --require-hashes --only-binary=:all: -r "$BuildRoot\requirements-win.lock"
    Invoke-Python -m pip install -r "$BuildRoot\build-requirements.txt"
    # Set the wheel version even if a CI checkout contains only the pinned commit.
    $env:SETUPTOOLS_SCM_PRETEND_VERSION = '7.9.1'
    Invoke-Python -m pip install --no-deps "$TaskRoot\labelme-src"
}
Invoke-Python -m pip check
Invoke-Python -c 'import labelme; assert labelme.__version__ == "7.9.1", labelme.__version__'
Invoke-Python -m PyInstaller --clean --noconfirm --distpath "$TaskRoot\dist" --workpath "$TaskRoot\build" "$BuildRoot\labelme_portable.spec"
$Exe = "$TaskRoot\dist\Labelme-7.9.1-Windows-x64.exe"
if (-not (Test-Path $Exe)) { throw 'PyInstaller did not create the EXE.' }

# Run the actual frozen EXE, including its Qt and ONNX native libraries.
$Report = "$TaskRoot\dist\smoke-test.json"
$env:LABELME_PORTABLE_TEST_REPORT = $Report
try {
    $Process = Start-Process -FilePath $Exe -PassThru
    if (-not $Process.WaitForExit(180000)) {
        $Process.Kill()
        throw 'Frozen application smoke test timed out.'
    }
    if ($Process.ExitCode -ne 0) { throw "Frozen application exited with $($Process.ExitCode)." }
} finally {
    Remove-Item Env:LABELME_PORTABLE_TEST_REPORT -ErrorAction SilentlyContinue
}
if (-not (Test-Path $Report)) { throw 'The frozen application did not produce its test report.' }
$Result = Get-Content -Raw -Encoding UTF8 $Report | ConvertFrom-Json
if (-not $Result.ok) { throw "Frozen application smoke test failed: $($Result.error)" }

Copy-Item "$TaskRoot\labelme-src\LICENSE" "$TaskRoot\dist\LICENSE-GPL-3.0.txt"
Copy-Item "$BuildRoot\使用说明.txt" "$TaskRoot\dist\使用说明.txt"
Invoke-Python -m pip freeze --all | Out-File -Encoding UTF8 "$TaskRoot\dist\dependencies.txt"
$Digest = (Get-FileHash -Algorithm SHA256 $Exe).Hash.ToLowerInvariant()
"$Digest  Labelme-7.9.1-Windows-x64.exe" | Out-File -Encoding ascii "$TaskRoot\dist\SHA256SUMS.txt"
Write-Host "Build and frozen EXE smoke test passed: $Exe"
