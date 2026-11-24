@echo off
REM Builds a double-click Deals.exe (needs Python on this PC; the result runs on PCs without Python).
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller requests beautifulsoup4 Pillow lxml keyring
python -m PyInstaller --noconfirm --windowed --name Deals --add-data "engine.py;." --add-data "ui_kit.py;." DealScraper.pyw
echo.
echo Done. Your app is in the dist\Deals folder - zip that folder to share it.
echo (Browser mode still needs Microsoft Edge or Chrome installed on the other PC.)
pause
