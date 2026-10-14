$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run install_windows.bat before building.'
}
& $python -m pip install -e '.[build]'
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed with exit code $LASTEXITCODE."
}
$pytestRunId = [Guid]::NewGuid().ToString('N')
$pytestTemp = Join-Path $projectRoot "test_reports\pytest_build_temp_$pytestRunId"
& $python -m pytest -p no:cacheprovider --basetemp $pytestTemp
if ($LASTEXITCODE -ne 0) {
    throw "Source test suite failed with exit code $LASTEXITCODE."
}
& $python -m laserline3d --self-test --self-test-output (Join-Path $projectRoot 'test_reports\prebuild_self_test')
if ($LASTEXITCODE -ne 0) {
    throw "Source scan/export self-test failed with exit code $LASTEXITCODE."
}

# Build away from the published folder. PyInstaller removes an existing output
# directory before collecting files; if the app is running, that can otherwise
# leave a half-deleted package when Windows locks a DLL.
$stagingRoot = Join-Path $projectRoot 'output\windows\build-staging'
$stagedPackage = Join-Path $stagingRoot 'LaserLine3D'
if (Test-Path -LiteralPath $stagingRoot) {
    $resolvedStaging = (Resolve-Path -LiteralPath $stagingRoot).Path
    $allowedOutput = Join-Path $projectRoot 'output\windows\'
    if (-not $resolvedStaging.StartsWith($allowedOutput, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean unexpected staging path: $resolvedStaging"
    }
    Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
}
& $python -m PyInstaller --clean --noconfirm --distpath $stagingRoot (Join-Path $projectRoot 'packaging\LaserLine3D.spec')
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

$packagedExe = Join-Path $stagedPackage 'LaserLine3D.exe'
foreach ($required in @(
    $packagedExe,
    (Join-Path $stagedPackage '_internal\cv2\config.py'),
    (Join-Path $stagedPackage '_internal\cv2\config-3.py')
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Packaged dependency is missing: $required"
    }
}

$qtSmokeReport = Join-Path $projectRoot 'test_reports\packaged_qt_smoke.json'
if (Test-Path -LiteralPath $qtSmokeReport) {
    Remove-Item -LiteralPath $qtSmokeReport -Force
}
$smoke = Start-Process -FilePath $packagedExe -ArgumentList @(
    '--qt-smoke-test',
    '--qt-smoke-output',
    'test_reports\packaged_qt_smoke.json'
) -WorkingDirectory $projectRoot -Wait -PassThru -WindowStyle Hidden
if ($smoke.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $qtSmokeReport)) {
    throw "Packaged Qt smoke test failed with exit code $($smoke.ExitCode)."
}

$packagedSelfTest = Start-Process -FilePath $packagedExe -ArgumentList @(
    '--self-test',
    '--self-test-output',
    'test_reports\packaged_self_test'
) -WorkingDirectory $projectRoot -Wait -PassThru -WindowStyle Hidden
if ($packagedSelfTest.ExitCode -ne 0) {
    throw "Packaged scan/export self-test failed with exit code $($packagedSelfTest.ExitCode)."
}

if (Get-Process -Name LaserLine3D -ErrorAction SilentlyContinue) {
    throw 'Close every running LaserLine3D window before publishing this verified build. The tested staging package was preserved.'
}

$distRoot = Join-Path $projectRoot 'dist'
$applicationVersion = (& $python -c 'import laserline3d; print(laserline3d.__version__)').Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read the application version (exit code $LASTEXITCODE)."
}
if ($applicationVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "Unexpected application version: $applicationVersion"
}
$publishedName = "LaserLine3D_$applicationVersion"
$publishedPackage = Join-Path $distRoot $publishedName
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
$backupPackage = $null
if (Test-Path -LiteralPath $publishedPackage) {
    $backupPackage = Join-Path $distRoot ($publishedName + "_previous_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    Move-Item -LiteralPath $publishedPackage -Destination $backupPackage
}
try {
    Move-Item -LiteralPath $stagedPackage -Destination $publishedPackage
} catch {
    if ($backupPackage -and -not (Test-Path -LiteralPath $publishedPackage)) {
        Move-Item -LiteralPath $backupPackage -Destination $publishedPackage
    }
    throw
}
Set-Content -LiteralPath (Join-Path $distRoot 'CURRENT_PACKAGE.txt') -Value $publishedName -Encoding ascii

Write-Host "Build complete: $publishedPackage"
if ($backupPackage) {
    Write-Host "Previous package preserved: $backupPackage"
}
