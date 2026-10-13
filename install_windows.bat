@echo off
setlocal
cd /d "%~dp0"
echo.
echo LaserLine 3D - Windows setup
echo =============================
echo This creates a private Python environment inside the project.
echo.
py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 x64 was not found.
  echo Install it from https://www.python.org/downloads/windows/ and enable the Python launcher.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -e ".[test]"
if errorlevel 1 goto :failed
echo.
echo Setup complete. Double-click run_scanner.bat to start.
pause
exit /b 0
:failed
echo.
echo Setup did not complete. Check the message above and your internet connection.
pause
exit /b 1
