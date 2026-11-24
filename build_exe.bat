@echo off
REM Optional local build of Deals.exe (the GitHub workflow does this automatically for releases).
python -m pip install --upgrade pyinstaller -r requirements.txt
python -m PyInstaller --noconfirm --clean --windowed --name Deals --collect-all playwright --hidden-import lxml.etree --add-data "engine.py;." --add-data "ui_kit.py;." --add-data "selftest.py;." --add-data "Fixtures;Fixtures" DealScraper.pyw
echo.
echo Built: dist\Deals\Deals.exe   (to make the installer too, open installer.iss in Inno Setup)
pause
