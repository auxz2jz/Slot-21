@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run install_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m laserline3d --self-test --self-test-output test_reports\self_test
echo.
if errorlevel 1 (
  echo SELF-TEST FAILED
) else (
  echo SELF-TEST PASSED
)
pause
