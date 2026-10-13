@echo off
setlocal
cd /d "%~dp0"
if exist "dist\LaserLine3D\LaserLine3D.exe" (
  if not exist "dist\LaserLine3D\_internal\cv2\config.py" goto :broken_package
  if not exist "dist\LaserLine3D\_internal\cv2\config-3.py" goto :broken_package
  start "LaserLine 3D" "dist\LaserLine3D\LaserLine3D.exe"
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
