param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$BuildRoot = $PSScriptRoot
$TaskRoot = Split-Path -Parent $BuildRoot
# Freeze the installed wheel built from this checkout, including its patches.
Set-Location $BuildRoot

# Hosted runners also contain unrelated Python tools (for example pipx).
# Build in a dedicated environment so their requirements cannot enter this
# application's dependency checks or PyInstaller analysis.
$BuildVenv = Join-Path $TaskRoot '.labelme-build-venv'
$BuildPython = Join-Path $BuildVenv 'Scripts\python.exe'
if (-not (Test-Path $BuildPython)) {
    & python -m venv $BuildVenv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the build virtual environment.' }
}

function Invoke-Python {
    & $BuildPython @args
    if ($LASTEXITCODE -ne 0) { throw "Python command failed: $args" }
}

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
    throw 'This build must run on Windows x64.'
}
Invoke-Python -c 'import struct,sys; assert sys.platform == "win32"; assert struct.calcsize("P") == 8; assert sys.version_info[:2] == (3,12), sys.version'
$ActualCommit = (& git -C $TaskRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not identify the modified source commit.' }
if (-not $SkipInstall) {
    Invoke-Python -m pip install --require-hashes --only-binary=:all: -r "$BuildRoot\requirements-win.lock"
    Invoke-Python -m pip install -r "$BuildRoot\build-requirements.txt"
    # Set the wheel version even if a CI checkout contains only the pinned commit.
    $env:SETUPTOOLS_SCM_PRETEND_VERSION = '7.9.1+layout.2'
    Invoke-Python -m pip install --no-deps $TaskRoot
    Invoke-Python -m pip install pytest==9.0.3 pytest-qt==4.5.0
}
Invoke-Python -m pip check
Invoke-Python -c 'import labelme; assert labelme.__version__ == "7.9.1+layout.2", labelme.__version__'
New-Item -ItemType Directory -Force -Path "$TaskRoot\dist" | Out-Null
$env:QT_QPA_PLATFORM = 'offscreen'
try {
    Invoke-Python -m pytest -q `
        "$TaskRoot\tests\e2e\tool_bar_layout_test.py" `
        "$TaskRoot\tests\e2e\window_geometry_persistence_test.py" `
        "$TaskRoot\tests\unit\widgets\_tool_bar_test.py" `
        "$TaskRoot\tests\unit\widgets\tool_bar_drag_test.py" `
        "$TaskRoot\tests\e2e\edge_click_test.py" `
        "$TaskRoot\tests\e2e\canvas_interaction_test.py" `
        "$TaskRoot\tests\e2e\settings_test.py" `
        "$TaskRoot\tests\unit\widgets\_canvas_test.py" `
        "$TaskRoot\tests\unit\widgets\_canvas_interaction" `
        "$TaskRoot\tests\unit\_config" `
        "--junitxml=$TaskRoot\dist\windows-tests.xml"
} finally {
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
}
Invoke-Python -m PyInstaller --clean --noconfirm --distpath "$TaskRoot\dist" --workpath "$TaskRoot\build" "$BuildRoot\labelme_portable.spec"
$Exe = "$TaskRoot\dist\Labelme-7.9.1-layout.2-Windows-x64.exe"
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

Copy-Item "$TaskRoot\LICENSE" "$TaskRoot\dist\LICENSE-GPL-3.0.txt"
Copy-Item "$BuildRoot\使用说明.txt" "$TaskRoot\dist\使用说明.txt"
Copy-Item "$BuildRoot\layout-release-notes.md" "$TaskRoot\dist\改动说明.md"
$ActualCommit | Out-File -Encoding ascii "$TaskRoot\dist\source-commit.txt"
Invoke-Python -m pip freeze --all | Out-File -Encoding UTF8 "$TaskRoot\dist\dependencies.txt"
$Digest = (Get-FileHash -Algorithm SHA256 $Exe).Hash.ToLowerInvariant()
"$Digest  $(Split-Path -Leaf $Exe)" | Out-File -Encoding ascii "$TaskRoot\dist\SHA256SUMS.txt"
Write-Host "Build and frozen EXE smoke test passed: $Exe"
