#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python is not installed. Get it at https://www.python.org/downloads/"
  read -p "Press Enter to close..."
  exit 1
fi
LOG="$HOME/.dealscraper_error.log"
nohup python3 DealScraper.pyw >"$LOG" 2>&1 &
pid=$!
disown
sleep 3
if ! kill -0 $pid 2>/dev/null; then
  echo "Deal Scraper didn't start:"
  cat "$LOG"
  echo
  echo "If this mentions tkinter, install Python from https://www.python.org/downloads/ (it includes it)."
  read -p "Press Enter to close..."
fi
