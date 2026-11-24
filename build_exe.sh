#!/bin/bash
# Builds a standalone Deals app (Mac/Linux). Needs Python on this machine; the result runs without it.
cd "$(dirname "$0")"
python3 -m pip install --upgrade pyinstaller requests beautifulsoup4 Pillow lxml keyring
python3 -m PyInstaller --noconfirm --windowed --name Deals --add-data "engine.py:." --add-data "ui_kit.py:." DealScraper.pyw
echo "Done. Your app is in the dist/ folder."
