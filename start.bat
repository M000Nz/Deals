@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw DealScraper.pyw
  exit /b
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw DealScraper.pyw
  exit /b
)
echo Python is not installed yet.
echo.
echo 1. Download it from https://www.python.org/downloads/
echo 2. In the installer, tick "Add python.exe to PATH"
echo 3. Then double-click start.bat again
echo.
pause
