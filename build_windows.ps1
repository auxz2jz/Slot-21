$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run install_windows.bat before building.'
}
& $python -m pip install -e '.[build]'
& $python -m pytest
& $python -m laserline3d --self-test --self-test-output (Join-Path $projectRoot 'test_reports\prebuild_self_test')

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
$publishedPackage = Join-Path $distRoot 'LaserLine3D'
New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
$backupPackage = $null
if (Test-Path -LiteralPath $publishedPackage) {
    $backupPackage = Join-Path $distRoot ("LaserLine3D_previous_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
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

Write-Host "Build complete: $publishedPackage"
if ($backupPackage) {
    Write-Host "Previous package preserved: $backupPackage"
}
