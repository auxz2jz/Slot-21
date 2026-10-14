@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "PACKAGE_DIR=dist\LaserLine3D"
if exist "dist\CURRENT_PACKAGE.txt" (
  set /p PACKAGE_NAME=<"dist\CURRENT_PACKAGE.txt"
  if defined PACKAGE_NAME set "PACKAGE_DIR=dist\!PACKAGE_NAME!"
)
if exist "%PACKAGE_DIR%\LaserLine3D.exe" (
  if not exist "%PACKAGE_DIR%\_internal\cv2\config.py" goto :broken_package
  if not exist "%PACKAGE_DIR%\_internal\cv2\config-3.py" goto :broken_package
  start "LaserLine 3D" "%PACKAGE_DIR%\LaserLine3D.exe"
  exit /b 0
)
if not exist ".venv\Scripts\pythonw.exe" (
  echo LaserLine 3D is not installed yet. Extract the complete release ZIP or run install_windows.bat.
  pause
  exit /b 1
)
start "LaserLine 3D" ".venv\Scripts\pythonw.exe" -m laserline3d
exit /b 0

:broken_package
echo.
echo The packaged LaserLine 3D folder is incomplete.
echo Do not copy only LaserLine3D.exe or merge release folders.
echo Extract the complete release ZIP into a fresh folder, or run build_windows.ps1.
pause
exit /b 1
