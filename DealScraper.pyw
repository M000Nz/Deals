#!/usr/bin/env python3
"""
Deals - Australian deal finder.
Start it with start.bat (Windows) / start.command (Mac), or: python DealScraper.pyw
"""
import importlib
import importlib.util
import io
import json
import ctypes
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog
from tkinter import messagebox as _native_mb


class _ThemedMessages:
    """Drop-in for tkinter.messagebox that uses Deals' own black-and-white dialogs once the window exists."""
    app = None

    def _go(self, kind, title, message, **kw):
        app = self.app
        try:
            if app is not None and app.winfo_exists():
                return MsgDialog(app, kind, str(title), str(message), kw.get("parent")).result
        except Exception:  # noqa: BLE001
            pass
        return getattr(_native_mb, kind)(title, message, **{k: v for k, v in kw.items() if k == "parent"})

    def showinfo(self, title, message, **kw):
        return self._go("showinfo", title, message, **kw)

    def showwarning(self, title, message, **kw):
        return self._go("showwarning", title, message, **kw)

    def showerror(self, title, message, **kw):
        return self._go("showerror", title, message, **kw)

    def askyesno(self, title, message, **kw):
        return self._go("askyesno", title, message, **kw)

    askokcancel = askretrycancel = askyesno                 # same two-button box


messagebox = _ThemedMessages()

FROZEN = bool(getattr(sys, "frozen", False))                 # running as the packaged Deals.exe
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# Your data (database, error log) sits next to the program from source, or in %APPDATA%\\Deals when installed.
DATA_HOME = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Deals") if FROZEN else HERE
try:
    os.makedirs(DATA_HOME, exist_ok=True)
except OSError:
    pass
NO_PIL_MARK = os.path.join(DATA_HOME, ".no_pillow")
ERR_LOG = os.path.join(DATA_HOME, "deals_error.log")

if "--selftest" in sys.argv:                                   # used by the automatic build to prove the .exe works
    try:
        import engine as _E
        import selftest as _S
        _problems = _S.run()
        _out = "\n".join(_problems) if _problems else "All checks passed."
        _out = f"Deals {_E.ENGINE_VERSION} (frozen={FROZEN})\n" + _out
    except Exception:  # noqa: BLE001
        import traceback as _tb
        _problems, _out = ["crash"], _tb.format_exc()
    try:
        with open(os.path.join(DATA_HOME, "selftest_result.txt"), "w", encoding="utf-8") as _f:
            _f.write(_out)
    except OSError:
        pass
    print(_out)
    sys.exit(1 if _problems else 0)

try:
    import ui_kit as ui
except ImportError:
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror("Deals", "ui_kit.py is missing.\n\nCopy it into the same folder as DealScraper.pyw "
                                  "(all the files from the download go together), then start again.")
    sys.exit(1)
ui.enable_dpi_awareness()          # must happen before the first window, or Windows blurs the whole app


def log_error(text):
    """Append a traceback to deals_error.log (there's no console when launched by double-click)."""
    try:
        with open(ERR_LOG, "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{text}\n")
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# One-time setup: required add-ons (+ optional Pillow for thumbnails)
# --------------------------------------------------------------------------- #
def _has(mod):
    return importlib.util.find_spec(mod) is not None


def _pip(pkgs):
    cmd = [sys.executable, "-m", "pip", "install", *pkgs]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(cmd + ["--user"], capture_output=True, text=True)
    importlib.invalidate_caches()
    return r.returncode == 0, (r.stderr or "")[-400:]


def ensure_deps():
    if FROZEN:                                                  # everything is already inside the packaged app
        return
    missing = [p for p, m in (("requests", "requests"), ("beautifulsoup4", "bs4")) if not _has(m)]
    want_pil = not _has("PIL") and not os.path.exists(NO_PIL_MARK)
    if not missing and not want_pil:
        return
    root = tk.Tk()
    root.withdraw()
    if missing:
        pkgs = missing + (["pillow"] if want_pil else [])
        if not messagebox.askyesno("Deals - one-time setup",
                                   "Deals needs a few small add-ons: " + ", ".join(pkgs) +
                                   "\n(Pillow is for product thumbnails.)\n\nInstall now? Needs internet, ~20 seconds."):
            sys.exit(0)
        ok, err = _pip(pkgs)
        if not (_has("requests") and _has("bs4")):
            messagebox.showerror("Setup failed", "Couldn't install automatically. In a terminal run:\n"
                                 "    pip install requests beautifulsoup4 pillow\n\n" + err)
            sys.exit(1)
    else:
        if messagebox.askyesno("Deals - thumbnails",
                               "Install Pillow so results can show product thumbnails?\n"
                               "(Choose No to run without pictures.)"):
            ok, _ = _pip(["pillow"])
            if not ok:
                messagebox.showinfo("Deals", "Couldn't install Pillow, so thumbnails are off.")
        else:
            open(NO_PIL_MARK, "w").close()
    root.destroy()


ensure_deps()
import engine as E  # noqa: E402

if getattr(E, "ENGINE_VERSION", 0) < 105:
    _r = tk.Tk()
    _r.withdraw()
    messagebox.showerror("Deals", "engine.py is out of date.\n\nReplace it with the new engine.py from the "
                                  "download (it must sit in the same folder as DealScraper.pyw), then start again.")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageTk
    HAS_PIL = True
except Exception:  # noqa: BLE001
    HAS_PIL = False
ui.load_pil()
from ui_kit import RoundButton, Switch, PillEntry, ScrollFrame, Chart, draw_rrect, draw_pill, px  # noqa: E402

CARD_W, IMG_W, IMG_H = 204, 184, 142        # logical sizes; multiplied by the screen scale at run time
PAGE = 36
WATCH_SORTS = ["Added", "Closest to target", "Biggest drop", "Last checked", "Name"]
OZB_SORTS = ["Newest", "Most votes", "Biggest % off", "Biggest savings", "Price: low to high", "Price: high to low"]
PICK_SORTS = ["Biggest savings", "Highest deal score", "Best reviews", "Biggest % off", "Price: high to low",
              "Price: low to high", "Newest", "Shuffled"]
SORTS = ["Best match", "Best value", "Price: low to high", "Price: high to low", "Biggest discount", "Deal score", "Ending soon"]
AUTO = {"Off": 0, "15 min": 15, "30 min": 30, "1 hour": 60, "2 hours": 120,
        "6 hours": 360, "12 hours": 720, "Daily": 1440}
DROPS = ["5%", "10%", "15%", "20%", "30%", "50%"]
ALERT_FIELDS = [
    ("ntfy", "ntfy topic (phone)", False), ("discord", "Discord webhook URL", True),
    ("tg_token", "Telegram bot token", True), ("tg_chat", "Telegram chat id", False),
    ("email_host", "Email SMTP server", False), ("email_port", "Email SMTP port", False),
    ("email_user", "Email username", False), ("email_pass", "Email password", True),
    ("email_from", "Email from address", False), ("email_to", "Email to address", False),
]
PALETTES = {
    "light": dict(bg="#ffffff", fg="#000000", muted="#6b6b6b", line="#e6e6e6", border="#d9d9d9", hover="#f4f4f4",
                  accent="#047857", accent_fill="#059669", accent_on="#ffffff", alert="#ef4444"),
    "dark": dict(bg="#000000", fg="#ffffff", muted="#9a9a9a", line="#262626", border="#383838", hover="#161616",
                 accent="#34d399", accent_fill="#10b981", accent_on="#03140e", alert="#f87171"),
}
HOW = ("SEARCH\n"
       "Type what you want and press Enter. Deals asks about 180 Australian sources at once - big retailers, "
       "specialist shops, StaticICE (200+ more shops) and OzBargain - and ranks what comes back. Real discounts "
       "are listed first, regular prices after. Paste a product link instead and it finds the same product "
       "everywhere else.\n\n"
       "Tips: name a brand (apple watch) and only that brand shows. Use -word to leave something out. "
       "Model numbers are exact (galaxy watch 6 will not show a Watch 5). Spelling mistakes are fixed for you. "
       "If a search finds very little, Deals automatically widens it to every shop.\n\n"
       "WATCHLIST\n"
       "Click + Add item to follow a product. You are alerted when it hits your target price, drops in price "
       "or turns up as a discounted OzBargain deal. Each item keeps a price history graph; collapse items with "
       "the arrow to see just the latest change.\n\n"
       "DAILY DEALS\n"
       "Big-ticket items that are well below their normal price today. Use category to focus on a hobby "
       "(golf, cycling, camping, music...) - it searches that category itself, so you get fresh finds, not just "
       "a filtered list. Sort and Shuffle change the order only.\n\n"
       "FOR YOU\n"
       "Deals similar to what you follow. Press Interested or Not interested and the suggestions improve. "
       "A few outliers are mixed in to keep it fresh, and if you press Find more several times without "
       "reacting it moves on to other categories. Reset recommended starts again from scratch.\n\n"
       "SOURCES\n"
       "Sources > manage sources lists every shop with a status and the reason when one fails. Test one shop "
       "or all of them. Shops that keep failing are paused automatically so searches stay quick, and Repair "
       "tries to find a working search address. The shop list also refreshes itself from GitHub each time "
       "Deals opens, so new shops and fixed addresses arrive without an app update.\n\n"
       "GOOD TO KNOW\n"
       "Reviews (filter bar) add star ratings and what Reddit says. Prices are read automatically and can be "
       "wrong, so check the shop before you buy. Everything stays on your computer. Deals checks for updates "
       "each time it opens and installs them in one click.")


TERMS = ("Deals is for your own personal use. It reads public pages the way a browser would, one request at a time per "
         "site, and stops asking sites that refuse it. Store websites and Reddit can change or block this at any "
         "time, and their terms may restrict automated access, so don't use it to resell data or run it at high "
         "volume.\n\nEverything stays on this computer: your watchlist, price history and settings are in "
         "dealscraper.db next to the app. Alert passwords are kept in your system's password store when the "
         "'keyring' add-on is installed (pip install keyring); otherwise they sit in that file, so keep it private.\n\n"
         "Prices and reviews are read automatically and can be wrong. Check the store before you buy. Right-click "
         "a card to report a wrong price.")


def fmt_time(t):
    return time.strftime("%d %b %H:%M", time.localtime(t)) if t else "never"


def fmt_delta(sym, new, old):
    """'-$50.00 (-10%)' / '+$5.00 (+2%)' / 'no change' for a price moving from old to new."""
    d = new - old
    if not old or abs(d) < 0.005:
        return "no change"
    pct = abs(100 * d / old)
    sign, arrow = ("-", "\u25bc") if d < 0 else ("+", "\u25b2")
    p = f"{pct:.0f}" if pct >= 1 else f"{pct:.1f}"
    return f"{arrow} {E.money(sym, abs(d))} ({sign}{p}%)"


def history_text(sym, hist):
    if not hist:
        return "no history yet - run a check"
    prices = [h["price"] for h in hist]
    if len(prices) == 1:
        return "1 check so far - history builds as it checks"
    return (f"low {E.money(sym, min(prices))}   high {E.money(sym, max(prices))}   {len(prices)} checks\n"
            f"since first check: {fmt_delta(sym, prices[-1], prices[0])}")


# --------------------------------------------------------------------------- #
# Small widgets (all plain tk so they follow the black/white theme everywhere)
# --------------------------------------------------------------------------- #
# Hover explanations for drop-down items (matched on the start of the label, case-insensitive).
TIPS = [
    # sorting
    ("best match", "Closest to what you typed, with real deals first."),
    ("best value", "Balances a low price against how good the deal is."),
    ("price: low to high", "Cheapest first."),
    ("price: high to low", "Most expensive first."),
    ("biggest discount", "Largest percentage off the usual price first."),
    ("biggest savings", "Largest dollar amount saved first."),
    ("biggest % off", "Largest percentage off first."),
    ("biggest drop", "Items whose price has fallen the most since you added them."),
    ("deal score", "Highest 0-100 score first (discount, price history, shop and reviews combined)."),
    ("highest deal score", "Highest 0-100 score first (discount, price history, shop and reviews combined)."),
    ("ending soon", "Limited-time deals that finish first."),
    ("best reviews", "Highest-rated products first."),
    ("newest", "Most recently found first."),
    ("shuffled", "A random order - press Shuffle for a new one."),
    ("added", "In the order you added them."),
    ("closest to target", "Items nearest to your target price first."),
    ("last checked", "Most recently checked first."),
    ("name", "Alphabetical."),
    # reviews
    ("off", "Don't look up reviews."),
    ("show ratings", "Show a star rating on products when one can be found."),
    ("hide poor reviews", "Hide products that have clearly bad reviews."),
    ("only 4 stars and up", "Only show products rated 4 stars or higher."),
    # watchlist auto-check
    ("15 min", "Check your Watchlist every 15 minutes while Deals is open."),
    ("daily", "Check your Watchlist once a day."),
    # menus
    ("manage sources", "Switch individual shops on or off and set up browser mode."),
    ("test all sources", "Try a sample search at every shop and show which ones work."),
    ("add custom store", "Add a shop that isn't in the list by giving its search address."),
    ("update shop list", "Download the latest shared shop list from GitHub: new shops and fixed search addresses, no app update needed. This also happens automatically each time Deals opens."),
    ("repair broken sources", "Find the real search address for shops that say 'Search URL not found'."),
    ("reset built-in list", "Restore the built-in shop list. Your custom shops are kept."),
    ("alerts", "Choose how you're told about deals: phone, Discord, Telegram, email, summaries and quiet hours."),
    ("browser mode", "Let Deals read shops that need JavaScript using a hidden browser."),
    ("hidden sites", "Sites whose results you never want to see."),
    ("cashback", "Add your cashback rate so effective prices include it."),
    ("check all sources", "Test every shop with a sample search and list the ones that need attention."),
    ("weekly source check", "Quietly test all shops once a week and warn you if some stop working."),
    ("export watchlist report", "Save your Watchlist and its price history as a web page."),
    ("run at startup", "Start Deals minimised when you log in so alerts keep working."),
    ("export data", "Save your data as CSV files you can open in Excel."),
    ("back up database", "Save a copy of your watchlist, history and settings."),
    ("restore database", "Replace your data with a backup file. Deals restarts afterwards."),
    ("colour pictures", "Switch product pictures between colour and black-and-white."),
    ("light / dark", "Switch between the light and dark look."),
    ("how it works", "A short guide to how Deals finds and ranks deals."),
    ("fair use and privacy", "What Deals does with the websites it reads and with your data."),
    ("open error log", "Open the file that records any problems, for troubleshooting."),
    ("run self-check", "Test that prices are read correctly from saved sample pages."),
    ("check for updates", "See whether a newer version of Deals is available."),
    ("about", "Version information."),
    # card menu
    ("open page", "Open this product on the shop's website."),
    ("add to watchlist", "Track this product and get alerted when the price drops."),
    ("copy deal text", "Copy a short description of this deal to paste elsewhere."),
    ("add to side-by-side", "Add to a comparison of up to 3 products."),
    ("remove from comparison", "Take this product out of the comparison."),
    ("clear comparison", "Empty the comparison list."),
    ("wrong price", "Tell Deals this listing's price is wrong and hide it."),
]


def tip_for(label):
    low = (label or "").lower()
    for key, tip in TIPS:
        if low == key or (len(key) > 6 and low.startswith(key)):
            return tip
    return None


class MsgDialog(tk.Toplevel):
    """A themed message / question box. kind: showinfo | showwarning | showerror | askyesno."""

    def __init__(self, app, kind, title, message, parent=None):
        host = parent if parent is not None and parent.winfo_exists() else app
        super().__init__(host)
        self.result = False if kind == "askyesno" else "ok"
        self.withdraw()
        P = app.P
        self.title(ui.cap(title))
        self.transient(host)
        self.resizable(False, False)
        app.reg(self, "window")
        body = app.frame(self)
        body.pack(fill="both", expand=True, padx=px(26), pady=px(22))
        tone = P["alert"] if kind == "showerror" else P["fg"]
        head = tk.Label(body, text=ui.cap(title), font=app.f_big, bg=P["bg"], fg=tone, anchor="w", justify="left",
                        wraplength=px(460))
        head.pack(anchor="w")
        long_text = len(message) > 700 or message.count("\n") > 14
        if long_text:
            box = tk.Frame(body, bg=P["bg"])
            box.pack(fill="both", expand=True, pady=(px(10), 0))
            txt = tk.Text(box, wrap="word", font=app.f_norm, bg=P["bg"], fg=P["fg"], bd=0, highlightthickness=0,
                          width=62, height=18, padx=0, pady=0, spacing3=px(3), insertwidth=0,
                          selectbackground=P["fg"], selectforeground=P["bg"])
            sb = ui.SlimScrollbar(app, box, txt.yview)
            txt.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            txt.pack(side="left", fill="both", expand=True)
            txt.insert("1.0", message)
            txt.configure(state="disabled")
            txt.bind("<MouseWheel>", lambda e: txt.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        else:
            tk.Label(body, text=message, font=app.f_norm, bg=P["bg"], fg=P["fg"] if kind != "showinfo" else P["fg"],
                     anchor="w", justify="left", wraplength=px(460)).pack(anchor="w", pady=(px(10), 0))
        bar = app.frame(body)
        bar.pack(anchor="e", pady=(px(20), 0), fill="x")
        if kind == "askyesno":
            app.button(bar, "Yes", lambda: self._done(True), pad=(24, 7), style="solid", font=app.f_bold).pack(side="right")
            app.button(bar, "No", lambda: self._done(False), pad=(22, 7), style="outline").pack(side="right", padx=(0, 8))
            esc = lambda e=None: self._done(False)  # noqa: E731
        else:
            app.button(bar, "OK", lambda: self._done("ok"), pad=(28, 7), style="solid", font=app.f_bold).pack(side="right")
            esc = lambda e=None: self._done("ok")  # noqa: E731
        self.bind("<Return>", lambda e: self._done(True if kind == "askyesno" else "ok"))
        self.bind("<Escape>", esc)
        self.protocol("WM_DELETE_WINDOW", esc)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        ref = host if host.winfo_viewable() else app
        x = ref.winfo_rootx() + max(0, (ref.winfo_width() - w) // 2)
        y = ref.winfo_rooty() + max(0, (ref.winfo_height() - h) // 3)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.deiconify()
        try:
            self.wait_visibility()
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass
        self.wait_window(self)

    def _done(self, value):
        self.result = value
        self.destroy()


class Pop:
    """A text button that opens a themed dropdown list of items [(label, command) | None]. `current` (optional) is a
    function returning the chosen value, which gets a tick."""

    def __init__(self, app, parent, text, items, pad=(12, 4), style="outline", current=None):
        self.app, self.text, self.items, self.current = app, text, items, current
        self.btn = app.button(parent, "", self.open, pad=pad, style=style)
        self.refresh()

    def refresh(self):
        try:
            self.btn.configure(text=self.text() if callable(self.text) else self.text)
        except tk.TclError:
            pass                                    # the screen was redrawn and this button no longer exists

    def open(self):
        menu = ui.StyledMenu(self.app, tip_for=tip_for)
        cur = self.current() if self.current else None
        for it in self.items:
            if it is None:
                menu.add_separator()
            else:
                menu.add_command(label=it[0], command=it[1], checked=cur is not None and it[0] == cur)
        menu.tk_popup(self.btn.winfo_rootx(), self.btn.winfo_rooty() + self.btn.winfo_height() + px(4))

    def pack(self, **kw):
        self.btn.pack(**kw)


class Form(tk.Toplevel):
    """Modal form. fields: key,label,kind(entry|password|dropdown|check),values,default,hint,width."""

    def __init__(self, app, title, fields, ok_text="save", intro=None, validate=None, extras=()):
        super().__init__(app)
        self.app, self.validate, self.result, self.vars = app, validate, None, {}
        self.title(title[:1].upper() + title[1:])
        self.transient(app)
        self.resizable(False, False)
        app.reg(self, "window")
        body = app.frame(self)
        body.pack(padx=14, pady=12)
        r, first = 0, None
        if intro:
            app.label(body, intro, "muted", font=app.f_small, wraplength=420, justify="left").grid(
                row=r, column=0, columnspan=2, sticky="w", pady=(0, 8))
            r += 1
        for f in fields:
            kind = f.get("kind", "entry")
            v = tk.StringVar(value=f.get("default", ""))
            self.vars[f["key"]] = v
            if kind == "check":
                app.label(body, f["label"]).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=4)
                app.switch(body, v.get() == "1", lambda on, v=v: v.set("1" if on else "0")).grid(
                    row=r, column=1, sticky="w", pady=4)
            else:
                app.label(body, f["label"]).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=3)
                if kind == "dropdown":
                    app.dropdown(body, "", f["values"], v.get, v.set).btn.grid(row=r, column=1, sticky="w", pady=3)
                else:
                    e = app.entry(body, v, width=f.get("width", 36), show="*" if kind == "password" else "")
                    e.grid(row=r, column=1, sticky="we", pady=3, ipady=2)
                    first = first or e
            r += 1
            if f.get("hint"):
                app.label(body, f["hint"], "muted", font=app.f_small, wraplength=300, justify="left").grid(
                    row=r, column=1, sticky="w")
                r += 1
        bar = app.frame(body)
        bar.grid(row=r, column=0, columnspan=2, sticky="e", pady=(10, 0))
        for text, fn in extras:
            app.button(bar, text, lambda fn=fn: fn(self.collect())).pack(side="left", padx=(0, 6))
        app.button(bar, "cancel", self.destroy).pack(side="left", padx=(0, 6))
        app.button(bar, ok_text, self._ok).pack(side="left")
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = app.winfo_rootx() + max(0, (app.winfo_width() - w) // 2)
        y = app.winfo_rooty() + max(0, (app.winfo_height() - h) // 3)
        self.geometry(f"+{x}+{y}")
        if first:
            first.focus_set()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window(self)

    def collect(self):
        return {k: v.get().strip() for k, v in self.vars.items()}

    def _ok(self):
        data = self.collect()
        if self.validate:
            err = self.validate(data)
            if err:
                messagebox.showerror("check this", err, parent=self)
                return
        self.result = data
        self.destroy()


class ProgressOverlay:
    """A small card laid over a window that shows work is under way: title, bar, 'N of M' and the current item.
    'Hide' only hides it - the work carries on and show() brings it back."""

    def __init__(self, app, host, title, total, note=""):
        self.indet = total is None                          # no count: an animated bar and a live "what it's doing" line
        self.app, self.total, self.done, self.alive = app, max(total or 1, 1), 0, True
        self.t0, self.phase = time.time(), 0.0
        self.title_text, self.note, self.item_text, self.bad = title, note, "", None
        self.hidden, self.ov, self.host = False, None, None
        self._build(host)
        try:
            app.progs.append(self)
        except AttributeError:
            pass
        if self.indet:
            self._anim()

    def _build(self, host):
        app, P = self.app, self.app.P
        self.host = host
        self.ov = tk.Frame(host, bg=P["bg"], bd=0, highlightthickness=0)
        self.ov.place(x=0, y=0, relwidth=1, relheight=1)
        self.ov.lift()
        box = tk.Frame(self.ov, bg=P["bg"], bd=0, highlightthickness=1, highlightbackground=P["border"],
                       padx=px(36), pady=px(28))
        box.place(relx=0.5, rely=0.45, anchor="center")
        self.title = tk.Label(box, text=self.title_text, font=app.f_page, bg=P["bg"], fg=P["fg"], bd=0, anchor="w")
        self.title.pack(anchor="w")
        if self.note:
            tk.Label(box, text=self.note, font=app.f_small, bg=P["bg"], fg=P["muted"], bd=0, anchor="w", justify="left",
                     wraplength=px(380)).pack(anchor="w", pady=(6, 0))
        self.w, self.h = px(380), px(8)
        self.bar = tk.Canvas(box, width=self.w, height=self.h, bg=P["line"], bd=0, highlightthickness=0)
        self.bar.pack(anchor="w", pady=(18, 10))
        self.fill = self.bar.create_rectangle(0, 0, 0, self.h, fill=P["accent"], width=0)
        self.count = tk.Label(box, text="Working..." if self.indet else "Starting...", font=app.f_bold, bg=P["bg"],
                              fg=P["fg"], bd=0, anchor="w")
        self.count.pack(anchor="w")
        self.item = tk.Label(box, text="", font=app.f_small, bg=P["bg"], fg=P["muted"], bd=0, anchor="w", width=48)
        self.item.pack(anchor="w", pady=(2, 0))
        self.fails = tk.Label(box, text="", font=app.f_small, bg=P["bg"], fg=P["muted"], bd=0, anchor="w")
        self.fails.pack(anchor="w")
        app.button(box, "Hide", self.hide, pad=(18, 7), style="ghost").pack(anchor="w", pady=(16, 0))
        self.hidden = False
        self._paint()

    def _paint(self):
        """Put the stored progress onto the widgets (used when the card is rebuilt in another window)."""
        try:
            self.item.configure(text=self.item_text)
            if self.bad is not None:
                self.fails.configure(text=f"{self.bad} not working so far")
            if not self.indet and self.done:
                self.bar.coords(self.fill, 0, 0, self.w * min(self.done / self.total, 1.0), self.h)
                self.count.configure(text=f"{self.done} of {self.total}   ({100 * self.done // self.total}%)")
        except tk.TclError:
            pass

    def hide(self):
        self.hidden = True
        try:
            self.ov.place_forget()
        except tk.TclError:
            pass

    def show(self, host=None):
        """Bring the card back, over `host` if given (rebuilt there if it was made in another window)."""
        if not self.alive:
            return
        try:
            if host is not None and host is not self.host and host.winfo_exists():
                try:
                    self.ov.destroy()
                except tk.TclError:
                    pass
                self._build(host)
            else:
                self.ov.place(x=0, y=0, relwidth=1, relheight=1)
                self.ov.lift()
                self.hidden = False
        except tk.TclError:
            # its window is gone: rebuild over the main window
            try:
                self._build(self.app)
            except tk.TclError:
                pass

    def _anim(self):
        """Indeterminate mode: a bar segment sweeps back and forth, with the seconds so far."""
        if not self.alive:
            return
        try:
            self.phase = (self.phase + 0.035) % 2.0
            p = self.phase if self.phase <= 1.0 else 2.0 - self.phase
            seg = self.w * 0.3
            x = (self.w - seg) * p
            self.bar.coords(self.fill, x, 0, x + seg, self.h)
            self.count.configure(text=f"Working...  {int(time.time() - self.t0)}s")
            self.bar.after(40, self._anim)
        except tk.TclError:
            self.alive = False

    def step(self, text):
        """What is happening right now (shown under the bar)."""
        if self.alive:
            try:
                self.item_text = text[:70]
                self.item.configure(text=self.item_text)
            except tk.TclError:
                self.alive = False

    def update(self, done, item="", bad=None):
        if not self.alive:
            return
        try:
            self.done = done
            self.bar.coords(self.fill, 0, 0, self.w * min(done / self.total, 1.0), self.h)
            self.count.configure(text=f"{done} of {self.total}   ({100 * done // self.total}%)")
            self.item_text = ui.cap(item)[:60]
            self.item.configure(text=self.item_text)
            if bad is not None:
                self.bad = bad
                self.fails.configure(text=f"{bad} not working so far")
        except tk.TclError:
            self.alive = False

    def close(self):
        self.alive = False
        try:
            self.app.progs.remove(self)
        except (AttributeError, ValueError):
            pass
        try:
            self.ov.destroy()
        except tk.TclError:
            pass


class AlertsDialog(tk.Toplevel):
    """Where Deals sends its alerts, explained step by step for each option, with a Test button that says what happened."""
    MODES = {"Right away": "instant", "One message a day": "summary"}

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Alerts")
        self.transient(app)
        self.geometry(f"{px(640)}x{px(760)}+{app.winfo_rootx() + px(70)}+{app.winfo_rooty() + px(30)}")
        app.reg(self, "window")
        s = E.get_settings(E.db())
        self.v = {k: tk.StringVar(value=s.get(k, "")) for k in
                  ("ntfy", "discord", "tg_token", "tg_chat", "email_host", "email_port", "email_user", "email_pass",
                   "email_from", "email_to", "summary_hour", "quiet_start", "quiet_end")}
        self.popups = s.get("popups", "1") == "1"
        self.quiet_on = s.get("quiet_on", "0") == "1"
        self.mode = "One message a day" if s.get("alert_mode") == "summary" else "Right away"
        self.chips = {}
        sf = ScrollFrame(app, self)
        self.sf = sf
        bar = app.frame(self)
        bar.pack(side="bottom", fill="x", padx=14, pady=10)
        app.frame(self, "line", height=1).pack(side="bottom", fill="x")
        sf.outer.pack(fill="both", expand=True)
        app.button(bar, "save", self.save, style="solid").pack(side="right")
        app.button(bar, "cancel", self.destroy, style="ghost").pack(side="right", padx=(0, 6))
        self.build(sf.inner)

    # -- small building blocks
    def head(self, parent, title, sub="", chip=None):
        app = self.app
        app.frame(parent, "line", height=1).pack(fill="x", padx=18, pady=(14, 0))
        row = app.frame(parent)
        row.pack(fill="x", padx=18, pady=(12, 0))
        app.label(row, title, font=app.f_big).pack(side="left")
        if chip:
            self.chips[chip] = app.label(row, "", "accent", font=app.f_small_b)
            self.chips[chip].pack(side="left", padx=10)
        if sub:
            app.label(parent, sub, "muted", font=app.f_small, wraplength=px(560), justify="left").pack(
                anchor="w", padx=18, pady=(2, 0))

    def steps(self, parent, lines):
        for i, t in enumerate(lines, 1):
            r = self.app.frame(parent)
            r.pack(fill="x", padx=18, pady=(4, 0))
            self.app.label(r, f"{i}.", "accent", font=self.app.f_small_b).pack(side="left", anchor="n")
            self.app.label(r, t, font=self.app.f_small, wraplength=px(540), justify="left").pack(
                side="left", padx=(8, 0), anchor="w")

    def field(self, parent, label, key, show="", width=34, hint=""):
        app = self.app
        r = app.frame(parent)
        r.pack(fill="x", padx=18, pady=(8, 0))
        app.label(r, label, "muted", font=app.f_small).pack(anchor="w")
        app.entry(r, self.v[key], width=width, show=show).pack(anchor="w", pady=(2, 0))
        if hint:
            app.label(r, hint, "muted", font=app.f_small, wraplength=px(540), justify="left").pack(anchor="w", pady=(2, 0))

    def test_row(self, parent, chan, extra=None):
        r = self.app.frame(parent)
        r.pack(fill="x", padx=18, pady=(10, 0))
        self.app.button(r, "Send a test", lambda: self.test(chan), style="outline").pack(side="left")
        for text, cmd in (extra or []):
            self.app.button(r, text, cmd, style="ghost").pack(side="left", padx=(6, 0))
        return r

    def build(self, p):
        app = self.app
        app.label(p, "Alerts", font=app.f_page).pack(anchor="w", padx=18, pady=(16, 0))
        app.label(p, "Deals tells you when something on your Watchlist reaches your target price or goes on sale. Pick where "
                     "those messages go - you can use more than one, and you can skip any you don't want. Every option has a "
                     "Send a test button so you know it works.", "muted", font=app.f_small, wraplength=px(580),
                  justify="left").pack(anchor="w", padx=18, pady=(4, 0))

        self.head(p, "On this computer", "A small box in the corner of your screen. No setup. It only appears while Deals is "
                                          "open (it can stay open in the notification area).")
        r = app.frame(p)
        r.pack(anchor="w", padx=18, pady=(8, 0))
        self.sw_pop = app.switch(r, self.popups, lambda v: setattr(self, "popups", v))
        self.sw_pop.pack(side="left")
        app.label(r, "Show a pop-up when a deal is found").pack(side="left", padx=10)

        self.head(p, "When should alerts be sent?")
        r = app.frame(p)
        r.pack(anchor="w", padx=18, pady=(8, 0))
        app.dropdown(r, "", list(self.MODES), lambda: self.mode, lambda v: setattr(self, "mode", v)).pack(side="left")
        r2 = app.frame(p)
        r2.pack(anchor="w", padx=18, pady=(6, 0))
        app.label(r2, "If \"one message a day\": send it after", "muted", font=app.f_small).pack(side="left")
        app.entry(r2, self.v["summary_hour"], width=4).pack(side="left", padx=6)
        app.label(r2, "o'clock (0-23, so 8 = 8am)", "muted", font=app.f_small).pack(side="left")
        r3 = app.frame(p)
        r3.pack(anchor="w", padx=18, pady=(12, 0))
        self.sw_quiet = app.switch(r3, self.quiet_on, lambda v: setattr(self, "quiet_on", v))
        self.sw_quiet.pack(side="left")
        app.label(r3, "Quiet hours - nothing while I sleep").pack(side="left", padx=10)
        r4 = app.frame(p)
        r4.pack(anchor="w", padx=18, pady=(6, 0))
        app.label(r4, "Quiet from", "muted", font=app.f_small).pack(side="left")
        app.entry(r4, self.v["quiet_start"], width=4).pack(side="left", padx=6)
        app.label(r4, "until", "muted", font=app.f_small).pack(side="left")
        app.entry(r4, self.v["quiet_end"], width=4).pack(side="left", padx=6)
        app.label(r4, "(e.g. 22 and 7 = 10pm to 7am). Alerts found meanwhile arrive together afterwards.", "muted",
                  font=app.f_small, wraplength=px(330), justify="left").pack(side="left")

        self.head(p, "On your phone - ntfy (the easiest)", "Free. No account. Works on iPhone and Android.", chip="ntfy")
        self.steps(p, ["On your phone, install the free app called \"ntfy\" (App Store or Google Play).",
                       "Press the button below to make yourself a private name, or type your own. Anyone who knows the name can "
                       "read your alerts, so make it hard to guess (letters and numbers only).",
                       "In the ntfy app, tap the + button, choose \"Subscribe to topic\" and type exactly the same name.",
                       "Press Send a test. Your phone should buzz within a few seconds."])
        self.field(p, "Your private name", "ntfy", width=30)
        self.test_row(p, "ntfy", [("Make me a private name", self.make_topic)])

        self.head(p, "Discord", "If you already use Discord, alerts can appear in a channel of your own server.", chip="discord")
        self.steps(p, ["In Discord, open your server's settings > Integrations > Webhooks > New Webhook.",
                       "Choose the channel the alerts should go to, then press \"Copy Webhook URL\".",
                       "Paste it below and press Send a test."])
        self.field(p, "Webhook URL", "discord", show="*", width=44)
        self.test_row(p, "discord")

        self.head(p, "Telegram", "Alerts arrive as a message from your own little bot.", chip="telegram")
        self.steps(p, ["In Telegram, search for \"BotFather\" (the one with the blue tick), send it /newbot and follow its "
                       "questions. It then gives you a long \"token\" - paste it below.",
                       "Open a chat with your new bot and press Start (or send it any message). This step is easy to miss and "
                       "alerts won't arrive without it.",
                       "To find your chat id, message the bot \"userinfobot\" - it replies with a number. Paste that number below.",
                       "Press Send a test."])
        self.field(p, "Bot token", "tg_token", show="*", width=44)
        self.field(p, "Your chat id (a number)", "tg_chat", width=20)
        self.test_row(p, "telegram")

        self.head(p, "Email", "Deals sends the alert from your email account to any address you choose.", chip="email")
        self.steps(p, ["Easiest with Gmail: press \"Fill in for Gmail\" below. Other providers: search for \"<your provider> SMTP "
                       "settings\" and type the server and port.",
                       "Most providers won't accept your normal password here. For Gmail, turn on 2-step verification, then "
                       "create an \"App password\" in your Google account security page, and paste that as the password.",
                       "Fill in the rest (your email address is the username), then press Send a test and check your inbox "
                       "(and Junk)."])
        self.field(p, "Mail server", "email_host", width=30)
        self.field(p, "Port (usually 587)", "email_port", width=8)
        self.field(p, "Username (your email address)", "email_user", width=34)
        self.field(p, "Password (an app password for Gmail)", "email_pass", show="*", width=34)
        self.field(p, "Send from (leave blank to use your username)", "email_from", width=34)
        self.field(p, "Send alerts to", "email_to", width=34)
        self.test_row(p, "email", [("Fill in for Gmail", self.fill_gmail)])
        app.frame(p, height=18).pack()
        self.update_chips()
        for k in ("ntfy", "discord", "tg_token", "tg_chat", "email_host", "email_to"):
            self.v[k].trace_add("write", lambda *a: self.update_chips())

    # -- behaviour
    def make_topic(self):
        import secrets
        self.v["ntfy"].set("deals-" + secrets.token_hex(5))

    def fill_gmail(self):
        self.v["email_host"].set("smtp.gmail.com")
        self.v["email_port"].set("587")

    def configured(self):
        g = lambda k: self.v[k].get().strip()
        return {"ntfy": bool(g("ntfy")), "discord": bool(g("discord")),
                "telegram": bool(g("tg_token") and g("tg_chat")), "email": bool(g("email_host") and g("email_to"))}

    def update_chips(self):
        for k, ok in self.configured().items():
            try:
                self.chips[k].configure(text="\u2713 set up" if ok else "")
            except (KeyError, tk.TclError):
                pass

    def test(self, chan):
        g = lambda k: self.v[k].get().strip()
        cfg = {"ntfy": {"ntfy": g("ntfy")}, "discord": {"discord": g("discord")},
               "telegram": {"tg_token": g("tg_token"), "tg_chat": g("tg_chat")},
               "email": {k: g(k) for k in ("email_host", "email_port", "email_user", "email_pass", "email_from", "email_to")}}[chan]
        if not self.configured()[chan]:
            return messagebox.showinfo("alerts", "Fill in the boxes for this option first (see the steps above them).")
        if chan == "ntfy" and (len(cfg["ntfy"]) < 6 or not re.fullmatch(r"[A-Za-z0-9_\-]+", cfg["ntfy"])):
            return messagebox.showinfo("alerts", "Use at least 6 letters or numbers, with no spaces. "
                                       "Press \"Make me a private name\" if you're not sure.")
        problems = []
        self.app.set_status("sending a test...")

        def work():
            E.notify(cfg, "Deals test", "If you can read this, alerts to this place work.", None, problems.append)

            def finish():
                self.app.set_status("ready")
                if problems:
                    messagebox.showinfo("alerts", "That didn't work:\n\n" + problems[0][:300] +
                                        "\n\nCheck the boxes against the steps above and try again.")
                else:
                    where = {"ntfy": "your phone (open the ntfy app)", "discord": "your Discord channel",
                             "telegram": "Telegram", "email": "your inbox (check Junk too)"}[chan]
                    messagebox.showinfo("alerts", f"Test sent. It should arrive on {where} within a minute.")
            self.app.q.put(finish)
        threading.Thread(target=work, daemon=True).start()

    def save(self):
        con = E.db()
        d = {k: self.v[k].get().strip() for k in self.v}
        for k in ("summary_hour", "quiet_start", "quiet_end"):
            try:
                d[k] = str(max(0, min(23, int(float(d[k])))))
            except ValueError:
                d[k] = E.DEFAULTS[k]
        d["popups"] = "1" if self.popups else "0"
        d["quiet_on"] = "1" if self.quiet_on else "0"
        d["alert_mode"] = self.MODES.get(self.mode, "instant")
        for k, v in d.items():
            E.set_setting(con, k, v)
        self.app.set_status("alert settings saved")
        self.destroy()


class StoresDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Sources")
        self.transient(app)
        self.geometry(f"{px(560)}x{px(620)}+{app.winfo_rootx() + px(60)}+{app.winfo_rooty() + px(40)}")
        app.reg(self, "window")
        self.head = app.label(self, "", "muted", font=app.f_small, justify="left", wraplength=500)
        self.head.pack(fill="x", padx=10, pady=(8, 6))
        brow = app.frame(self)
        brow.pack(fill="x", padx=10, pady=(0, 10))
        self.b_sw = app.switch(brow, E.get_settings(E.db()).get("browser", "1") == "1", app.set_browser)
        self.b_sw.pack(side="left")
        app.label(brow, "Read JavaScript stores in a browser").pack(side="left", padx=10)
        self.b_btn = app.button(brow, "Set up", app.install_browser, pad=(12, 3))
        self.b_status = app.label(brow, "", "muted", font=app.f_small)
        self.b_row = brow
        app.stores_dialog = self
        self.update_browser_row()
        app.frame(self, "line", height=1).pack(fill="x")
        srow = app.frame(self)
        srow.pack(fill="x", padx=10, pady=(8, 8))
        self.q = tk.StringVar()
        self.q_entry = app.entry(srow, self.q, width=34)
        self.q_entry.pack(side="left")
        self.count = app.label(srow, "", "muted", font=app.f_small)
        self.count.pack(side="left", padx=10)
        clear = app.label(srow, "clear", "muted", font=app.f_small, cursor="hand2")
        clear.bind("<Button-1>", lambda e: self.q.set(""))
        clear.pack(side="right")
        self.q.trace_add("write", lambda *a: self._filter_soon())
        app.frame(self, "line", height=1).pack(fill="x")
        self.sf = ScrollFrame(app, self)
        self.sf.outer.pack(fill="both", expand=True)
        # Only the rows on screen exist as widgets (a small pool that is re-used while scrolling); with a couple of
        # hundred shops, one widget set per shop made scrolling stutter and draw blank patches.
        self.ROW_H = px(42)
        self.pool, self.rows, self.view, self._first = [], [], [], -1
        self._vt = self._ft = None
        self.sf.canvas.configure(yscrollcommand=self._on_yview)
        self.sf.canvas.bind("<Configure>", self._on_canvas, add="+")
        self.empty = app.label(self.sf.inner, "", "muted")
        app.frame(self, "line", height=1).pack(fill="x")
        bar = app.frame(self)
        bar.pack(fill="x", padx=10, pady=6)
        self.b_test = app.button(bar, "Test all", lambda: app.test_stores(self.refresh, host=self))
        self.b_test.pack(side="left", padx=(0, 6))
        self.b_prog = app.button(bar, "Show progress", self.show_progress)
        self.prog_bar = bar
        app.button(bar, "add custom...", lambda: app.add_store(self.refresh)).pack(side="left", padx=(0, 6))
        app.button(bar, "reset list", lambda: (app.reset_stores(), self.refresh())).pack(side="left")
        app.button(bar, "close", self.destroy).pack(side="right")
        self._gen = 0
        self.after(10, self.refresh)               # the window appears at once; the rows fill in right after
        self.poll_progress()

    def show_progress(self):
        for p in reversed(self.app.progs):
            if p.alive:
                p.show(self)
                break
        self.poll_progress()

    def poll_progress(self):
        """'Show progress' only appears while something is running with its card hidden."""
        try:
            if not self.winfo_exists():
                return
            hidden = any(p.alive and p.hidden for p in self.app.progs)
            shown = bool(self.b_prog.winfo_manager())
            if hidden and not shown:
                self.b_prog.pack(side="left", padx=(0, 6), after=self.b_test)
            elif not hidden and shown:
                self.b_prog.pack_forget()
            self.after(500, self.poll_progress)
        except tk.TclError:
            pass

    def update_browser_row(self):
        st = E.browser_status(E.get_settings(E.db()))
        self.b_status.configure(text=st)
        self.b_btn.pack_forget()
        self.b_status.pack_forget()
        needs = st == "not installed" or st.startswith("problem")
        if needs:
            self.b_btn.pack(side="right")
        self.b_status.pack(side="right", padx=8)

    def update_head(self):
        con = E.db()
        region = E.get_settings(con)["region"] or self.app.region
        rows = con.execute("SELECT enabled FROM stores WHERE region=? OR custom=1", (region,)).fetchall()
        on = sum(1 for r in rows if r["enabled"])
        self.head.configure(text=f"{on}/{len(rows)} Australian sources on.  Flip a switch to turn one off.  "
                                 "\u2713 = returning products, \u2717 = blocked or not working (the reason is shown).")

    def refresh(self):
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        app, con = self.app, E.db()
        region = E.get_settings(con)["region"] or app.region
        self.rows = [dict(r) for r in con.execute("SELECT * FROM stores WHERE region=? OR custom=1 ORDER BY custom, name",
                                                  (region,)).fetchall()]
        self.update_head()
        app.prune()
        self._apply_filter(keep_scroll=True)

    # ---- search + virtual list -------------------------------------------------------------------------------
    def _status(self, r):
        st = r.get("status") or "Not tested"
        if (r.get("skip_until") or 0) > time.time():
            st += "  \u00b7  paused until " + time.strftime("%d %b", time.localtime(r["skip_until"]))
        return st

    def _filter_soon(self):
        if self._ft:
            self.after_cancel(self._ft)
        self._ft = self.after(120, lambda: self._apply_filter(keep_scroll=False))

    def _apply_filter(self, keep_scroll):
        self._ft = None
        self._gen += 1
        words = self.q.get().lower().split()
        if words:
            self.view = [r for r in self.rows
                         if all(w in f"{r['name']} {self._status(r)} {r.get('search_url') or ''}".lower() for w in words)]
        else:
            self.view = list(self.rows)
        n, total = len(self.view), len(self.rows)
        self.count.configure(text=f"{n} of {total}" if words else f"{total} sources")
        cv = self.sf.canvas
        frac = cv.yview()[0] if keep_scroll else 0.0
        self.sf.inner.configure(height=max(1, n * self.ROW_H))
        self.sf.canvas.configure(scrollregion=(0, 0, 1, max(1, n * self.ROW_H)))
        if n:
            self.empty.place_forget()
        else:
            self.empty.configure(text="No sources match that search.")
            self.empty.place(x=14, y=14)
        cv.yview_moveto(frac)
        self._first = -1
        self._show()

    def _on_yview(self, a, b):
        self.sf.sb.set(a, b)
        if not self._vt:
            self._vt = self.after_idle(self._show)

    def _on_canvas(self, e):
        self._first = -1
        if not self._vt:
            self._vt = self.after_idle(self._show)

    def _make_slot(self):
        app = self.app
        row = app.frame(self.sf.inner)
        row.pack_propagate(False)
        slot = {"row": row, "idx": None, "id": None, "state": None}
        app.frame(row, "line", height=1).pack(side="bottom", fill="x", padx=12)
        slot["sw"] = app.switch(row, False, lambda on, sl=slot: self.set_enabled(sl["id"], on))
        slot["name"] = app.label(row, "")
        slot["x"] = app.label(row, "\u00d7", "muted", cursor="hand2")
        slot["x"].bind("<Button-1>", lambda e, sl=slot: self.delete(sl["id"]))
        slot["test"] = app.button(row, "Test", lambda sl=slot: self.test_one(sl["id"]), pad=(10, 2), style="ghost",
                                  font=app.f_small)
        slot["verify"] = app.button(row, "Verify", lambda sl=slot: self.verify_one(sl["id"]), pad=(10, 2),
                                    style="ghost", font=app.f_small)
        slot["st"] = app.label(row, "", "muted", font=app.f_small)
        return slot

    def _show(self):
        self._vt = None
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        cv, H = self.sf.canvas, self.ROW_H
        n = len(self.view)
        need = min(n, cv.winfo_height() // H + 4)
        while len(self.pool) < need:
            self.pool.append(self._make_slot())
        top = int(cv.canvasy(0) // H)
        first = max(0, min(top - 1, max(0, n - need)))
        size = max(1, len(self.pool))
        used = set()
        for i in range(first, min(n, first + need)):
            slot = self.pool[i % size]
            used.add(id(slot))
            if slot["idx"] != i or slot.get("gen") != self._gen:
                self._bind(slot, i)
        for slot in self.pool:
            if id(slot) not in used and slot["idx"] is not None:
                slot["row"].place_forget()
                slot["idx"] = None
        self._first = first

    def _bind(self, slot, i):
        r = self.view[i]
        slot["idx"], slot["id"], slot["gen"] = i, r["id"], self._gen
        slot["row"].place(x=0, y=i * self.ROW_H, relwidth=1, height=self.ROW_H)
        slot["sw"].set(bool(r["enabled"]))
        slot["name"].configure(text=r["name"] + (" (custom)" if r["custom"] else ""))
        st = self._status(r)
        mark = {"v": "\u2713", "x": "\u2717", "-": "\u00b7"}[E.status_mark(st)]
        slot["st"].configure(text=f"{mark} {st}")
        flagged = any(w in st.lower() for w in ("bot", "blocked", "protection"))
        state = (bool(r["custom"]), flagged)
        if slot["state"] != state:
            slot["state"] = state
            for k in ("x", "test", "verify", "st"):
                slot[k].pack_forget()
            slot["sw"].pack(side="left", padx=(12, 0))
            slot["name"].pack(side="left", padx=10)
            if r["custom"]:
                slot["x"].pack(side="right", padx=(0, 12))
            slot["test"].pack(side="right")
            if flagged:
                slot["verify"].pack(side="right", padx=(0, 4))
            slot["st"].pack(side="right", padx=8)

    def test_one(self, i):
        self.app.test_store_one(i, self.refresh, host=self)

    def verify_one(self, i):
        self.app.verify_store(i, self.refresh, host=self)

    def set_enabled(self, i, on):
        con = E.db()
        con.execute("UPDATE stores SET enabled=? WHERE id=?", (1 if on else 0, i))
        con.commit()
        for r in self.rows:                       # keep the list in memory in step, so a re-used row shows the right switch
            if r["id"] == i:
                r["enabled"] = 1 if on else 0
        self.update_head()

    def delete(self, i):
        if messagebox.askyesno("delete", "Delete this custom store?", parent=self):
            con = E.db()
            con.execute("DELETE FROM stores WHERE id=? AND custom=1", (i,))
            con.commit()
            self.refresh()


def wrap_lines(text, font, width, max_lines):
    """Word-wrap `text` to at most max_lines lines no wider than `width` px, ending in an ellipsis if cut."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if font.measure(t) <= width:
            cur = t
            continue
        if cur:
            lines.append(cur)
            if len(lines) >= max_lines:
                cur = ""
                break
        cur = w
        while font.measure(cur) > width and len(cur) > 1:          # a single very long word
            cut = len(cur)
            while cut > 1 and font.measure(cur[:cut]) > width:
                cut -= 1
            lines.append(cur[:cut])
            cur = cur[cut:]
            if len(lines) >= max_lines:
                cur = ""
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    lines = lines[:max_lines]
    if lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while last and font.measure(last + "\u2026") > width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "\u2026"
    return lines or [""]


class Card(tk.Canvas):
    """A product card: large picture, then title, price, saving and store. Deals use the emerald accent."""

    def __init__(self, app, parent, o, sym, deal, prev=None):
        self.app, self.o, self.sym, self.deal = app, o, sym, deal
        self.photo, self.hover = None, False
        f, tw = app.fm, app.cw - 2 * px(12)
        pct, kind = deal
        self.title_lines = wrap_lines(o.title, f["title"], tw, 2)
        if kind == "markdown":
            self.save = f"\u25bc Save {E.money(sym, o.was_price - o.price)}  ({pct:.0f}% off)"
        elif kind == "below":
            self.save = f"\u25bc {E.money(sym, o.ref_price - o.price)} ({pct:.0f}%) below other shops"
        elif kind == "dropped" and prev:
            self.save = f"\u25bc Dropped {E.money(sym, prev - o.price)} ({pct:.0f}%)"
        elif kind == "ozb":
            self.save = "OzBargain deal"
        else:
            self.save = ""
        self.save = wrap_lines(self.save, f["small_b"], tw, 1)[0] if self.save else ""
        meta = [o.store] + ([f"{o.votes:+d} votes"] if o.source == "ozb" else []) + (["accessory"] if o.accessory else [])
        if o.oos:
            meta.append("out of stock")
        if o.used:
            meta.append("refurbished / used")
        if o.match == "exact":
            meta.append("\u2713 same product")
        if o.others:
            meta.append(f"+{len(o.others)} more store{'s' if len(o.others) > 1 else ''} from "
                        f"{E.money(sym, min(x.price for x in o.others))}")
        if app.cash_pct > 0:
            meta.append(f"~{E.money(sym, E.effective_price(o.price, app.cash_pct))} after cashback")
        self.meta = wrap_lines("  \u00b7  ".join(meta), f["small"], tw, 1)[0]
        self.expiry = wrap_lines(E.expiry_text(o.expires), f["small_b"], tw, 1)[0] if o.expires else ""
        self.lt, self.lp, self.ls = (f["title"].metrics("linespace"), f["price"].metrics("linespace"),
                                     f["small"].metrics("linespace"))
        pad = px(10)
        self.nl = 4                                                    # info lines under the price
        self.review = app.review_line(o)
        self.hv = app.hist_verdict(o)
        self.low = wrap_lines(E.low_line(o, app.hist.get(o.url), sym), f["small"], app.cw - 2 * px(12), 1)[0] \
            if getattr(app, "hist", None) else ""
        self.meta_y = (0, 0)
        self.tip_kind = None
        self.star_box = (0, 0, 0, 0)
        self.h = pad + app.ih + px(8) + 2 * self.lt + px(4) + self.lp + px(3) + self.nl * self.ls + pad
        super().__init__(parent, width=app.cw, height=self.h, bd=0, highlightthickness=0, cursor="hand2")
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._leave())
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Button-3>", lambda e: app.card_menu(e, self))
        self.bind("<Button-2>", lambda e: app.card_menu(e, self))
        self.plus_box = (0, 0, 0, 0)
        self.added = app.is_watched(o.title)
        self.redraw()

    def _hit(self, e):
        for name, (x0, y0, x1, y1) in (("plus", self.plus_box), ("star", self.star_box)):
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                return name
        return None

    def _motion(self, e):
        kind = self._hit(e)
        if kind != self.tip_kind:
            self.tip_kind = kind
            self.show_tip(kind)

    def show_tip(self, kind):
        self.delete("tip")
        self.tip_kind = kind
        if not kind:
            self.configure(cursor="hand2")
            return
        self.configure(cursor="plus" if kind == "plus" else "hand2")
        app, f, P = self.app, self.app.fm, self.app.P
        if kind == "plus":
            text = "On your Watchlist" if self.added else "Add to Watchlist"
            box = self.plus_box
        else:
            text = app.star_tip(self.o)
            box = self.star_box
        edge = px(6)
        text = wrap_lines(text, f["small_b"], app.cw - 2 * edge - px(18), 1)[0]      # never wider than the card
        w, h = f["small_b"].measure(text) + px(18), f["small_b"].metrics("linespace") + px(10)
        x0 = max(edge, min(self.plus_box[2] - w, app.cw - w - edge))                # right-aligned, kept inside the card
        y0 = self.plus_box[3] + px(4)                                                # just under the buttons, on the picture
        n0 = len(self.find_all())
        draw_pill(self, x0, y0, w, h, P["fg"])
        self.create_text(x0 + w / 2, y0 + h / 2, text=text, font=f["small_b"], fill=P["bg"])
        for item in self.find_all()[n0:]:
            self.addtag_withtag("tip", item)

    def set_review(self, review):
        self.review = review
        self.redraw()

    def _click(self, e):
        hit = self._hit(e)
        if hit == "plus":
            self.app.add_watch(self)
        elif hit == "star":
            self.app.review_menu(e, self)
        elif self.o.others and self.meta_y[0] <= e.y <= self.meta_y[1]:
            self.app.open_compare(self.o)
        else:
            self.app.viewed(self.o)
            self.app.open_url(self.o.url)

    def _hover(self, on):
        """Highlight the border. Only the border picture is swapped - a full redraw on every Enter/Leave is what made
        scrolling flicker as cards slid under the pointer."""
        if on == self.hover:
            return
        self.hover = on
        if on and time.perf_counter() < getattr(self.app, "scroll_until", 0):
            self.hover = False                                    # cards are moving under a still pointer: ignore
            return
        frame = getattr(self, "_frame", None)
        if frame is None:
            return self.redraw()
        P = self.app.P
        try:
            if ui.can_aa():
                ph = ui.aa_rrect(int(self.app.cw), int(self.h), int(px(14)), P["bg"], P["fg"] if on else P["border"],
                                 max(1, px(1)), P["bg"])
                self._keep.append(ph)
                self.itemconfigure(frame, image=ph)
            else:
                self.itemconfigure(frame, outline=P["fg"] if on else P["border"])
        except tk.TclError:
            pass

    def _leave(self):
        self.tip_kind = None
        self._hover(False)

    def set_photo(self, photo):
        """Swap just the picture (a full redraw of every card as its image arrives is what made scrolling choppy)."""
        if photo is self.photo:
            return
        self.photo = photo
        if getattr(self, "_has_pic", False):
            self.itemconfigure("pic", image=photo)
            self._keep = [photo]
            return
        pad = px(10)
        self.delete("ph")
        self.create_image(pad, pad, image=photo, anchor="nw", tags=("pic",))
        self._keep = [photo]
        self._has_pic = True
        self.tag_lower("pic", "badge")

    def redraw(self):
        app, o = self.app, self.o
        P, f = app.P, app.fm
        pct, kind = self.deal
        cw, ih, pad = app.cw, app.ih, px(10)
        tk.Canvas.configure(self, bg=P["bg"])
        self.delete("all")
        self.tip_kind = None
        self._keep = []
        self._frame = draw_rrect(self, 0, 0, cw, self.h, px(14), P["bg"], P["fg"] if self.hover else P["border"],
                                 max(1, px(1)), P["bg"])
        self._has_pic = self.photo is not None
        if self.photo is not None:
            self._keep.append(self.photo)
            self.create_image(pad, pad, image=self.photo, anchor="nw", tags=("pic",))
        else:
            n0 = len(self.find_all())
            draw_rrect(self, pad, pad, app.iw, ih, px(10), P["hover"], P["hover"], 0, P["bg"])
            self.create_text(pad + app.iw / 2, pad + ih / 2, text=o.store[:24], font=f["small"], fill=P["muted"])
            for item in self.find_all()[n0:]:
                self.addtag_withtag("ph", item)
        if kind and (pct or 0) >= 1:                                  # saving badge on the picture
            t = f"-{pct:.0f}%"
            bw, bh = f["small_b"].measure(t) + px(16), f["small_b"].metrics("linespace") + px(5)
            bx, by = pad + px(8), pad + px(8)
            n0 = len(self.find_all())
            draw_pill(self, bx, by, bw, bh, P["accent_fill"])
            self.create_text(bx + bw / 2, by + bh / 2, text=t, font=f["small_b"], fill=P["accent_on"])
            for item in self.find_all()[n0:]:
                self.addtag_withtag("badge", item)
        size = px(28)                                                  # + button: add to the Watchlist
        bx2, by2 = pad + app.iw - size - px(8), pad + px(8)
        self.plus_box = (bx2 - px(3), by2 - px(3), bx2 + size + px(3), by2 + size + px(3))
        n0 = len(self.find_all())
        if self.added:
            draw_pill(self, bx2, by2, size, size, P["accent_fill"])
            self.create_text(bx2 + size / 2, by2 + size / 2, text="\u2713", font=f["small_b"], fill=P["accent_on"])
        else:
            ui.draw_badge(self, bx2, by2, size, P["bg"], P["border"], max(1, px(1)))
            self.create_text(bx2 + size / 2, by2 + size / 2 - px(1), text="+", font=f["price"], fill=P["fg"])
        sx = bx2 - size - px(6)                                          # reviews button, just left of +
        self.star_box = (sx - px(3), by2 - px(3), sx + size + px(3), by2 + size + px(3))
        ui.draw_badge(self, sx, by2, size, P["bg"], P["border"], max(1, px(1)))
        has = app.rev_info.get(o.url)
        tone = E.review_verdict(has)[0] if has else None
        self.create_text(sx + size / 2, by2 + size / 2 - px(1), text="\u2605", font=f["small_b"],
                         fill=P["accent"] if tone == "good" else P["alert"] if tone == "poor" else P["fg"])
        for item in self.find_all()[n0:]:
            self.addtag_withtag("badge", item)
        x, y = px(12), pad + ih + px(8)
        for ln in self.title_lines:
            self.create_text(x, y, anchor="nw", text=ln, font=f["title"], fill=P["fg"])
            y += self.lt
        y = pad + ih + px(8) + 2 * self.lt + px(4)
        price = "FREE" if o.source == "ozb-free" else E.money(self.sym, o.price)
        self.create_text(x, y, anchor="nw", text=price, font=f["price"], fill=P["accent"] if kind else P["fg"])
        if kind == "markdown" and o.was_price:
            self.create_text(x + f["price"].measure(price) + px(8), y + (self.lp - self.ls) // 2 + px(1), anchor="nw",
                             text=E.money(self.sym, o.was_price), font=f["was"], fill=P["muted"])
        series = (app.hist.get(o.url) or {}).get("series") or []
        if len(series) >= 3 and max(series) > min(series):
            sw, sh = px(46), px(16)
            end = x + f["price"].measure(price) + (px(8) + f["was"].measure(E.money(self.sym, o.was_price))
                                                   if kind == "markdown" and o.was_price else 0)
            sx0 = cw - px(12) - sw
            if end + px(8) < sx0:
                lo, hi = min(series), max(series)
                pts = []
                for i, v in enumerate(series):
                    pts += [sx0 + sw * i / (len(series) - 1), y + (self.lp - sh) // 2 + sh * (1 - (v - lo) / (hi - lo))]
                col = P["accent"] if series[-1] < series[0] else P["alert"] if series[-1] > series[0] else P["muted"]
                self.create_line(*pts, fill=col, width=max(1, px(1)), smooth=False)
        y += self.lp + px(3)
        # info lines under the price; at most `nl` fit, so the most useful win (lower number = more important)
        cand = []
        htone, htext = self.hv
        if self.save and htone != "inflated":
            cand.append((0, 0, self.save, f["small_b"], P["accent"]))
        if htone == "inflated":
            cand.append((0, 0, wrap_lines("\u26a0 " + htext, f["small_b"], app.cw - 2 * px(12), 1)[0], f["small_b"], P["alert"]))
        elif htone == "lowest":
            cand.append((1, 1, wrap_lines("\u2713 " + htext, f["small_b"], app.cw - 2 * px(12), 1)[0], f["small_b"], P["accent"]))
        if kind and not o.accessory:
            sc, lab, _ = app.deal_score(o)
            if sc >= 20:
                cand.append((1, 1.5, f"Deal score {sc}  \u00b7  {lab}", f["small_b"],
                             P["accent"] if sc >= 55 else P["fg"] if sc >= 35 else P["muted"]))
        cand.append((2, 2, self.meta, f["small"], P["fg"] if o.others else P["muted"]))
        if self.low:
            cand.append((2, 2.5, self.low, f["small"], P["muted"]))
        if o.coupon and app.show_codes:
            cm = f"Code {o.coupon}" + (f"  \u00b7  ends {time.strftime('%d %b', time.localtime(o.expires))}" if o.expires else "")
            cand.append((0, 0.8, wrap_lines(cm, f["small_b"], app.cw - 2 * px(12), 1)[0], f["small_b"], P["accent"]))
        if self.expiry:
            cand.append((1, 4, self.expiry, f["small_b"], P["fg"]))
        if app.rev_mode != "Off":
            tone, rtext = self.review if self.review else (None, "")
            if rtext:
                col = P["accent"] if tone == "good" else P["alert"] if tone == "poor" else P["fg"]
                mark = "\u2713 " if tone == "good" else "\u26a0 " if tone == "poor" else ""
                cand.append((3, 3, wrap_lines(mark + rtext, f["small_b"], app.cw - 2 * px(12), 1)[0], f["small_b"], col))
            else:
                cand.append((4, 3, self.app.review_wait(), f["small"], P["muted"]))
        keep = sorted(sorted(cand)[:self.nl], key=lambda c: c[1])
        for _, _, text, font, col in keep:
            if text == self.meta:
                self.meta_y = (y, y + self.ls)
            self.create_text(x, y, anchor="nw", text=text, font=font, fill=col)
            y += self.ls


class HistoryDialog(tk.Toplevel):
    def __init__(self, app, item_id):
        super().__init__(app)
        con = E.db()
        item = con.execute("SELECT * FROM watchlist WHERE id=?", (item_id,)).fetchone()
        if not item:
            self.destroy()
            return
        sym = E.get_settings(con)["currency"]
        hist = E.price_history(con, item_id)
        self.title("Price history")
        self.transient(app)
        app.reg(self, "window")
        self.geometry(f"{px(600)}x{px(540)}+{app.winfo_rootx() + px(80)}+{app.winfo_rooty() + px(50)}")
        app.label(self, item["keywords"], font=app.f_big).pack(anchor="w", padx=12, pady=(10, 2))
        app.label(self, history_text(sym, hist), "muted", font=app.f_small, justify="left").pack(anchor="w", padx=12)
        reg = E.regular_price(con, item_id)
        if reg:
            app.label(self, f"Usual price (not on sale): {E.money(sym, reg[0])}  -  from {reg[1]} listings", "muted",
                      font=app.f_small).pack(anchor="w", padx=12)
        Chart(app, self, [h["price"] for h in hist], height=110,
              lines=[(item["max_price"], "target"), (reg[0] if reg else None, "usual")]).pack(fill="x", padx=12, pady=8)
        app.advice_lines(self, E.buy_advice(item["best_price"], reg[0] if reg else None, hist, sym=sym), 560, padx=12)
        app.frame(self, "line", height=1).pack(fill="x")
        sf = ScrollFrame(app, self)
        sf.outer.pack(fill="both", expand=True)
        if not hist:
            app.label(sf.inner, "No checks yet. Press 'check watchlist'.", "muted").pack(anchor="w", padx=12, pady=12)
        for i in range(len(hist) - 1, -1, -1):          # newest first
            h = hist[i]
            row = app.frame(sf.inner)
            row.pack(fill="x", padx=12, pady=2)
            change = fmt_delta(sym, h["price"], hist[i - 1]["price"]) if i > 0 else "first check"
            cells = [app.label(row, fmt_time(h["t"]), "muted", width=13),
                     app.label(row, E.money(sym, h["price"]), font=app.f_bold, width=11),
                     app.label(row, change, "accent" if change.startswith("\u25bc") else "alert" if change.startswith("\u25b2") else "text", width=19),
                     app.label(row, h["store"], "muted", font=app.f_small)]
            for c in cells:
                c.pack(side="left")
            for w in [row] + cells:
                w.bind("<Button-1>", lambda e, u=h["url"]: app.open_url(u))
                w.configure(cursor="hand2")
        app.frame(self, "line", height=1).pack(fill="x")
        bar = app.frame(self)
        bar.pack(fill="x", padx=12, pady=6)
        app.button(bar, "close", self.destroy).pack(side="right")


# --------------------------------------------------------------------------- #
# The app
# --------------------------------------------------------------------------- #
class CompareDialog(tk.Toplevel):
    """The same product at every store we found it, cheapest first."""

    def __init__(self, app, o):
        super().__init__(app)
        self.title("Compare stores")
        self.transient(app)
        app.reg(self, "window")
        sym = app.sym()
        rows = sorted([o] + list(o.others), key=lambda x: (x.oos, x.price))
        body = app.frame(self)
        body.pack(padx=18, pady=14)
        app.label(body, o.title[:90], font=app.f_big).pack(anchor="w")
        low = rows[0].price
        for x in rows:
            app.frame(body, "line", height=1).pack(fill="x", pady=(8, 0))
            line = app.frame(body)
            line.pack(fill="x", pady=6)
            app.label(line, E.money(sym, x.price), "accent" if x.price == low and not x.oos else "text",
                      font=app.f_big, width=11).pack(side="left")
            mid = app.frame(line)
            mid.pack(side="left", fill="x", expand=True)
            extra = (" - out of stock" if x.oos else "") + (f"   (+{E.money(sym, x.price - low)})" if x.price > low else "")
            app.label(mid, x.store + extra, font=app.f_bold).pack(anchor="w")
            if x.was_price and x.was_price > x.price:
                app.label(mid, f"was {E.money(sym, x.was_price)}", "muted", font=app.f_small).pack(anchor="w")
            hint = E.price_match_hint(x.store) if x.price > low else None
            if hint:
                app.label(mid, "Tip: " + hint, "muted", font=app.f_small, wraplength=360, justify="left").pack(anchor="w")
            if app.cash_pct > 0:
                app.label(mid, f"~{E.money(sym, E.effective_price(x.price, app.cash_pct))} after {app.cash_pct:g}% cashback",
                          "muted", font=app.f_small).pack(anchor="w")
            app.button(line, "Open", lambda u=x.url: app.open_url(u), pad=(14, 4), font=app.f_small).pack(side="right")
            if x.price > low and not rows[0].oos:
                app.button(line, "Price match", lambda x=x: app.copy_price_match(o.title, rows[0], x.store), pad=(12, 4),
                           font=app.f_small, style="ghost").pack(side="right", padx=(0, 6))
        app.label(body, "Shops can differ on delivery cost and stock - check at the store.", "muted", font=app.f_small).pack(
            anchor="w", pady=(10, 0))
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{app.winfo_rootx() + max(0, (app.winfo_width() - w) // 2)}+{app.winfo_rooty() + max(0, (app.winfo_height() - h) // 4)}")
        self.bind("<Escape>", lambda e: self.destroy())


class ProductCompare(tk.Toplevel):
    """2-3 products in columns: the facts that decide a purchase, with the best value in each row highlighted."""

    def __init__(self, app, offers):
        super().__init__(app)
        self.title("Compare products")
        self.transient(app)
        app.reg(self, "window")
        sym = app.sym()
        body = app.frame(self)
        body.pack(padx=18, pady=14)
        low = min(o.price for o in offers)
        scores = [app.deal_score(o)[0] for o in offers]
        rats = [E.review_rating(app.rev_info.get(o.url)) for o in offers]
        best_sc = max(scores)
        best_rt = max((r for r in rats if r), default=None)
        rows = [("", [o.title[:70] for o in offers], None),
                ("Store", [o.store for o in offers], None),
                ("Price", [E.money(sym, o.price) for o in offers], [o.price == low for o in offers]),
                ("Was", [E.money(sym, o.was_price) if o.was_price and o.was_price > o.price else "-" for o in offers], None),
                ("Discount", [f"{E.deal_pct(o)[0]:.0f}% off" if E.deal_pct(o)[0] else "-" for o in offers], None),
                ("Deal score", [f"{sc}  {E.deal_score(o)[1]}" if sc else "-" for sc, o in zip(scores, offers)],
                 [sc == best_sc and sc > 0 for sc in scores]),
                ("Reviews", [E.review_verdict(app.rev_info.get(o.url))[1] or "not checked yet" for o in offers],
                 [bool(r) and r == best_rt for r in rats]),
                ("Price history", [E.price_verdict(o, app.hist.get(o.url))[1] or "-" for o in offers], None),
                ("Also at", [f"{len(o.others)} other store(s) from {E.money(sym, min(x.price for x in o.others))}" if o.others else "-"
                             for o in offers], None)]
        for r, (name, vals, best) in enumerate(rows):
            app.label(body, name, "muted", font=app.f_small).grid(row=r, column=0, sticky="nw", padx=(0, 14), pady=5)
            for c, v in enumerate(vals):
                hi = bool(best and best[c])
                app.label(body, v, "accent" if hi else "text", font=app.f_big if name == "Price" else
                          (app.f_bold if name in ("", "Deal score") or hi else app.f_small),
                          wraplength=210, justify="left").grid(row=r, column=c + 1, sticky="nw", padx=8, pady=5)
        for c, o in enumerate(offers):
            app.button(body, "Open", lambda u=o.url: app.open_url(u), pad=(14, 4), font=app.f_small).grid(
                row=len(rows), column=c + 1, sticky="w", padx=8, pady=(8, 0))
        app.button(body, "Clear", lambda: (app.cmp.clear(), self.destroy()), pad=(12, 4), style="ghost",
                   font=app.f_small).grid(row=len(rows), column=0, sticky="w", pady=(8, 0))
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{app.winfo_rootx() + max(0, (app.winfo_width() - w) // 2)}+{app.winfo_rooty() + max(0, (app.winfo_height() - h) // 4)}")
        self.bind("<Escape>", lambda e: self.destroy())


class TextDialog(tk.Toplevel):
    """Modal box with a multi-line text area. `.result` is the text, or None if cancelled."""

    def __init__(self, app, title, intro, ok_text="add"):
        super().__init__(app)
        self.result = None
        self.title(title[:1].upper() + title[1:])
        self.transient(app)
        app.reg(self, "window")
        body = app.frame(self)
        body.pack(padx=14, pady=12)
        app.label(body, intro, "muted", font=app.f_small, wraplength=460, justify="left").pack(anchor="w", pady=(0, 8))
        self.txt = app.reg(tk.Text(body, width=60, height=10, bd=0, highlightthickness=1, font=app.f_norm, wrap="word"), "entry")
        self.txt.pack()
        bar = app.frame(body)
        bar.pack(fill="x", pady=(10, 0))
        app.button(bar, ok_text, self.ok, pad=(16, 5), style="solid").pack(side="right")
        app.button(bar, "cancel", self.destroy, pad=(14, 5), style="ghost").pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda e: self.destroy())
        self.txt.focus_set()
        self.grab_set()
        app.wait_window(self)

    def ok(self):
        self.result = self.txt.get("1.0", "end").strip()
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        messagebox.app = self
        ui.init_scale(self)                      # screen scale (1.0 = 96 dpi) for crisp, correctly sized UI
        ui.patch_geometry()
        self.title("Deals")
        self.cw, self.ih = px(CARD_W), px(IMG_H)
        self.iw = self.cw - 2 * px(10)
        self.minsize(px(860), px(560))
        fam = tkfont.nametofont("TkDefaultFont").actual("family")   # the system UI font
        self.f_norm, self.f_small = (fam, 10), (fam, 9)
        self.f_bold, self.f_bold_u = (fam, 10, "bold"), (fam, 10, "bold underline")
        self.f_big, self.f_title = (fam, 12, "bold"), (fam, 13, "bold")
        self.f_small_b = (fam, 9, "bold")
        self.f_hero = (fam, 26, "bold")
        self.f_logo = (fam, 26, "bold")
        self.f_page = (fam, 18, "bold")
        self.fm = {"title": tkfont.Font(font=(fam, 10)), "price": tkfont.Font(font=(fam, 14, "bold")),
                   "small": tkfont.Font(font=(fam, 9)), "small_b": tkfont.Font(font=(fam, 9, "bold")),
                   "was": tkfont.Font(font=(fam, 9, "overstrike"))}

        self.q = queue.Queue()
        self.tray, self._tray_told, self.tray_close = None, False, False
        self._testing_all, self._test_prog = False, None
        self._stream, self._stream_sig, self._dev_clicks, self._dev_t = False, None, 0, 0.0
        self._digest_busy, self._ml_busy, self._ml_pending = False, False, []
        self._pc_busy, self._pc_base, self._pc_dots = None, "", 0
        self._pc_banner = self._pc_title = None
        self._sb_mode, self._sb_frame, self._sb_title, self._sb_sub, self._sb_bar = None, None, None, None, None
        self._sb_done, self._sb_total, self._sb_n, self._sb_t0, self._sb_dots, self._sb_anim = 0, 0, 0, 0.0, 0, False
        self._pc_redraw = False
        self.show_hidden, self.hidden_offers = False, []      # "Show hidden listings" at the bottom of the results
        self._sgen, self._scancel = 0, None               # which search is current, and how to stop the one before
        self.progs = []                                   # running progress cards (so a hidden one can be brought back)
        self._err_count = 0
        self.reg_list, self.scrollers = [], {}
        s = E.get_settings(E.db())
        self.dark = s.get("theme", "dark") == "dark"
        self.region = "Australia"
        self.stores_dialog = None
        self.hide_acc = s.get("hide_acc", "0") == "1"
        self.limited = s.get("limited", "0") == "1"
        self.hide_used = s.get("hide_used", "1") == "1"
        self.group = s.get("group", "1") == "1"
        try:
            self.cash_pct = float(s.get("cashback") or 0)
        except ValueError:
            self.cash_pct = 0.0
        self.hist, self.results_all = {}, []
        self.link_info, self.fixed, self.did_mean = None, None, None
        self.rev_mode = s.get("reviews") if s.get("reviews") in E.REVIEW_MODES else "Off"
        self.rev_info, self.rev_busy, self.cards_by_url, self.pick_pool = {}, False, {}, []
        self._rev_pend = set()
        self.colour_pics = s.get("colour", "0") == "1"
        self.show_codes = s.get("show_codes", "1") == "1"
        self.view, self.cols, self._relayout = "home", 3, None
        self.sort = s.get("sort") if s.get("sort") in SORTS else SORTS[0]
        try:
            self.auto_minutes = int(float(s.get("auto") or 0))
        except ValueError:
            self.auto_minutes = 0
        self.next_at = time.time() + 5 if self.auto_minutes else None
        self.scanning = self.searching = False
        self.popups_shown = 0
        self.results, self.shown, self.query = [], PAGE, ""
        self.prev_prices = {}
        self.thumb_targets, self.pil_cache, self.photo_cache, self.thumb_pending = {}, {}, {}, set()
        self.thumb_fail, self.thumb_pages = {}, {}
        self._mask_cache = {}
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.status_var = tk.StringVar(value="ready")
        self.next_var = tk.StringVar(value="")
        self.info_var = tk.StringVar(value="")

        self.configure(bg=self.P["bg"])
        self.geometry(self.initial_geometry(s))
        self.chrome = ui.Frameless(self)
        self.wants_frameless = (sys.platform == "win32" and s.get("classic_frame", "0") != "1"
                                and "--classic" not in sys.argv)
        self.build()
        if self.wants_frameless and not self.chrome.enable():
            log_error("Custom window frame couldn't be set up; using the normal Windows frame.")
        self.chrome.raise_grips()
        self.chrome.recolour(self.P["bg"])
        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Button-4>", self._wheel)
        self.bind_all("<Button-5>", self._wheel)
        self.bind("<Control-l>", lambda e: self.focus_search())
        self.bind("<Control-k>", lambda e: self.focus_search())
        self.bind("<slash>", self._slash)
        self.bind("<Control-h>", lambda e: self.show_home())
        self.bind("<Control-r>", lambda e: self.start_check())
        self.show_home()
        if s.get("deals_seen") is None:                  # deals from before this version aren't "new"
            self.mark_deals_seen()
        self.update_badge()
        if "--minimized" in sys.argv:                     # started at login: stay out of the way, keep checking
            self.after(600, self.chrome.minimize if self.chrome.on else self.iconify)
        else:
            self.after(700, self.first_run_browser)
        self.after(150, self.pump)
        self.after(300, self.start_tray)
        self.after(1000, self.tick)
        self.after(5000, self.auto_update_check)
        self.after(2500, lambda: self.sync_shop_list(silent=True))
        self.after(60, self.style_window)
        self.set_icon()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------------------------------------------------------- theme --
    @property
    def P(self):
        return PALETTES["dark" if getattr(self, "dark", False) else "light"]

    def report_callback_exception(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        log_error(text)
        self._err_count += 1
        try:
            self.set_status("error - details saved in deals_error.log")
            if self._err_count <= 2:
                messagebox.showerror("Deals - something went wrong",
                                     text[-1200:] + "\n(saved to deals_error.log)")
        except Exception:  # noqa: BLE001
            pass

    def reg(self, w, role):
        self.reg_list.append((w, role))
        self.style(w, role)
        return w

    def style(self, w, role):
        P = self.P
        try:
            if hasattr(w, "redraw"):                       # custom canvas widgets repaint themselves
                w.redraw()
            elif role == "bg":
                w.configure(bg=P["bg"])
            elif role == "line":
                w.configure(bg=P["line"])
            elif role == "text":
                w.configure(bg=P["bg"], fg=P["fg"])
            elif role == "muted":
                w.configure(bg=P["bg"], fg=P["muted"])
            elif role == "accent":
                w.configure(bg=P["bg"], fg=P["accent"])
            elif role == "alert":
                w.configure(bg=P["bg"], fg=P["alert"])
            elif role == "btn":
                w.configure(bg=P["bg"], fg=P["fg"], highlightbackground=P["fg"], highlightcolor=P["fg"])
            elif role == "entry":
                w.configure(bg=P["bg"], fg=P["fg"], insertbackground=P["fg"], highlightbackground=P["line"],
                            highlightcolor=P["fg"], selectbackground=P["fg"], selectforeground=P["bg"])
            elif role == "menu":
                w.configure(bg=P["bg"], fg=P["fg"], activebackground=P["fg"], activeforeground=P["bg"])
            elif role == "canvas":
                w.configure(bg=P["bg"])
            elif role == "window":
                w.configure(bg=P["bg"])
                ui.style_titlebar(w, self.dark, P["bg"], P["fg"], P["border"])
        except Exception:  # noqa: BLE001  (a widget that can't take a colour must never break the app)
            pass

    def prune(self, force=False):
        if not force and len(self.reg_list) < 2500:      # checking every widget on every redraw is wasted work while the list is short
            return
        live = []
        for w, role in self.reg_list:
            try:
                if w.winfo_exists():
                    live.append((w, role))
            except tk.TclError:
                pass
        self.reg_list = live

    def apply_theme(self):
        try:
            self.configure(bg=self.P["bg"])
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())
        try:
            self.chrome.recolour(self.P["bg"])
            if self.chrome.on:
                self.chrome._corners(not self.chrome.maxed)        # keeps the thin window border in the new theme's colour
        except Exception:  # noqa: BLE001
            pass
        try:
            self.prune(True)
            for w, role in self.reg_list:
                self.style(w, role)
            self.render_watch()
            self.render_results()
            if self.view in ("daily", "foryou", "ozb", "free"):
                self.render_picks(self.view)
            if self.view == "home":
                self.refresh_home()
            self.style_window()
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())
            self.set_status("theme change failed - details in deals_error.log")

    def toggle_theme(self):
        self.dark = not self.dark
        try:
            E.set_setting(E.db(), "theme", "dark" if self.dark else "light")
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())
        if getattr(self, "theme_sw", None) is not None:
            self.theme_sw.set(self.dark)
        self.apply_theme()

    def set_dark(self, on):
        if bool(on) != self.dark:
            self.toggle_theme()

    # ------------------------------------------------------------ factories --
    def frame(self, parent, role="bg", **kw):
        for k in ("width", "height"):
            if k in kw:
                kw[k] = px(kw[k])
        return self.reg(tk.Frame(parent, bd=0, highlightthickness=0, **kw), role)

    def label(self, parent, text="", role="text", font=None, **kw):
        kw.setdefault("anchor", "w")
        if "wraplength" in kw:
            kw["wraplength"] = px(kw["wraplength"])
        return self.reg(tk.Label(parent, text=ui.cap(text), font=font or self.f_norm, bd=0, padx=0, pady=0, **kw), role)

    def button(self, parent, text, cmd, font=None, pad=(12, 4), style="outline"):
        return self.reg(RoundButton(self, parent, text, cmd, font or self.f_norm, pad, style), "btn")

    def switch(self, parent, value=False, command=None):
        return self.reg(Switch(self, parent, value, command), "switch")

    def entry(self, parent, var, width=30, show="", font=None, big=False):
        return self.reg(PillEntry(self, parent, var, width, show, font, big), "entry")

    def dropdown(self, parent, prefix, values, get, setter):
        box = {}

        def choose(v):
            setter(v)
            box["p"].refresh()

        p = Pop(self, parent, lambda: f"{prefix}{get()} \u25be", [(v, lambda v=v: choose(v)) for v in values], current=get)
        box["p"] = p
        return p

    def _wheel(self, e):
        w = self.winfo_containing(e.x_root, e.y_root)
        while w is not None:
            sf = self.scrollers.get(str(w))
            if sf:
                sf.scroll(e)
                return
            w = w.master

    # --------------------------------------------------------------- layout --
    def build(self):
        self.search_var = tk.StringVar()
        titlebar = self.frame(self)
        titlebar.pack(fill="x")
        top = self.frame(titlebar, height=50)
        top.pack(fill="x", padx=(20, 0), pady=(8, 0))
        top.pack_propagate(False)
        logo = self.label(top, "Deals", font=self.f_logo, cursor="hand2")
        logo.pack(side="left")
        star = self.label(top, "*", "accent", font=self.f_logo, cursor="hand2")
        star.pack(side="left", anchor="n", padx=(2, 0), pady=(2, 0))
        for w in (logo, star):
            w.bind("<Button-1>", lambda e: self.show_home())
        tabsrow = self.frame(self)
        tabsrow.pack(fill="x", padx=20, pady=(4, 8))
        tabs = self.frame(tabsrow)
        tabs.pack(side="left")
        self.tab_btn = {
            "search": self.button(tabs, "Search", self.show_search_tab, font=self.f_bold, pad=(18, 6), style="solid"),
            "watch": self.button(tabs, "Watchlist", self.show_watch, font=self.f_bold, pad=(18, 6), style="ghost"),
            "daily": self.button(tabs, "Daily deals", lambda: self.show_picks("daily"), font=self.f_bold, pad=(18, 6),
                                 style="ghost"),
            "foryou": self.button(tabs, "For you", lambda: self.show_picks("foryou"), font=self.f_bold, pad=(18, 6),
                                  style="ghost"),
            "ozb": self.button(tabs, "OzBargain", lambda: self.show_picks("ozb"), font=self.f_bold, pad=(18, 6),
                               style="ghost"),
            "free": self.button(tabs, "Freebies", lambda: self.show_picks("free"), font=self.f_bold, pad=(18, 6),
                                style="ghost")}
        self.tab_btn["search"].pack(side="left", padx=(0, 4))
        self.tab_btn["watch"].pack(side="left", padx=(0, 4))
        self.tab_btn["daily"].pack(side="left", padx=(0, 4))
        self.tab_btn["foryou"].pack(side="left", padx=(0, 4))
        self.tab_btn["ozb"].pack(side="left", padx=(0, 4))
        self._tabs_holder = tabs
        self.apply_dev_tabs()                                       # Freebies is a developer-mode tab for now

        if self.wants_frameless:                                    # our own minimise / maximise / close
            wb = self.frame(top)
            wb.pack(side="right", fill="y")
            for glyph, cmd, danger in (("close", self.close_clicked, True), ("max", self.chrome.toggle_max, False),
                                       ("min", self.chrome.minimize, False)):
                self.win_button(wb, glyph, cmd, danger).pack(side="right", fill="y")
        self.theme_sw = self.reg(ui.ThemeToggle(self, top, self.dark, self.set_dark, self.tab_btn["search"].bh), "switch")
        self.theme_sw.pack(side="right", padx=(8, 14))
        menus = [
            ("Sources", [("manage sources...", lambda: StoresDialog(self)), ("test all sources", lambda: self.test_stores()),
                         ("add custom store...", lambda: self.add_store()), ("repair broken sources", self.run_repair),
                         ("update shop list", self.sync_shop_list), None,
                         ("reset built-in list", self.reset_stores)]),
            ("Settings", [("alerts...", self.open_alerts), ("daily deals digest...", self.open_digest), ("browser mode...", lambda: StoresDialog(self)),
                          ("hidden sites...", self.open_hidden), ("cashback %...", self.open_cashback),
                          ("check all sources...", self.run_health), ("weekly source check on / off", self.toggle_health),
                          ("export Watchlist report...", self.export_report),
                          ("run at startup on / off", self.toggle_autostart),
                          ("close button: quit / keep in tray", self.toggle_tray_close), None,
                          ("export data (CSV)...", self.export_data), ("back up database...", self.backup_data),
                          ("restore database...", self.restore_data), None,
                          ("colour pictures on / off", self.toggle_colour), ("coupon codes on / off", self.toggle_codes), ("light / dark", self.toggle_theme),
                          ("window style: custom / classic", self.toggle_frame)]),
            ("Help", [("how it works", lambda: messagebox.showinfo("How it works", HOW)),
                      ("fair use and privacy", lambda: messagebox.showinfo("Fair use and privacy", TERMS)),
                      ("open error log", self.open_error_log), ("run self-check", self.run_selftest),
                      ("check for updates...", self.check_updates),
                      ("about", self.open_about)]),
        ]
        for i, (name, items) in enumerate(reversed(menus)):
            Pop(self, top, name, items, pad=(11, 5), style="ghost").pack(side="right", padx=(0, 2))
        if self.wants_frameless:                                    # drag the window by its empty top area
            for w in (titlebar, top, tabsrow):
                self.chrome.drag_handle(w)

        # bars shown only on the results page
        self.bar_search = self.frame(self)
        self.button(self.bar_search, "\u2039 Home", self.show_home, pad=(12, 5), style="ghost").pack(side="left", padx=(0, 8))
        self.search_entry = self.entry(self.bar_search, self.search_var, width=10, font=self.f_big, big=True)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        self.button(self.bar_search, "Search", self.do_search, font=self.f_bold, pad=(22, 9), style="solid").pack(
            side="left", padx=(8, 0))
        self.bar_filters = self.frame(self)
        fr = self.bar_filters
        self.dropdown(fr, "sort: ", SORTS, lambda: self.sort, self.set_sort).pack(side="left", padx=(0, 10))
        self.dropdown(fr, "reviews: ", E.REVIEW_MODES, lambda: self.rev_mode, self.set_reviews).pack(side="left", padx=(0, 16))
        self.hide_sw = self.switch(fr, self.hide_acc, self.set_hide)
        self.hide_sw.pack(side="left")
        self.label(fr, "hide accessories", font=self.f_small).pack(side="left", padx=(6, 16))
        self.lim_sw = self.switch(fr, self.limited, self.set_limited)
        self.lim_sw.pack(side="left")
        self.label(fr, "limited-time only", font=self.f_small).pack(side="left", padx=(6, 16))
        self.used_sw = self.switch(fr, self.hide_used, self.set_hide_used)
        self.used_sw.pack(side="left")
        self.label(fr, "hide refurbished", font=self.f_small).pack(side="left", padx=(6, 16))
        self.group_sw = self.switch(fr, self.group, self.set_group)
        self.group_sw.pack(side="left")
        self.label(fr, "group stores", font=self.f_small).pack(side="left", padx=(6, 0))
        self.info_lbl = self.label(self, textvariable=self.info_var, role="muted", font=self.f_small)
        self.info_line = self.frame(self, "line", height=1)
        self.results_bars = [(self.bar_search, dict(fill="x", padx=16, pady=(2, 8))),
                             (self.bar_filters, dict(fill="x", padx=16, pady=(0, 8))),
                             (self.info_lbl, dict(fill="x", padx=18)),
                             (self.info_line, dict(fill="x", pady=(5, 0)))]

        bar = self.frame(self)
        bar.pack(side="bottom", fill="x", padx=18, pady=5)
        self.label(bar, textvariable=self.status_var, role="muted", font=self.f_small).pack(side="left")
        self.label(bar, textvariable=self.next_var, role="muted", font=self.f_small).pack(side="right")
        self.frame(self, "line", height=1).pack(side="bottom", fill="x")

        self.body = self.frame(self)
        self.body.pack(fill="both", expand=True)
        self.main = self.frame(self.body)
        self.main.pack(fill="both", expand=True)
        self.res = ScrollFrame(self, self.main)
        self.res.on_width = self.on_res_width
        self.watch = ScrollFrame(self, self.main)
        self.daily = ScrollFrame(self, self.main)
        self.foryou = ScrollFrame(self, self.main)
        self.ozb = ScrollFrame(self, self.main)
        self.free = ScrollFrame(self, self.main)
        self.ozb_cat = E.get_settings(E.db()).get("ozb_cat") or "All deals"
        if self.ozb_cat not in E.OZB_CAT_NAMES:
            self.ozb_cat = "All deals"
        self.ozb_page = 0
        self.picking, self.pick_cells, self._pick_cols, self.daily_shuffle = None, [], {}, None
        self.pick_sorts = {"daily": "Biggest savings", "foryou": "Newest", "ozb": "Newest", "free": "Newest"}
        self.daily_cat = E.get_settings(E.db()).get("daily_cat") or "All"
        if self.daily_cat not in E.DAILY_CAT_NAMES:
            self.daily_cat = "All"
        self.cmp = []                                                    # products chosen for side-by-side compare
        self._update_ov, self._updating = None, False
        self.scroll_until = 0.0
        self.watch_sort = E.get_settings(E.db()).get("watch_sort") or "Added"
        if self.watch_sort not in WATCH_SORTS:
            self.watch_sort = "Added"
        self.watch_folded = {int(x) for x in (E.get_settings(E.db()).get("watch_folded") or "").split(",") if x.strip().isdigit()}
        self.daily.on_width = lambda w: self.on_pick_width("daily", w)
        self.foryou.on_width = lambda w: self.on_pick_width("foryou", w)
        self.ozb.on_width = lambda w: self.on_pick_width("ozb", w)
        self.free.on_width = lambda w: self.on_pick_width("free", w)
        self.build_home()
        self.build_loading()

    def build_loading(self):
        self.loading = self.frame(self.main)
        self.load_total = 0
        box = self.frame(self.loading)
        box.place(relx=0.5, rely=0.42, anchor="center")
        self.load_spin = self.reg(ui.Spinner(self, box, 46), "redraw")
        self.load_spin.pack()
        self.load_title = self.label(box, "Searching Australian sources...", font=self.f_big, anchor="center")
        self.load_title.pack(pady=(14, 2))
        self.load_sub = self.label(box, "Starting...", "muted", font=self.f_small, anchor="center")
        self.load_sub.pack()
        self.load_bar = self.reg(ui.ProgressBar(self, box, 320), "redraw")
        self.load_bar.pack(pady=(12, 0))
        self.label(box, "Stores that keep failing are skipped, and slow ones are cut off after a few seconds.", "muted",
                   font=self.f_small, anchor="center", wraplength=360, justify="center").pack(pady=(10, 0))

    def show_loading(self, n, title="Searching Australian sources..."):
        self.load_total = n
        self.load_title.configure(text=title)
        self.res.outer.pack_forget()
        self.loading.pack(fill="both", expand=True)
        self.load_sub.configure(text=f"Checking {n} sources...")
        self.load_bar.set(0)
        self.load_spin.start()

    def hide_loading(self):
        self.load_spin.stop()
        self.loading.pack_forget()

    def on_search_progress(self, done, total):
        if self.searching and total:
            self.load_sub.configure(text=f"{done} of {total} sources checked")
            self.load_bar.set(done / total)
            self._sb_done, self._sb_total = done, total
            if self._sb_mode == "search":
                self.update_sb()

    def start_sb(self, mode, n=0):
        """The big 'still working' banner at the top of the results (first search, or the second go at slow shops)."""
        self._sb_mode, self._sb_n, self._sb_t0 = mode, n, time.time()
        if not self._sb_anim:
            self._sb_anim = True
            self.after(400, self.animate_sb)

    def end_sb(self):
        self._sb_mode = None
        try:
            if self._sb_frame is not None:
                self._sb_frame.destroy()
        except tk.TclError:
            pass
        self._sb_frame = None

    def animate_sb(self):
        if not self._sb_mode:
            self._sb_anim = False
            return
        self._sb_dots = (self._sb_dots + 1) % 4
        self.update_sb()
        self.after(400, self.animate_sb)

    def update_sb(self):
        if self._sb_frame is None or not self._sb_mode:
            return
        dots = "." * self._sb_dots
        try:
            if self._sb_mode == "search":
                self._sb_title.configure(text="Still searching" + dots)
                self._sb_sub.configure(text=f"{self._sb_done} of {self._sb_total} sources answered  -  showing the best results so far")
                self._sb_bar.set(self._sb_done / self._sb_total if self._sb_total else 0)
            else:
                self._sb_title.configure(text="Checking the slower shops" + dots)
                self._sb_sub.configure(text=f"{self._sb_n} shops were too slow the first time  -  giving them another go, "
                                            "anything new will be added here")
                self._sb_bar.set(min(0.95, (time.time() - self._sb_t0) / 40.0))
        except tk.TclError:
            pass

    def build_sb(self, parent):
        self._sb_frame = box = self.frame(parent)
        box.pack(fill="x", padx=16, pady=(14, 6))
        self._sb_title = self.label(box, "", "accent", font=self.f_page, anchor="center")
        self._sb_title.pack(fill="x")
        self._sb_sub = self.label(box, "", "muted", anchor="center")
        self._sb_sub.pack(fill="x", pady=(2, 8))
        self._sb_bar = self.reg(ui.ProgressBar(self, box, 460, 8), "redraw")
        self._sb_bar.pack()
        self.update_sb()

    def on_search_partial(self, offers, done, total, query):
        """The first good results appear while slower shops are still answering."""
        if not self.searching or self.view != "results" or query != self.query:
            return
        sig = [(o.url, o.price) for o in offers[:PAGE]]
        first = not self._stream
        self._stream = True
        self._sb_done, self._sb_total = done, total
        if self._sb_mode != "search":
            self.start_sb("search")
        self.info_var.set("Searching...")
        if sig == self._stream_sig:
            return
        now = time.time()
        if not first and now - getattr(self, "_stream_at", 0) < 4.0:     # redrawing every card is costly: at most every 4 s
            return
        self._stream_at = now
        if not first:
            try:
                if self.res.canvas.yview()[0] > 0.02:          # the person is scrolling: don't move things under them
                    return
            except tk.TclError:
                return
        self._stream_sig = sig
        self.results_all, self.shown = offers, PAGE
        self.hist = getattr(self, "hist", None) or {}
        try:
            self.prev_prices = E.last_prices(E.db(), [o.url for o in offers])
        except Exception:  # noqa: BLE001
            self.prev_prices = {}
        self.apply_group()
        if first:
            self.hide_loading()
            self.res.outer.pack(fill="both", expand=True)
        self.render_results()

    def win_button(self, parent, kind, cmd, danger=False):
        """A minimise / maximise / close button for the custom window frame (Windows' own icon font when available)."""
        fams = set(tkfont.families())
        icon = "Segoe Fluent Icons" if "Segoe Fluent Icons" in fams else ("Segoe MDL2 Assets" if "Segoe MDL2 Assets" in fams else None)
        glyphs = {"min": ("\ue921", "\u2013"), "max": ("\ue922", "\u25a1"), "close": ("\ue8bb", "\u2715")}[kind]
        lab = tk.Label(parent, text=glyphs[0] if icon else glyphs[1], font=(icon, 9) if icon else (self.f_norm[0], 11),
                       bd=0, padx=px(18), cursor="arrow")
        self.reg(lab, "text")

        def on(e):
            lab.configure(bg="#e81123" if danger else self.P["hover"], fg="#ffffff" if danger else self.P["fg"])

        def off(e):
            lab.configure(bg=self.P["bg"], fg=self.P["fg"])
        lab.bind("<Enter>", on)
        lab.bind("<Leave>", off)
        lab.bind("<Button-1>", lambda e: cmd())
        return lab

    # ------------------------------------------------------------------ tray --
    def start_tray(self):
        """The notification-area icon: shows Deals is running (also while it works or updates in the background)."""
        self.tray, self._tray_told = None, False
        self.tray_close = E.get_settings(E.db()).get("tray_close", "0") == "1"
        if sys.platform != "win32" or "--no-tray" in sys.argv:
            return
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
        try:
            self.tray = ui.Tray(self.on_tray, icon_path=os.path.join(base, "assets", "deals.ico"))
            if not self.tray.start():
                log_error("tray icon could not be created")
                self.tray = None
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())
            self.tray = None

    def on_tray(self, name):
        """Called from the tray thread."""
        if name == "force":
            self.force_quit()
        elif name == "open":
            self.q.put(self.show_window)
        elif name == "check":
            self.q.put(lambda: None if self.scanning else self.start_check())
        elif name == "quit":
            threading.Timer(8.0, self.force_quit).start()          # if a clean exit hangs, finish it off
            self.q.put(self.on_close)

    def tray_status(self, text):
        if getattr(self, "tray", None):
            self.tray.status(text)

    def show_window(self):
        try:
            if self.state() == "withdrawn":
                self.deiconify()
            if self.chrome.on:
                pending = getattr(self.chrome, "_min_pending", False)
                ctypes.windll.user32.ShowWindow(self.chrome.hwnd, 9)          # SW_RESTORE
                if not pending:
                    self.attributes("-alpha", 0.0)
                    self.chrome.fade(1.0, 150, start=0.0)
            else:
                self.state("normal")
            self.lift()
            self.focus_force()
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())

    def hide_to_tray(self):
        def go():
            self.withdraw()
            try:
                self.attributes("-alpha", 1.0)
            except tk.TclError:
                pass
            if not self._tray_told:
                self._tray_told = True
                self.tray.notify("Deals is still running", "Click the tray icon to open it again, or right-click it to quit.")
        if self.chrome.on:
            self.chrome.fade(0.0, 120, then=go)
        else:
            go()

    def toggle_tray_close(self):
        self.tray_close = not self.tray_close
        E.set_setting(E.db(), "tray_close", "1" if self.tray_close else "0")
        if self.tray_close and not getattr(self, "tray", None):
            return messagebox.showinfo("Deals", "The tray icon isn't available here, so the close button will still quit Deals.")
        messagebox.showinfo("Deals", "The close button now keeps Deals running in the tray (the small arrow by the clock), so "
                                     "alerts keep working. Right-click the icon to quit." if self.tray_close else
                            "The close button now quits Deals.")

    def exit_for_update(self):
        """Leave completely (no lingering process) so the installer can replace the files."""
        try:
            E.set_setting(E.db(), "geometry", self.geometry())
        except Exception:  # noqa: BLE001
            pass
        try:
            if getattr(self, "tray", None):
                self.tray.stop()
        except Exception:  # noqa: BLE001
            pass
        os._exit(0)

    def force_quit(self):
        """Stop Deals immediately, including any background browser, even if the window is hidden or stuck."""
        try:
            if getattr(self, "tray", None):
                self.tray.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            subprocess.Popen(["taskkill", "/F", "/T", "/PID", str(os.getpid())], creationflags=0x08000000)
            time.sleep(1.0)
        except Exception:  # noqa: BLE001
            pass
        os._exit(0)

    def close_clicked(self):
        if getattr(self, "tray_close", False) and getattr(self, "tray", None) and self.tray.ok:
            return self.hide_to_tray()
        if self.chrome.on:
            self.chrome.fade(0.0, 120, then=self.on_close)
        else:
            self.on_close()

    def toggle_frame(self):
        on = E.get_settings(E.db()).get("classic_frame", "0") != "1"
        if not messagebox.askyesno("Window style", ("Switch to the classic Windows frame? " if on else
                                   "Switch to Deals' custom rounded window? ") + "Deals will restart."):
            return
        E.set_setting(E.db(), "classic_frame", "1" if on else "0")
        self.restart_app()

    def build_home(self):
        self.home = self.frame(self.main)
        box = self.frame(self.home)
        box.place(relx=0.5, rely=0.4, anchor="center")
        self.label(box, "What are you looking for?", font=self.f_hero, anchor="center").pack()
        self.label(box, "Australian prices and live deals, in one search", "muted", anchor="center").pack(pady=(4, 22))
        row = self.frame(box)
        row.pack()
        self.home_entry = self.entry(row, self.search_var, width=40, font=self.f_big, big=True)
        self.home_entry.pack(side="left")
        self.home_entry.bind("<Return>", lambda e: self.do_search())
        self.button(row, "Search", self.do_search, font=self.f_bold, pad=(22, 9), style="solid").pack(
            side="left", padx=(8, 0))
        self.chips = self.frame(box)
        self.chips.pack(pady=(18, 0))
        self.label(box, "Name a brand to see only that brand  \u00b7  use -word to exclude", "muted",
                   font=self.f_small, anchor="center").pack(pady=(14, 0))

    def refresh_home(self):
        for w in self.chips.winfo_children():
            w.destroy()
        self.prune()
        con = E.db()
        watch = [r["keywords"] for r in con.execute("SELECT keywords FROM watchlist ORDER BY id LIMIT 5")]
        recent = [x for x in E.get_settings(con).get("recent", "").split("\n") if x][:5]
        try:
            seen = [tuple(x) for x in json.loads(E.get_settings(con).get("viewed") or "[]")][:5]
        except (ValueError, TypeError):
            seen = []
        if seen:
            row = self.frame(self.chips)
            row.pack(pady=4)
            self.label(row, "Viewed", "muted", font=self.f_small).pack(side="left", padx=(0, 8))
            for t, u in seen:
                lab = t if len(t) <= 26 else t[:25] + "\u2026"
                self.button(row, lab, lambda u=u: self.open_url(u), pad=(11, 3), font=self.f_small).pack(side="left", padx=3)
        for title, items in (("Watching", watch), ("Recent", recent)):
            if not items:
                continue
            row = self.frame(self.chips)
            row.pack(pady=4)
            self.label(row, title, "muted", font=self.f_small).pack(side="left", padx=(0, 8))
            for k in items:
                lab = k if len(k) <= 26 else k[:25] + "\u2026"
                self.button(row, lab, lambda k=k: self.quick_search(k), pad=(11, 3), font=self.f_small).pack(
                    side="left", padx=3)

    def quick_search(self, q):
        self.search_var.set(q)
        self.do_search()

    def remember_search(self, q):
        con = E.db()
        old = [x for x in E.get_settings(con).get("recent", "").split("\n") if x and x != q]
        E.set_setting(con, "recent", "\n".join([q] + old[:7]))

    def _slash(self, e):
        try:
            if e.widget.winfo_class() in ("Entry", "Text", "TEntry"):
                return None
        except Exception:  # noqa: BLE001
            pass
        self.focus_search()
        return "break"

    def focus_search(self):
        (self.home_entry if self.view == "home" else self.search_entry).focus_set()

    def _hide_views(self):
        for w, _ in self.results_bars:
            w.pack_forget()
        self.home.pack_forget()
        self.res.outer.pack_forget()
        self.watch.outer.pack_forget()
        self.daily.outer.pack_forget()
        self.foryou.outer.pack_forget()
        self.ozb.outer.pack_forget()
        self.free.outer.pack_forget()
        self.loading.pack_forget()
        self.load_spin.stop()

    def set_tabs(self, active):
        for name, b in self.tab_btn.items():
            b.style_ = "solid" if name == active else "ghost"
            b.redraw()

    def show_home(self):
        self.view = "home"
        self._hide_views()
        self.home.pack(fill="both", expand=True)
        self.set_tabs("search")
        self.refresh_home()
        self.home_entry.focus_set()

    def show_results_view(self):
        self.view = "results"
        self._hide_views()
        for w, opts in self.results_bars:
            w.pack(before=self.body, **opts)
        self.res.outer.pack(fill="both", expand=True)
        self.set_tabs("search")
        self.render_results()
        if self.searching:                               # came back to the results tab mid-search
            self.show_loading(self.load_total)

    def unseen_deals(self):
        con = E.db()
        seen = int(E.get_settings(con).get("deals_seen") or 0)
        return con.execute("SELECT COUNT(*) FROM alerts WHERE id > ?", (seen,)).fetchone()[0]

    def mark_deals_seen(self):
        con = E.db()
        top = con.execute("SELECT COALESCE(MAX(id), 0) FROM alerts").fetchone()[0]
        E.set_setting(con, "deals_seen", str(top))

    def update_badge(self):
        on = self.view != "watch" and self.unseen_deals() > 0
        b = self.tab_btn["watch"]
        if b.badge != on:
            b.badge = on
            b.redraw()

    def show_watch(self):
        self.view = "watch"
        self._hide_views()
        self.watch.outer.pack(fill="both", expand=True)
        self.set_tabs("watch")
        self.mark_deals_seen()
        self.update_badge()
        self.render_watch()

    def show_search_tab(self):
        if self.results or self.query:
            self.show_results_view()
        else:
            self.show_home()

    def initial_geometry(self, s):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        m = re.match(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$", s.get("geometry", ""))
        if m:
            w, h, x, y = map(int, m.groups())
            if 500 < w <= sw and 380 < h <= sh and -40 <= x < sw - 120 and -10 <= y < sh - 120:
                return s["geometry"]
        w, h = min(px(1180), sw - px(80)), min(px(780), sh - px(120))
        return f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2 - px(20))}"

    def style_window(self):
        if getattr(self.chrome, "on", False):
            return                                     # no Windows title bar to colour
        ui.style_titlebar(self, self.dark, self.P["bg"], self.P["fg"], self.P["border"])

    def set_icon(self):
        try:
            if HAS_PIL:
                im = ui.make_icon(256)
                self._icons = [ImageTk.PhotoImage(im), ImageTk.PhotoImage(im.resize((32, 32)))]
                self.iconphoto(True, *self._icons)
        except Exception:  # noqa: BLE001
            pass

    def on_close(self):
        try:
            E.set_setting(E.db(), "geometry", self.geometry())
        except Exception:  # noqa: BLE001
            pass
        try:
            if getattr(self, "tray", None):
                self.tray.stop()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()

    def toggle_codes(self):
        self.show_codes = not self.show_codes
        E.set_setting(E.db(), "show_codes", "1" if self.show_codes else "0")
        self.set_status("coupon codes " + ("on" if self.show_codes else "off"))
        self.render_results()

    def toggle_colour(self):
        self.colour_pics = not self.colour_pics
        E.set_setting(E.db(), "colour", "1" if self.colour_pics else "0")
        self.photo_cache = {}
        self.render_results()

    # -------------------------------------------------------------- helpers --
    def pump(self):
        """Run queued UI work, but never hog the window: stop after ~10 ms and carry on next tick."""
        end, busy = time.perf_counter() + 0.010, False
        try:
            while True:
                fn = self.q.get_nowait()
                try:
                    fn()
                except tk.TclError as ex:
                    if "invalid command name" not in str(ex) and "bad window path" not in str(ex):
                        log_error(traceback.format_exc())            # a widget that is already gone is not worth logging
                except Exception:  # noqa: BLE001
                    log_error(traceback.format_exc())
                if time.perf_counter() > end:
                    busy = True
                    break
        except queue.Empty:
            pass
        self.after(30 if busy else 200, self.pump)

    def sym(self):
        return E.get_settings(E.db())["currency"]

    def open_url(self, url):
        if url:
            webbrowser.open(url)

    def set_status(self, text):
        self.status_var.set(ui.cap(text))
        self.tray_status("" if text in ("ready", "") else text)

    def set_sort(self, v):
        self.sort = v
        E.set_setting(E.db(), "sort", v)
        self.shown = PAGE
        if v == "Best value" and self.rev_mode == "Off":
            self.rev_mode = "Show ratings"                  # value needs ratings
            E.set_setting(E.db(), "reviews", self.rev_mode)
        self.render_results()
        if v == "Best value":
            self.start_review_check()

    def open_cashback(self):
        d = Form(self, "cashback", [{"key": "pct", "label": "cashback / gift card saving %", "width": 8,
                                     "default": f"{self.cash_pct:g}" if self.cash_pct else "",
                                     "hint": "Optional. If you usually get cashback (ShopBack, Cashrewards) or buy "
                                             "discounted gift cards, cards show roughly what you'd pay after it."}]).result
        if d is None:
            return
        try:
            self.cash_pct = max(0.0, min(50.0, float(d["pct"].rstrip("%")))) if d["pct"].strip() else 0.0
        except ValueError:
            self.cash_pct = 0.0
        E.set_setting(E.db(), "cashback", f"{self.cash_pct:g}" if self.cash_pct else "")
        self.render_results()

    def toggle_autostart(self):
        on = not E.autostart_enabled()
        try:
            E.set_autostart(on, os.path.abspath(__file__))
        except OSError as ex:
            return messagebox.showerror("Deals", f"Couldn't change that: {ex}")
        if on:
            if not self.auto_minutes:
                self.set_auto("1 hour")
            messagebox.showinfo("Deals", "Deals will now start minimised when you log in and check your watchlist "
                                         "every hour, so alerts work without you opening it. Keep the window "
                                         "minimised, not closed.")
        else:
            messagebox.showinfo("Deals", "Deals will no longer start when you log in.")

    def export_data(self):
        folder = filedialog.askdirectory(title="Export data to which folder?")
        if folder:
            made = E.export_csv(folder)
            self.set_status(f"exported {len(made)} files to {folder}")

    def backup_data(self):
        dest = filedialog.asksaveasfilename(title="Back up Deals database", defaultextension=".db",
                                            initialfile="deals-backup.db")
        if dest:
            E.backup_db(dest)
            self.set_status("backup saved")

    def restore_data(self):
        src = filedialog.askopenfilename(title="Choose a Deals backup (.db)")
        if src and messagebox.askyesno("Restore", "This replaces your watchlist, history and settings with the backup. "
                                                  "Deals will restart by itself. Continue?"):
            self.set_status("restoring...")
            if E.restore_db(src):
                try:
                    E.db()                                   # upgrade an old backup now, so a problem shows here
                except Exception:  # noqa: BLE001
                    log_error(traceback.format_exc())
                    return messagebox.showerror("Deals", "The backup was restored but couldn't be opened - see Help > open error log.")
                self.restart_app()
            else:
                messagebox.showerror("Deals", "That file isn't a Deals backup.")

    def open_error_log(self):
        if os.path.exists(ERR_LOG):
            webbrowser.open("file://" + os.path.abspath(ERR_LOG).replace("\\", "/"))
        else:
            messagebox.showinfo("Deals", "No problems have been logged.")

    def set_hide_used(self, on):
        self.hide_used = bool(on)
        E.set_setting(E.db(), "hide_used", "1" if on else "0")
        self.shown = PAGE
        self.render_results()

    def set_group(self, on):
        self.group = bool(on)
        E.set_setting(E.db(), "group", "1" if on else "0")
        self.apply_group()
        self.shown = PAGE
        self.render_results()

    def apply_group(self):
        for o in self.results_all:
            o.others = []
        self.results = E.group_offers(list(self.results_all)) if self.group else list(self.results_all)

    def order(self, offers=None):
        vk = ((lambda o: (-self.deal_score(o)[0], o.price)) if self.sort == "Deal score"
              else (lambda o: E.value_score(o, self.rev_info.get(o.url))))
        return E.order_offers(self.results if offers is None else offers, self.sort, self.hide_acc, self.limited,
                              self.prev_prices, self.hide_used, vk)

    def deal_score(self, o):
        try:
            return E.deal_score(o, self.prev_prices.get(o.url), self.hist.get(o.url), self.rev_info.get(o.url),
                                getattr(self, "_typical", None))
        except Exception:  # noqa: BLE001
            return 0, "", []

    def hist_verdict(self, o):
        return E.price_verdict(o, self.hist.get(o.url))

    def card_menu(self, e, card):
        o = card.o
        m = ui.StyledMenu(self, tip_for=tip_for)
        m.add_command(label="Open page", command=lambda: self.open_url(o.url))
        if o.others:
            m.add_command(label=f"Compare {len(o.others) + 1} stores...", command=lambda: self.open_compare(o))
        m.add_command(label="Add to Watchlist", command=lambda: self.add_watch(card))
        m.add_command(label="Copy deal text", command=lambda: self.copy_deal(o))
        inc = any(x.url == o.url for x in self.cmp)
        m.add_command(label="Remove from comparison" if inc else f"Add to side-by-side comparison ({len(self.cmp)}/3)",
                      command=lambda: self.toggle_compare(o))
        if len(self.cmp) >= 2:
            m.add_command(label=f"Compare {len(self.cmp)} products now...", command=self.open_compare_products)
        if self.cmp:
            m.add_command(label="Clear comparison", command=lambda: self.cmp.clear())
        sc, lab, why = self.deal_score(o)
        if sc:
            m.add_separator()
            m.add_command(label=f"Deal score {sc} ({lab}): " + ", ".join(why), state="disabled")
        m.add_separator()
        m.add_command(label="Wrong price - report and hide this listing...", command=lambda: self.report_price(o))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def copy_price_match(self, title, cheaper, store):
        try:
            self.clipboard_clear()
            self.clipboard_append(E.price_match_text(title[:90], cheaper, store, self.sym()))
            self.toast(f"Price-match message for {store} copied - paste it into their chat or email")
        except tk.TclError:
            pass

    def toggle_compare(self, o):
        if any(x.url == o.url for x in self.cmp):
            self.cmp = [x for x in self.cmp if x.url != o.url]
            return self.toast(f"Removed - {len(self.cmp)} selected")
        if len(self.cmp) >= 3:
            return self.toast("Compare up to 3 at a time - clear one first")
        self.cmp.append(o)
        if len(self.cmp) >= 2:
            self.toast(f"{len(self.cmp)} selected", self.open_compare_products, label="Compare now")
        else:
            self.toast("Pick one more product (right-click > Add to comparison)")

    def open_compare_products(self):
        if len(self.cmp) >= 2:
            ProductCompare(self, list(self.cmp))

    def viewed(self, o):
        try:
            con = E.db()
            old = json.loads(E.get_settings(con).get("viewed") or "[]")
            old = [x for x in old if x[1] != o.url]
            E.set_setting(con, "viewed", json.dumps([[o.title[:80], o.url]] + old[:7]))
        except Exception:  # noqa: BLE001
            pass

    def copy_deal(self, o):
        sym = self.sym()
        text = f"{o.title} - {E.money(sym, o.price)} at {o.store}"
        if o.was_price and o.was_price > o.price:
            text += f" (was {E.money(sym, o.was_price)}, {100 * (o.was_price - o.price) / o.was_price:.0f}% off)"
        try:
            self.clipboard_clear()
            self.clipboard_append(f"{text}\n{o.url}")
            self.toast("Deal copied - paste it into a message")
        except tk.TclError:
            pass

    def toast(self, text, undo=None, secs=8, label="Undo"):
        """A small bar at the bottom of the window, with an optional Undo."""
        try:
            self._toast.destroy()
        except Exception:  # noqa: BLE001
            pass
        P = self.P
        box = tk.Frame(self, bg=P["fg"], padx=px(14), pady=px(8))
        tk.Label(box, text=text, bg=P["fg"], fg=P["bg"], font=self.f_small).pack(side="left")
        if undo:
            u = tk.Label(box, text="  " + label, bg=P["fg"], fg=P["bg"], font=self.f_small_b, cursor="hand2")
            u.pack(side="left")
            u.bind("<Button-1>", lambda e: (box.destroy(), undo()))
        box.place(relx=0.5, rely=1.0, anchor="s", y=-px(28))
        box.lift()
        self._toast = box

        def gone():
            try:
                box.destroy()
            except tk.TclError:
                pass
        self.after(int(secs * 1000), gone)

    def undo_hide(self, o):
        E.unhide_listing(E.db(), o.url)
        self.results_all.append(o)
        self.apply_group()
        self.set_status("listing restored")
        if self.view == "results":
            self.render_results()
        elif self.view in ("daily", "foryou", "ozb", "free"):
            self.render_picks(self.view)

    def report_price(self, o):
        d = Form(self, "report a wrong price", [
            {"key": "correct", "label": "correct price", "width": 12,
             "hint": "Optional - what the page really charges. The listing is hidden from now on and saved in "
                     "Settings > export data."}], ok_text="hide it",
                 intro=f"{o.title[:80]}\nShown as {E.money(self.sym(), o.price)} at {o.store}.").result
        if d is None:
            return
        try:
            correct = float(d["correct"].lstrip("$").replace(",", "")) if d["correct"].strip() else None
        except ValueError:
            correct = None
        E.hide_listing(E.db(), o, correct)
        self.results_all = [x for x in self.results_all if x.url != o.url]
        self.apply_group()
        self.set_status("listing hidden and reported")
        self.toast("Listing hidden", lambda: self.undo_hide(o))
        if self.view == "results":
            self.render_results()
        elif self.view in ("daily", "foryou", "ozb", "free"):
            self.render_picks(self.view)

    def star_tip(self, o):
        info = self.rev_info.get(o.url)
        if info is None:
            self.lookup_one(o)
            return "Checking reviews..."
        text = E.review_verdict(info)[1]
        return f"Reviews: {text}  (click for more)" if text else "No ratings found - click to search for reviews"

    def lookup_one(self, o):
        pend = self._rev_pend
        if o.url in pend:
            return
        pend.add(o.url)

        def work():
            try:
                info = E.review_info_for(o)
            except Exception:  # noqa: BLE001
                info = {"rating": None, "count": 0, "reddit": None, "rposts": 0, "pr": None}
            self.q.put(lambda: self.on_review(o, info))

        threading.Thread(target=work, daemon=True).start()

    def review_menu(self, e, card):
        m = ui.StyledMenu(self, tip_for=tip_for)
        text = E.review_verdict(self.rev_info.get(card.o.url))[1]
        m.add_command(label=text or "Reviews", state="disabled")
        m.add_separator()
        for label, url in E.review_links(card.o):
            m.add_command(label=label, command=lambda u=url: self.open_url(u))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def open_compare(self, o):
        CompareDialog(self, o)

    def set_reviews(self, v):
        self.rev_mode = v
        E.set_setting(E.db(), "reviews", v)
        self.shown = max(self.shown, PAGE)
        if self.view in ("daily", "foryou"):
            self.render_picks(self.view)
        else:
            self.render_results()
        if v != "Off":
            self.start_review_check()

    def review_wait(self):
        return "Checking reviews..." if self.rev_busy else "No reviews found"

    def review_line(self, o):
        if self.rev_mode == "Off":
            return None
        info = self.rev_info.get(o.url)
        if not info:
            return None
        typical = getattr(self, "_typical", None)
        return E.review_verdict(info, o.price, typical)

    def start_review_check(self):
        if self.rev_mode == "Off" or self.rev_busy:
            return
        if self.view in ("daily", "foryou", "ozb", "free"):
            offers = [o for o in self.pick_pool if self.rev_pass(o, True)][:30]
        elif self.results:
            deals, others = self.order()
            offers = [o for o in deals + others if self.rev_pass(o, True)][:min(max(self.shown, PAGE), 24)]
        else:
            return
        if not offers:
            return
        self.rev_busy = True
        self.set_status("checking product reviews...")

        def cb(o, info):
            self.q.put(lambda: self.on_review(o, info))

        def work():
            try:
                E.check_reviews(offers, cb=cb, limit=len(offers), workers=3)
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
            self.q.put(self.reviews_done)

        threading.Thread(target=work, daemon=True).start()

    def on_review(self, o, info):
        self.rev_info[o.url] = info
        line = self.review_line(o)
        for card in self.cards_by_url.get(o.url, []):
            try:
                if self.rev_mode != "Off":
                    card.set_review(line)
                else:
                    card.redraw()                                  # the star turns green / red
                    if card.tip_kind == "star":
                        card.show_tip("star")
            except tk.TclError:
                pass

    def reviews_done(self):
        self.rev_busy = False
        self.set_status("ready")
        by_rev = self.view in ("daily", "foryou") and self.pick_sorts.get(self.view) in ("Best reviews", "Highest deal score") \
            and not (self.view == "daily" and self.daily_shuffle)
        if (self.rev_mode in ("Hide poor reviews", "Only 4 stars and up") or by_rev) and self.view in ("results", "daily", "foryou"):
            self.render_picks(self.view) if self.view != "results" else self.render_results()
        else:
            for urlcards in self.cards_by_url.values():          # swap "Checking reviews..." for "No reviews found"
                for card in urlcards:
                    try:
                        if not card.review:
                            card.redraw()
                    except tk.TclError:
                        pass

    def rev_pass(self, o, unknown_ok=None):
        if self.rev_mode in ("Off", "Show ratings"):
            return True
        return E.passes_reviews(self.rev_mode, self.rev_info.get(o.url),
                                self.rev_busy if unknown_ok is None else unknown_ok)

    def set_hide(self, on):
        self.hide_acc = bool(on)
        E.set_setting(E.db(), "hide_acc", "1" if on else "0")
        self.shown = PAGE
        self.render_results()

    def set_limited(self, on):
        self.limited = bool(on)
        E.set_setting(E.db(), "limited", "1" if on else "0")
        self.shown = PAGE
        self.render_results()

    def set_auto(self, v):
        self.auto_minutes = AUTO[v]
        E.set_setting(E.db(), "auto", str(self.auto_minutes))
        self.next_at = time.time() + 2 if self.auto_minutes else None
        if not self.auto_minutes:
            self.next_var.set("")

    def on_res_width(self, width):
        cols = max(1, (width - px(16)) // (self.cw + px(12)))
        if cols != self.cols:
            self.cols = cols
            if self.view == "results" and self.results:
                if self._relayout:
                    self.after_cancel(self._relayout)
                self._relayout = self.after(150, self.render_results)

    def do_search(self, exact=False):
        q = self.search_var.get().strip()
        if E.is_url(q):
            return self.search_link(q)
        if not E.parse_keywords(q)[0]:
            return
        self.stop_picks()
        gen, cancel = self.begin_search()
        if self.view != "results":
            self.show_results_view()
        self.remember_search(q)
        con = E.db()
        cfg = E.get_settings(con)
        cfg["region"] = cfg.get("region") or self.region
        cfg["_cancel"] = cancel
        stores = E.active_stores(con, cfg["region"])
        if not stores:
            self.searching = False
            return messagebox.showinfo("search", "No sources are switched on. Open Sources > manage sources.")
        self.link_info = None
        self.fixed = None
        self.did_mean = None
        run_q = q
        if not exact:
            try:
                run_q, changes = E.correct_query(q)
                if changes:
                    self.fixed = (q, run_q)
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                run_q = q
        self.searching, self.query = True, run_q
        self._stream, self._stream_sig = False, None
        self.hidden_offers, self.show_hidden = [], False
        self.set_status(f"searching {len(stores)} sources...")
        self.show_loading(len(stores))

        def work():
            try:
                prog = lambda d, t, g=gen: self.q.put(lambda d=d, t=t: gen == self._sgen and self.on_search_progress(d, t))
                part = lambda offs, d, t, g=gen: self.q.put(
                    lambda offs=offs, d=d, t=t: gen == self._sgen and self.on_search_partial(offs, d, t, run_q))
                cfg["defer_verify"] = "1"                        # show results first; shop-page price checks run afterwards
                offers, report = E.find_offers(run_q, stores, cfg, progress=prog, partial=part)
                if gen != self._sgen:
                    return                                       # a newer search took over: drop this one
                if not offers and not exact:                    # nothing found: try a more forgiving spelling fix
                    q2, ch = E.correct_query(run_q, aggressive=True)
                    if not ch or q2 == run_q:                   # or borrow the spelling the shops' own results use
                        q2 = E.did_you_mean(run_q, getattr(report, "words", {})) or run_q
                    if q2 != run_q:
                        offers, report = E.find_offers(q2, stores, cfg, progress=prog)
                        if gen != self._sgen:
                            return
                        if offers:
                            self.fixed, self.query = (q, q2), q2
                late = getattr(report, "timed_out", 0)
                again = bool(late) and not cancel.is_set()
                if again:
                    self.q.put(lambda: gen == self._sgen and self.start_sb("second", late))
                self.q.put(lambda: gen == self._sgen and self.show_results(offers, report))
                if again and gen == self._sgen:                 # shops that missed out get a second go, in the background
                    got = E.second_pass(self.query, stores, offers, report, cfg)
                    if got and gen == self._sgen:
                        self.q.put(lambda: gen == self._sgen and self.second_pass_done(got))
                    else:
                        self.q.put(lambda: gen == self._sgen and self.end_sb())
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                self.q.put(lambda: gen == self._sgen and (self.end_sb(), self.show_results([], [])))

        threading.Thread(target=work, daemon=True).start()

    def second_pass_done(self, got):
        """The slow shops have answered: add what they found (keeping your place on the page)."""
        merged, rep, added = got
        self.end_sb()
        self.set_status("ready")
        if self.view != "results" or not added:
            return
        self._stream = True                              # makes show_results keep the scroll position
        self.show_results(merged, rep)
        self.toast(f"{added} more result{'s' if added != 1 else ''} from the slower shops")

    def begin_search(self):
        """A new search always wins: the one still running is told to stop and its late answers are ignored."""
        if self._scancel is not None:
            self._scancel.set()
        self._sgen += 1
        self._sb_mode = None
        self._scancel = threading.Event()
        self.searching = True
        self.hide_loading()
        return self._sgen, self._scancel

    def search_link(self, url):
        """Pasted product link: read it, then search every other store for the same product."""
        self.stop_picks()
        gen, cancel = self.begin_search()
        if self.view != "results":
            self.show_results_view()
        con = E.db()
        cfg = E.get_settings(con)
        cfg["region"] = cfg.get("region") or self.region
        cfg["_cancel"] = cancel
        stores = E.active_stores(con, cfg["region"])
        if not stores:
            self.searching = False
            return messagebox.showinfo("search", "No sources are switched on. Open Sources > manage sources.")
        self.searching, self.link_info, self.fixed = True, None, None
        self._stream, self._stream_sig = False, None
        self.set_status("reading that product page...")
        self.show_loading(len(stores), "Reading the product page...")

        def work():
            try:
                info = E.product_from_url(url, cfg)
            except Exception as e:  # noqa: BLE001
                msg = str(getattr(e, "kind", "") and f"{e}" or e)
                self.q.put(lambda: gen == self._sgen and self.link_failed(msg))
                return
            if gen != self._sgen:
                return
            self.q.put(lambda: gen == self._sgen and (self.set_status(f"searching {len(stores)} sources for {info['query']}..."),
                                                      self.search_var.set(info["query"])))
            try:
                prog = lambda d, t: self.q.put(lambda d=d, t=t: gen == self._sgen and self.on_search_progress(d, t))
                offers, report = E.find_offers(info["query"], stores, cfg, progress=prog)
                if gen != self._sgen:
                    return
                self.q.put(lambda: gen == self._sgen and self.load_sub.configure(
                    text="Checking which results are the exact same product..."))
                try:
                    info["different"] = E.match_link_offers(info, offers)
                    offers = [o for o in offers if o.match != "different"]
                except Exception:  # noqa: BLE001
                    log_error(traceback.format_exc())
                    info["different"] = 0
                if gen != self._sgen:
                    return
                self.q.put(lambda: gen == self._sgen and self.link_done(info, offers, report))
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                self.q.put(lambda: gen == self._sgen and self.link_done(info, [], []))

        threading.Thread(target=work, daemon=True).start()

    def link_failed(self, msg):
        self.searching = False
        self.hide_loading()
        self.set_status("ready")
        messagebox.showinfo("link", "Couldn't read a product from that link"
                            + (f" ({msg})" if msg else "") + ".\nTry typing the product name instead.")

    def link_done(self, info, offers, report):
        self.query = info["query"]
        self.link_info = info
        self.remember_search(info["query"])
        self.show_results(offers, report)

    def show_results(self, offers, report):
        self.searching = False
        if self._sb_mode == "search":
            self._sb_mode = None
        was_streaming, self._stream = self._stream, False
        keep = 0.0
        if was_streaming:
            try:
                keep = self.res.canvas.yview()[0]
            except tk.TclError:
                keep = 0.0
        self.hide_loading()
        self.results_all, self.shown = offers, PAGE
        self.show_hidden = False
        self.hidden_offers = list(getattr(report, "hidden_offers", []) or [])
        self.apply_group()
        try:
            self.hist = E.history_stats(E.db(), [o.url for o in offers[:300]])
        except Exception:  # noqa: BLE001
            self.hist = {}
        ok = sum(1 for r in report if r["raw"] > 0)
        blocked = sum(1 for r in report if r["err"] in ("blocked", "botcheck", "needsjs"))
        acc = sum(1 for o in offers if o.accessory)
        try:
            self.prev_prices = E.last_prices(E.db(), [o.url for o in offers])
        except Exception:  # noqa: BLE001
            self.prev_prices = {}
        brands = E.query_brands(self.query)
        self.info_var.set(f"{len(offers)} results from {ok}/{len(report)} sources"
                          + (f"  -  {', '.join(brands)} only" if brands else "")
                          + (f"  -  {acc} accessories {'hidden' if self.hide_acc else 'moved down'}" if acc else "")
                          + (f"  -  {getattr(report, 'junk', 0)} too-cheap listings hidden" if getattr(report, "junk", 0) else "")
                          + (f"  -  {getattr(report, 'paused', 0)} sources paused (they keep failing)" if getattr(report, "paused", 0) else "")
                          + (f"  -  {getattr(report, 'timed_out', 0)} too slow" if getattr(report, "timed_out", 0) else "")
                          + (f"  -  {blocked} blocked (see Sources)" if blocked else ""))
        self.did_mean = None
        if len(offers) < 3 and not self.fixed and not getattr(self, "link_info", None):
            try:
                sug = E.did_you_mean(self.query, getattr(report, "words", {}))
                if sug and E.norm(sug) != E.norm(self.query):
                    self.did_mean = sug
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
        if self.fixed:
            self.info_var.set(f"Showing results for \"{self.fixed[1]}\"  -  " + self.info_var.get())
        self.set_status("ready")
        if self.view == "results":
            self.res.outer.pack(fill="both", expand=True)
        self.start_price_check(offers)                   # sets the "confirming prices" banner before drawing
        self.render_results()
        if keep > 0.02:
            self.after(60, lambda: self.res.canvas.yview_moveto(keep))

    def start_price_check(self, offers):
        """Re-read prices from the shop's own product pages (JB Hi-Fi etc.) after the results are already on screen,
        then refresh the cards if anything changed - so a search never waits for it."""
        gen = self._sgen
        cfg = E.get_settings(E.db())
        todo = [o for o in offers if o.source in ("store", "staticice")][:60]
        if not todo or self._pc_busy == gen:
            return
        self._pc_busy = gen
        self._pc_base, self._pc_dots = self.info_var.get(), 0
        self.after(400, lambda: self.animate_price_check(gen))

        def work():
            fixed = 0
            try:
                fixed = E.verify_store_prices(todo, cfg=cfg, on_fix=lambda o: self.q.put(lambda: self.price_fixed(gen)))
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
            self.q.put(lambda: self.price_check_done(gen, fixed))

        threading.Thread(target=work, daemon=True).start()

    def price_fixed(self, gen):
        """One price was just corrected: redraw soon (several arriving together are drawn once), keeping the scroll position."""
        if gen != self._sgen or self.view != "results" or self._pc_redraw:
            return
        self._pc_redraw = True

        def go():
            self._pc_redraw = False
            if gen != self._sgen or self.view != "results":
                return
            try:
                keep = self.res.canvas.yview()[0]
            except tk.TclError:
                keep = 0.0
            self.render_results()
            if keep > 0.02:
                self.after(60, lambda: self.res.canvas.yview_moveto(keep))
        self.after(350, go)

    def animate_price_check(self, gen):
        """A small moving note while the shop pages are being re-read, so it's clear the app is still confirming prices."""
        if self._pc_busy != gen or gen != self._sgen:
            return
        self._pc_dots = (self._pc_dots + 1) % 4
        self.info_var.set(f"{self._pc_base}  -  confirming the latest prices at the shops{'.' * self._pc_dots}")
        try:
            if self._pc_banner is not None:
                self._pc_title.configure(text="Confirming the best prices" + "." * self._pc_dots)
        except tk.TclError:
            pass
        self.after(400, lambda: self.animate_price_check(gen))

    def price_check_done(self, gen, fixed):
        if self._pc_busy == gen:
            self._pc_busy = None
            self.info_var.set(self._pc_base)
            try:
                if self._pc_banner is not None:
                    self._pc_banner.destroy()
            except tk.TclError:
                pass
            self._pc_banner = None
        if fixed and gen == self._sgen:                 # the banner is already gone; make sure the last correction is drawn
            self.price_fixed(gen)

    def section(self, parent, text, accent):
        self.label(parent, text, "accent" if accent else "muted", font=self.f_small_b).pack(
            anchor="w", padx=16, pady=(12, 2))

    def cols_for(self, sf):
        w = sf.canvas.winfo_width()
        return max(1, (w - px(16)) // (self.cw + px(12))) if w > 100 else max(1, self.cols)

    def on_pick_width(self, kind, width):
        cols = max(1, (width - px(16)) // (self.cw + px(12)))
        if cols != self._pick_cols.get(kind):
            self._pick_cols[kind] = cols
            if self.view == kind and not self.picking:
                if getattr(self, "_pick_relayout", None):
                    self.after_cancel(self._pick_relayout)
                self._pick_relayout = self.after(150, lambda: self.render_picks(kind))

    def card_grid(self, parent, offers, sym, sf=None, feedback=None):
        cols = self.cols_for(sf) if sf is not None else max(1, self.cols)
        avail = max(self.cw + px(12), (sf or self.res).canvas.winfo_width() - px(8))
        gap = max(6.0, (avail - cols * self.cw) / (cols * 2) / ui.UI)      # logical units (pack/grid scale them)
        grid = self.frame(parent)
        grid.pack(pady=(2, 6))
        self.pick_cells, self._pick_grid = [], (cols, gap)
        for i, o in enumerate(offers):
            prev = self.prev_prices.get(o.url)
            holder = self.frame(grid) if feedback is not None else grid
            card = self.reg(Card(self, holder, o, sym, E.deal_pct(o, prev), prev), "card")
            r, c = divmod(i, cols)
            if feedback is not None:
                card.pack()
                self.feedback_row(holder, o, feedback.get(o.url))
                holder.grid(row=r, column=c, padx=gap, pady=5)
                self.pick_cells.append(holder)
            else:
                card.grid(row=r, column=c, padx=gap, pady=5)
            self.cards_by_url.setdefault(o.url, []).append(card)
            if HAS_PIL:
                key = o.image or ("page:" + o.url)
                self.thumb_targets.setdefault(key, []).append(card)
                self.thumb_pages.setdefault(key, o.url)

    def render_results(self):
        if self.view != "results":
            return
        sf = self.res
        self._watch_keys = None
        sf.clear()
        self.prune()
        self.thumb_targets = {}
        inner, sym = sf.inner, self.sym()
        self.cards_by_url = {}
        self._sb_frame = None
        if self._sb_mode:
            self.build_sb(inner)                         # big, centred, at the very top: the app is still working
        season = E.sale_season()
        if season:
            self.label(inner, season, "muted", font=self.f_small, wraplength=900, justify="left").pack(
                anchor="w", padx=16, pady=(8, 0))
        if getattr(self, "fixed", None):
            row = self.frame(inner)
            row.pack(anchor="w", padx=16, pady=(8, 0))
            self.label(row, f"Showing results for \"{self.fixed[1]}\".  ", "text", font=self.f_small_b).pack(side="left")
            self.button(row, f"Search instead for \"{self.fixed[0]}\"", self.search_exact, pad=(10, 3),
                        font=self.f_small).pack(side="left")
        if self.query and not getattr(self, "link_info", None):
            brow = self.frame(inner)
            brow.pack(anchor="w", padx=16, pady=(8, 0))
            self.button(brow, "Save this search as an alert", lambda: self.save_search_form(self.query), pad=(12, 4),
                        style="ghost", font=self.f_small).pack(side="left")
            self.button(brow, "Why these results?", self.show_search_report, pad=(12, 4),
                        style="ghost", font=self.f_small).pack(side="left", padx=(8, 0))
        if getattr(self, "did_mean", None):
            row = self.frame(inner)
            row.pack(anchor="w", padx=16, pady=(8, 0))
            self.label(row, "Did you mean  ", "text", font=self.f_small_b).pack(side="left")
            self.button(row, self.did_mean, lambda s=self.did_mean: (self.search_var.set(s), self.do_search(exact=True)),
                        pad=(10, 3), font=self.f_small).pack(side="left")
            self.label(row, "?", "text", font=self.f_small_b).pack(side="left")
        li = getattr(self, "link_info", None)
        if li:
            self.link_banner(inner, li, sym)
        deals, others = self.order()
        strong = sorted(o.price for o in self.results if o.score >= E.ALERT_MIN_SCORE and not o.accessory)
        self._typical = strong[len(strong) // 2] if len(strong) >= 4 else None
        if self.rev_mode in ("Hide poor reviews", "Only 4 stars and up"):
            n_all = len(deals) + len(others)
            deals = [o for o in deals if self.rev_pass(o)]
            others = [o for o in others if self.rev_pass(o)]
            self.rev_hidden = n_all - len(deals) - len(others)
        else:
            self.rev_hidden = 0
        self.visible_count = (len(deals), len(others))
        if not deals:
            self.label(inner, "No current deals found", font=self.f_big).pack(anchor="w", padx=16, pady=(14, 0))
            sub = ("Showing regular prices below." if others else
                   "Nothing matched this search. Some stores may be blocking us - see Sources." if self.query
                   else "Search for anything.")
            self.label(inner, sub, "muted", font=self.f_small).pack(anchor="w", padx=16, pady=(2, 6))
        self._pc_banner = None
        if self._pc_busy is not None and self._pc_busy == self._sgen:
            self._pc_banner = self.frame(inner)
            self._pc_banner.pack(fill="x", padx=16, pady=(14, 8))
            self._pc_title = self.label(self._pc_banner, "Confirming the best prices", "accent", font=self.f_page,
                                        anchor="center")
            self._pc_title.pack(fill="x")
            self.label(self._pc_banner, "Double-checking the shops' own pages for any price changes or deals",
                       "muted", anchor="center").pack(fill="x", pady=(2, 0))
        budget = self.shown
        if deals:
            self.section(inner, f"DEALS  \u00b7  {len(deals)}", True)
            self.card_grid(inner, deals[:budget], sym)
            budget -= min(len(deals), budget)
        if others and budget > 0:
            self.section(inner, f"REGULAR PRICES  \u00b7  {len(others)}", False)
            self.card_grid(inner, others[:budget], sym)
        left = len(deals) + len(others) - self.shown
        if left > 0:
            self.button(inner, f"Show more ({left} left)", self.more, pad=(16, 5)).pack(pady=12)
        self.hidden_section(inner, sym)
        if HAS_PIL:
            self.load_thumbs(list(self.thumb_targets))
            self.prune_pictures()
        if self.rev_hidden:
            self.label(inner, f"{self.rev_hidden} hidden because of their reviews", "muted", font=self.f_small).pack(
                anchor="w", padx=16, pady=(0, 8))
        if self.rev_mode != "Off" and not self.rev_busy and any(o.url not in self.rev_info for o in (deals + others)[:max(self.shown, PAGE)]):
            self.after(50, self.start_review_check)

    def hidden_groups(self):
        """Listings left out of the results, grouped by why."""
        filt = [o for o in self.results if (self.hide_acc and o.accessory) or (self.hide_used and o.used)]
        names = {"cheap": "TOO CHEAP TO BE THE PRODUCT (cases, parts...)", "site": "FROM SITES YOU HIDE",
                 "reported": "LISTINGS YOU REPORTED"}
        groups = [("FILTERED OUT BY YOUR SETTINGS (used / accessories)", filt)] if filt else []
        for key in ("cheap", "site", "reported"):
            items = [o for o, why in self.hidden_offers if why == key]
            if items:
                groups.append((names[key], items))
        return groups

    def hidden_section(self, inner, sym):
        """A quiet link at the very bottom: reveals everything the search left out, labelled by reason."""
        if getattr(self, "link_info", None):
            return
        groups = self.hidden_groups()
        n = sum(len(g[1]) for g in groups)
        if not n:
            return
        text = f"Hide the {n} hidden listings" if self.show_hidden else f"Show {n} hidden listings"
        self.button(inner, text, self.toggle_hidden, pad=(12, 4), style="ghost", font=self.f_small).pack(
            anchor="w", padx=16, pady=(14, 18))
        if self.show_hidden:
            for title, items in groups:
                self.section(inner, f"HIDDEN  \u00b7  {title}  \u00b7  {len(items)}", False)
                self.card_grid(inner, items, sym)

    def toggle_hidden(self):
        self.show_hidden = not self.show_hidden
        try:
            keep = self.res.canvas.yview()[0]
        except tk.TclError:
            keep = 0.0
        self.render_results()
        if keep > 0.02:
            self.after(60, lambda: self.res.canvas.yview_moveto(keep))

    def search_exact(self):
        if self.fixed:
            self.search_var.set(self.fixed[0])
            self.do_search(exact=True)

    def link_banner(self, parent, li, sym):
        price = li.get("price")
        cheaper = sorted((o for o in self.results_all if price and o.price < price * 0.98 and not o.accessory
                          and not o.used and o.score >= E.ALERT_MIN_SCORE), key=lambda o: o.price)
        box = self.frame(parent)
        box.pack(fill="x", padx=16, pady=(10, 2))
        title = li["title"] if len(li["title"]) < 90 else li["title"][:87] + "..."
        self.label(box, f"Your link:  {title}", "text", font=self.f_small_b, wraplength=900, justify="left").pack(anchor="w")
        same = sum(1 for o in self.results_all if o.match == "exact")
        if same or li.get("different"):
            bits = ([f"{same} confirmed as the same product by barcode or model code"] if same else []) + \
                   ([f"{li['different']} different models left out"] if li.get("different") else [])
            self.label(box, "\u2713 " + "  \u00b7  ".join(bits), "muted", font=self.f_small).pack(anchor="w")
        if price:
            self.label(box, f"{li['store']} sells it for {E.money(sym, price)}", "muted", font=self.f_small).pack(anchor="w")
            if cheaper:
                b = cheaper[0]
                self.label(box, f"\u25bc {len(cheaper)} cheaper elsewhere  -  best {E.money(sym, b.price)} at {b.store} "
                                f"(save {E.money(sym, price - b.price)}, {100 * (price - b.price) / price:.0f}% less)",
                           "accent", font=self.f_small_b, wraplength=900, justify="left").pack(anchor="w")
            else:
                self.label(box, "\u2713 Nobody we checked beats that price - your link is already a good one",
                           "accent", font=self.f_small_b).pack(anchor="w")
        else:
            self.label(box, f"Couldn't read the price on {li['store']}, so everything we found is listed below.",
                       "muted", font=self.f_small).pack(anchor="w")
        act = self.frame(box)
        act.pack(anchor="w", pady=(4, 0))
        self.button(act, "Watch this product", lambda: self.watch_link(li), pad=(12, 4), font=self.f_small).pack(side="left")
        self.button(act, "Open the page", lambda: self.open_url(li["url"]), pad=(12, 4), font=self.f_small, style="outline").pack(
            side="left", padx=(6, 0))

    def watch_link(self, li):
        try:
            added, kw = E.add_to_watchlist(E.db(), li["title"])
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())
            return
        self._watch_keys = None
        self.set_status(f"watching '{kw}'" if added else f"already watching '{kw}'")

    def more(self):
        self.shown += PAGE
        self.render_results()


    # -------------------------------------------------- daily deals / for you --
    def is_watched(self, title):
        keys = getattr(self, "_watch_keys", None)
        if keys is None:
            keys = self._watch_keys = {E.norm(r["keywords"]) for r in E.db().execute("SELECT keywords FROM watchlist")}
        kw = E.keywords_from_title(title)
        return bool(kw) and E.norm(kw) in keys

    def add_watch(self, card):
        try:
            added, kw = E.add_to_watchlist(E.db(), card.o.title)
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())
            return
        self._watch_keys = None
        card.added = True
        card.redraw()
        self.set_status(f"Added '{kw}' to your Watchlist" if added else f"'{kw}' is already on your Watchlist")

    def ago(self, secs):
        if secs is None:
            return "never"
        m = int(secs // 60)
        return "just now" if m < 2 else (f"{m} min ago" if m < 90 else f"{round(m / 60)} h ago")

    def show_picks(self, kind):
        self.view = kind
        self._hide_views()
        sf = self._sf(kind)
        sf.outer.pack(fill="both", expand=True)
        self.set_tabs(kind)
        self.update_badge()
        con = E.db()
        if kind in ("ozb", "free"):
            age = E.picks_age(con, E.ozb_kind(self._ozbname(kind)))
            stale = age is None or age > E.OZB_EVERY
        else:
            age = E.picks_age(con, kind)
            stale = age is None or age > (E.DAILY_EVERY if kind == "daily" else 12 * 3600)
        if self.picking == kind:
            sf.outer.pack_forget()
            self.show_loading(self.load_total, self.pick_title(kind))
        elif kind in ("ozb", "free"):
            if stale and not self.picking and not self.searching:
                self.refresh_ozb(kind=kind)
            else:
                self.render_picks(kind)
        elif stale and not self.picking and not self.searching and (kind == "daily" or E.interest_queries(con)):
            self.refresh_picks(kind)
        else:
            self.render_picks(kind)

    def _sf(self, kind):
        return {"daily": self.daily, "foryou": self.foryou, "ozb": self.ozb, "free": self.free}[kind]

    def apply_dev_tabs(self):
        b = self.tab_btn["free"]
        if self.dev_mode():
            if not b.winfo_manager():
                b.pack(side="left")
        else:
            b.pack_forget()
            if getattr(self, "view", "") == "free":
                self.show_home()

    def _ozbname(self, kind=None):
        k = kind or (self.view if self.view in ("ozb", "free") else "ozb")
        return "Freebies" if k == "free" else self.ozb_cat

    # ---- OzBargain tab ----
    def refresh_ozb(self, pages=None, kind=None):
        if self.picking or self.searching:
            self.cancel_running()
        kind = kind or (self.view if self.view in ("ozb", "free") else "ozb")
        name = self._ozbname(kind)
        depth = pages or E.OZB_PAGES
        self.picking = kind
        self.pick_cancel = cancel = threading.Event()
        self._sf(kind).outer.pack_forget()
        self.show_loading(depth, f"Reading {depth} pages of OzBargain {name}...")
        self.load_sub.configure(text=f"0 of {depth} pages read")
        self.set_status("reading OzBargain...")

        def prog(d, t):
            if not cancel.is_set():
                self.q.put(lambda: (self.load_sub.configure(text=f"{d} of {t} pages read"), self.load_bar.set(d / max(t, 1)))
                           if self.picking == kind else None)

        def work():
            msg = ""
            try:
                E.refresh_ozb(name, depth, progress=prog, cancel=cancel)
            except Exception as e:  # noqa: BLE001
                log_error(traceback.format_exc())
                msg = f"Couldn't read OzBargain just now ({e}). Try Refresh in a minute."
            if not cancel.is_set():
                self.q.put(lambda: self.picks_done(kind, msg))
        threading.Thread(target=work, daemon=True).start()

    def set_ozb_cat(self, v):
        self.ozb_cat, self.ozb_page = v, 0
        E.set_setting(E.db(), "ozb_cat", v)
        age = E.picks_age(E.db(), E.ozb_kind(v))
        if age is None or age > E.OZB_EVERY:
            self.refresh_ozb()
        else:
            self.stop_picks()
            self.render_picks("ozb")

    def ozb_goto(self, page):
        k = self.view if self.view in ("ozb", "free") else "ozb"
        self.ozb_page = page
        self.render_picks(k)
        self.after(30, lambda: self._sf(k).canvas.yview_moveto(0))

    def ozb_pager(self, parent, page, pages, more=None):
        row = self.frame(parent)
        row.pack(fill="x", padx=26, pady=(6, 6))
        if pages > 1:
            if page > 0:
                self.button(row, "\u2039 Prev", lambda: self.ozb_goto(page - 1), pad=(12, 4), style="ghost").pack(side="left", padx=(0, 4))
            lo = max(0, min(page - 3, pages - 7))
            for n in range(lo, min(pages, lo + 7)):
                self.button(row, str(n + 1), lambda n=n: self.ozb_goto(n), pad=(11, 4),
                            style="solid" if n == page else "ghost").pack(side="left", padx=(0, 4))
            if page < pages - 1:
                self.button(row, "Next \u203a", lambda: self.ozb_goto(page + 1), pad=(12, 4), style="ghost").pack(side="left")
        if more:
            self.button(row, more[0], more[1], pad=(14, 4), style="solid").pack(side="right")
        return row

    def shuffle_daily(self):
        self.daily_shuffle = random.randint(1, 10 ** 9)
        self.render_picks("daily")

    def set_pick_sort(self, kind, v):
        if v == "Shuffled":
            if kind == "daily":
                return self.shuffle_daily()
            v = "Newest"
        self.pick_sorts[kind] = v
        if kind in ("ozb", "free"):
            self.ozb_page = 0
        if kind == "daily":
            self.daily_shuffle = None
        self.render_picks(kind)

    def sort_picks(self, offers, kind, con):
        """Order Daily deals / For you by the chosen sort (or a random mix after Shuffle)."""
        try:
            self.hist = E.history_stats(con, [o.url for o in offers])
        except Exception:  # noqa: BLE001
            self.hist = {}
        self.prev_prices = {}
        if kind == "daily" and self.daily_shuffle and len(offers) > 1:
            rnd = random.Random(self.daily_shuffle)
            offers.sort(key=lambda o: rnd.random() ** (1.0 / (1 + max(0.0, (o.was_price or 0) - o.price) ** 0.5)), reverse=True)
            return
        mode = self.pick_sorts.get(kind, "Newest")
        save = lambda o: max(0.0, (o.was_price or o.ref_price or 0) - o.price)
        pctoff = lambda o: save(o) / (o.was_price or o.ref_price or 1)
        if mode == "Most votes":
            offers.sort(key=lambda o: -(o.votes or 0))
        elif mode == "Biggest savings":
            offers.sort(key=lambda o: -save(o))
        elif mode == "Biggest % off":
            offers.sort(key=lambda o: -pctoff(o))
        elif mode == "Highest deal score":
            offers.sort(key=lambda o: (-self.deal_score(o)[0], -save(o)))
        elif mode == "Best reviews":
            def rk(o):
                r = E.review_rating(self.rev_info.get(o.url))
                return (r is None, -(r or 0), -save(o))
            offers.sort(key=rk)
        elif mode == "Price: high to low":
            offers.sort(key=lambda o: -o.price)
        elif mode == "Price: low to high":
            offers.sort(key=lambda o: o.price)

    def stop_picks(self):
        """A new search takes priority over a Daily deals / For you scan that is still running in the background."""
        if self.picking:
            try:
                self.pick_cancel.set()
            except AttributeError:
                pass
            self.picking = None
            self.hide_loading()

    def set_daily_cat(self, v):
        """Pick a Daily deals category. It steers the search itself (not just the list): with few saved deals in that
        category it goes off and looks for them straight away."""
        self.daily_cat = v
        E.set_setting(E.db(), "daily_cat", v)
        self.daily_shuffle = None
        have = len(E.pick_offers(E.db(), "daily", category=v))
        if v != "All" and have < 6:
            self.refresh_picks("daily")
        else:
            self.stop_picks()
            self.render_picks("daily")

    def pick_title(self, kind):
        if kind in ("ozb", "free"):
            return f"Reading OzBargain {self._ozbname(kind)}..."
        if kind == "daily" and getattr(self, "daily_cat", "All") != "All":
            return f"Finding the best {self.daily_cat} deals..."
        return ("Finding today's biggest discounts..." if kind == "daily" else "Looking for deals you might like...")

    def cancel_running(self):
        """The latest thing the person asks for wins: stop a running Daily deals / For you scan or search."""
        self.stop_picks()
        if self.searching:
            if self._scancel is not None:
                self._scancel.set()
            self._sgen += 1
            self.searching, self._stream = False, False
            self.hide_loading()

    def refresh_picks(self, kind):
        if self.picking or self.searching:
            self.cancel_running()
        if kind == "daily":
            self.daily_shuffle = None
        con = E.db()
        cfg = E.get_settings(con)
        stores = E.active_stores(con, cfg.get("region") or self.region)
        if not stores:
            return messagebox.showinfo("Deals", "No sources are switched on. Open Sources > manage sources.")
        self.picking = kind
        cat = self.daily_cat
        self.pick_cancel = cancel = threading.Event()
        sf = self.daily if kind == "daily" else self.foryou
        sf.outer.pack_forget()
        self.show_loading(len(stores), self.pick_title(kind))
        self.set_status("looking for deals...")

        def prog(d, t):
            if not cancel.is_set():
                self.q.put(lambda: self.on_pick_progress(d, t))

        def work():
            msg = ""
            try:
                if kind == "daily":
                    E.refresh_daily(stores, cfg, progress=prog, cancel=cancel, category=cat)
                else:
                    _, msg = E.refresh_foryou(stores, cfg, progress=prog, cancel=cancel)
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
            if not cancel.is_set():           # a new search took over: nothing left to finish here
                self.q.put(lambda: self.picks_done(kind, msg))

        threading.Thread(target=work, daemon=True).start()

    def on_pick_progress(self, done, total):
        if self.picking and total:
            self.load_sub.configure(text=f"{done} of {total} checks done")
            self.load_bar.set(done / total)

    def picks_done(self, kind, msg=""):
        self.picking = None
        self.pick_msg = msg
        self.set_status("ready")
        if self.view == kind:
            self.hide_loading()
            self._sf(kind).outer.pack(fill="both", expand=True)
            self.render_picks(kind)

    def render_picks(self, kind):
        if self.view != kind or self.picking == kind:
            return
        sf = self._sf(kind)
        self._watch_keys = None
        sf.clear()
        self.prune()
        self.thumb_targets, self.cards_by_url, self._typical = {}, {}, None
        inner, sym, con = sf.inner, self.sym(), E.db()
        if kind in ("ozb", "free"):
            return self.render_ozb(sf, inner, sym, con, kind)
        offers = E.pick_offers(con, kind, category=self.daily_cat if kind == "daily" else "All")
        self.sort_picks(offers, kind, con)
        self.pick_pool = list(offers[:80 if kind == "daily" else 60])
        self.rev_hidden = 0
        if self.rev_mode in ("Hide poor reviews", "Only 4 stars and up"):
            before = len(offers)
            offers = [o for o in offers if self.rev_pass(o)]
            self.rev_hidden = before - len(offers)
        if kind == "daily":
            offers = offers[:48]
        hdr = self.frame(inner)
        hdr.pack(fill="x", padx=26, pady=(18, 2))
        title = "Daily deals" if kind == "daily" else "For you"
        self.label(hdr, title, font=self.f_page).pack(side="left")
        self.button(hdr, "Refresh" if kind == "daily" else "Find more", lambda: self.refresh_picks(kind),
                    pad=(14, 5)).pack(side="right")
        if kind == "daily":
            self.dropdown(hdr, "category: ", E.DAILY_CAT_NAMES, lambda: self.daily_cat, self.set_daily_cat).pack(side="left", padx=(18, 0))
            self.button(hdr, "Shuffle", self.shuffle_daily, pad=(14, 5), style="solid").pack(side="right", padx=(0, 8))
        else:
            self.button(hdr, "Reset recommended", self.reset_foryou, pad=(14, 5)).pack(side="right", padx=(0, 8))
        self.dropdown(hdr, "reviews: ", E.REVIEW_MODES, lambda: self.rev_mode, self.set_reviews).pack(side="right", padx=(0, 10))
        self.dropdown(hdr, "sort: ", PICK_SORTS,
                      lambda k=kind: "Shuffled" if (k == "daily" and self.daily_shuffle) else self.pick_sorts.get(k, "Newest"),
                      lambda v, k=kind: self.set_pick_sort(k, v)).pack(side="right", padx=(0, 10))
        age = E.picks_age(con, kind)
        if kind == "daily":
            sub = (f"Big-ticket items (over {sym}{E.DAILY_MIN_PRICE:.0f}) that are at least {E.DAILY_MIN_PCT:.0f}% off, "
                   f"sorted as you choose. Updated {self.ago(age)}.")
            if self.daily_cat != "All":
                sub = (f"{self.daily_cat} deals at least {E.DAILY_MIN_PCT:.0f}% off. Refresh searches this category only. "
                       f"Updated {self.ago(age)}.")
        else:
            sub = ("Discounted items similar to what you follow. Tap Interested or Not interested and the "
                   f"suggestions get better each time you Find more. Updated {self.ago(age)}.")
            if E.foryou_random(con):
                sub = ("Showing random popular deals - recommendations were reset. Press Interested on something, or add an "
                       f"item to your Watchlist, and they'll start matching you again. Updated {self.ago(age)}.")
        self.label(inner, sub, "muted", font=self.f_small, wraplength=760, justify="left").pack(anchor="w", padx=26, pady=(0, 6))
        if not offers:
            note = getattr(self, "pick_msg", "") or ("Nothing found today. Try Refresh later." if kind == "daily"
                                                      else "No suggestions yet. Press Find more.")
            self.label(inner, note, font=self.f_big).pack(anchor="w", padx=26, pady=(14, 0))
        else:
            fb = {r["url"]: r["verdict"] for r in con.execute("SELECT url, verdict FROM feedback")} if kind == "foryou" else None
            self.card_grid(inner, offers, sym, sf=sf, feedback=fb)
        if HAS_PIL:
            self.load_thumbs(list(self.thumb_targets))
        if self.rev_hidden:
            self.label(inner, f"{self.rev_hidden} hidden because of their reviews", "muted", font=self.f_small).pack(
                anchor="w", padx=26, pady=(0, 8))
        if self.rev_mode != "Off" and not self.rev_busy and any(o.url not in self.rev_info for o in self.pick_pool):
            self.after(50, self.start_review_check)

    def render_ozb(self, sf, inner, sym, con, kind="ozb"):
        free = kind == "free"
        name = self._ozbname(kind)
        offers = E.pick_offers(con, E.ozb_kind(name), limit=2000)
        self.sort_picks(offers, kind, con)
        self.pick_pool = []
        meta = E.ozb_meta(con, name)
        total = len(offers)
        pages = max(1, -(-total // E.OZB_SHOW))
        self.ozb_page = max(0, min(self.ozb_page, pages - 1))
        page = self.ozb_page
        depth = int(meta.get("pages") or E.OZB_PAGES)
        hdr = self.frame(inner)
        hdr.pack(fill="x", padx=26, pady=(18, 2))
        self.label(hdr, "Freebies" if free else "OzBargain", font=self.f_page).pack(side="left")
        if not free:
            self.dropdown(hdr, "category: ", E.OZB_CAT_NAMES, lambda: self.ozb_cat, self.set_ozb_cat).pack(side="left", padx=(18, 0))
        self.button(hdr, "Refresh", lambda: self.refresh_ozb(kind=kind), pad=(14, 5)).pack(side="right")
        self.dropdown(hdr, "sort: ", OZB_SORTS, lambda: self.pick_sorts.get(kind, "Newest"),
                      lambda v: self.set_pick_sort(kind, v)).pack(side="right", padx=(0, 10))
        age = E.picks_age(con, E.ozb_kind(name))
        if free:
            sub = (f"Developer preview. Free outright from the first {depth} pages of OzBargain: {total} found. Anything that needs "
                   f"a purchase, gift card, membership tier, trial or postage is left out. Check the deal page before you go - "
                   f"some are local or limited. Updated {self.ago(age)}"
                   + (f"  (source: {meta['src']})" if meta.get("src") else "") + ".")
        else:
            sub = (f"Live OzBargain deals from the first {depth} pages of {name}: {total} that state a price "
                   f"(deals like '20% off sitewide' have no item price, so they aren't shown). Updated {self.ago(age)}.")
        self.label(inner, sub, "muted", font=self.f_small, wraplength=760, justify="left").pack(anchor="w", padx=26, pady=(0, 4))
        more = None
        if meta.get("full") and depth < E.OZB_MAX_PAGES:
            nxt = min(E.OZB_MAX_PAGES, depth + E.OZB_STEP)
            more = (f"Load pages {depth + 1}-{nxt}", lambda n=nxt: self.refresh_ozb(n, kind=kind))
        if not offers:
            note = getattr(self, "pick_msg", "") or ("No free deals found right now. Press Refresh later." if free
                                                     else "Nothing came back. Press Refresh.")
            self.label(inner, note, font=self.f_big).pack(anchor="w", padx=26, pady=(14, 0))
            self.pick_msg = ""
            return
        shown = offers[page * E.OZB_SHOW:(page + 1) * E.OZB_SHOW]
        self.ozb_pager(inner, page, pages, more)
        self.card_grid(inner, shown, sym, sf=sf)
        if HAS_PIL:
            self.load_thumbs(list(self.thumb_targets))
        self.label(inner, f"Showing {page * E.OZB_SHOW + 1}-{page * E.OZB_SHOW + len(shown)} of {total}", "muted",
                   font=self.f_small).pack(anchor="w", padx=26, pady=(8, 0))
        self.ozb_pager(inner, page, pages, more)

    def reset_foryou(self):
        if not messagebox.askyesno("Reset recommended", "This clears everything For you has learned (your Interested / Not "
                                   "interested choices and the current suggestions). You'll get random popular suggestions "
                                   "until you press Interested on something or add a new item to your Watchlist. Continue?"):
            return
        E.reset_foryou(E.db())
        self.pick_msg = ""
        self.set_status("recommendations reset")
        self.refresh_picks("foryou")

    def feedback_row(self, holder, o, verdict):
        row = self.frame(holder)
        row.pack(fill="x", pady=(2, 0))
        if verdict == "yes":
            self.label(row, "\u2713 Interested - we'll find more like this", "accent", font=self.f_small_b).pack(anchor="w", padx=px(4))
            return
        self.button(row, "Interested", lambda: self.give_feedback(o, "yes", row, holder), pad=(12, 4), style="solid").pack(
            side="left", padx=(0, 6))
        self.button(row, "Not interested", lambda: self.give_feedback(o, "no", row, holder), pad=(12, 4),
                    style="ghost").pack(side="left")

    def give_feedback(self, o, verdict, row, holder=None):
        removed = set(E.set_feedback(E.db(), o.url, verdict, o.title))
        try:
            self.toast(E.feedback_note(o.title, verdict))        # say what was learned, so the click visibly counts
        except Exception:  # noqa: BLE001
            pass
        holder = holder or getattr(row, "master", None)
        gone = [h for h in list(self.pick_cells) if h is holder or any(
            isinstance(getattr(w, "o", None), E.Offer) and w.o.url in removed for w in h.winfo_children())]
        for h in gone:
            if h in self.pick_cells:
                self.pick_cells.remove(h)
            h.destroy()
        if gone:
            cols, gap = self._pick_grid
            for i, h in enumerate(self.pick_cells):
                r, c = divmod(i, cols)
                h.grid(row=r, column=c, padx=gap, pady=5)
        if verdict == "yes":
            self.more_like(o.title)

    def more_like(self, title):
        """After Interested: go and look for similar discounted things right away (one at a time, in the background)."""
        self._ml_pending.append(title)
        if self._ml_busy or self.picking or self.searching:
            return
        self._ml_busy = True
        con = E.db()
        cfg = E.get_settings(con)
        stores = E.active_stores(con, cfg.get("region") or self.region)
        titles, self._ml_pending = self._ml_pending[-2:], []

        def work():
            n = 0
            try:
                for t in titles:
                    n += E.more_like(t, stores, cfg)
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())

            def finish():
                self._ml_busy = False
                if n:
                    self.set_status(f"found {n} more like that")
                    if self.view == "foryou" and not self.picking and not self.searching:
                        try:
                            keep = self.foryou.canvas.yview()[0]
                        except tk.TclError:
                            keep = 0.0
                        self.render_picks("foryou")
                        self.after(60, lambda: self.foryou.canvas.yview_moveto(keep))
                        self.toast(f"Found {n} more like that - they're at the top")
                if self._ml_pending and not self.picking and not self.searching:
                    self.more_like(self._ml_pending.pop())
            self.q.put(finish)
        threading.Thread(target=work, daemon=True).start()

    # ----------------------------------------------------------- thumbnails --
    def load_thumbs(self, urls):
        for u in urls:
            if u in self.pil_cache:
                self.attach_thumb(u)
            elif u not in self.thumb_pending and self.thumb_fail.get(u, 0) < 3:
                self.thumb_pending.add(u)
                self.pool.submit(self._fetch_thumb, u, self.thumb_pages.get(u))

    def _load_image(self, url, page):
        """Download and prepare one picture. Tries with the shop as referrer (many image hosts insist on it), then without,
        then the real picture behind an image-resizer link."""
        heads = []
        if page:
            p = E.urlparse(page)
            heads.append({"User-Agent": E.UA, "Referer": f"{p.scheme}://{p.netloc}/"})
        heads.append({"User-Agent": E.UA})
        heads.append({"User-Agent": E.UA_ALT})
        why = []
        for u in [url] + E.image_alternatives(url):
            for h in heads:
                h["Accept"] = "image/webp,image/jpeg,image/png,image/*;q=0.8,*/*;q=0.5"
                try:
                    r = E.requests.get(u, headers=h, timeout=(5, 10))
                    if r.status_code != 200 or len(r.content) < 200:
                        why.append(f"HTTP {r.status_code}, {len(r.content)} bytes")
                        continue
                    im = Image.open(io.BytesIO(r.content))
                    try:                                    # JPEGs decode at reduced size: far less CPU than full resolution
                        im.draft("RGB", (self.iw * 2, self.ih * 2))
                    except Exception:  # noqa: BLE001
                        pass
                    if min(im.size) < 57:                   # a tracking pixel or icon, not a product photo
                        why.append("too small (placeholder?)")
                        continue
                    return self._prepare(im)
                except Exception as e:  # noqa: BLE001
                    why.append(f"{type(e).__name__}: {str(e)[:60]}")
                    continue
        self._note_image_failure(url, why)
        return None

    def _note_image_failure(self, url, why):
        """Keep the last few picture failures in image_check.log (Help > open error log folder) so they can be diagnosed."""
        try:
            self._img_fail = (getattr(self, "_img_fail", []) + [f"{url[:150]}  ->  {', '.join(dict.fromkeys(why))[:200]}"])[-40:]
            with open(os.path.join(DATA_HOME, "image_check.log"), "w", encoding="utf-8") as f:
                f.write("Pictures that couldn't be loaded (newest last):\n" + "\n".join(self._img_fail))
        except OSError:
            pass

    def prune_pictures(self, extra=150):
        """Every picture of every search used to be kept for the whole session (tens of MB after a day of searching).
        Keep the ones on screen plus the most recent few, so going back to a search is still instant."""
        try:
            keep = set(self.thumb_targets)
            for cache, keyof in ((self.pil_cache, lambda k: k), (self.photo_cache, lambda k: k[0])):
                over = len(cache) - (len(keep) * (1 if cache is self.pil_cache else 2) + extra)
                if over <= 0:
                    continue
                for k in list(cache):                    # dicts keep insertion order: oldest first
                    if over <= 0:
                        break
                    if keyof(k) not in keep:
                        del cache[k]
                        over -= 1
            if len(self.thumb_pages) > 2000:
                self.thumb_pages = {u: p for u, p in list(self.thumb_pages.items())[-1000:]}
            if len(self.thumb_fail) > 2000:
                self.thumb_fail = {}
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())

    def _prepare(self, im):
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            im = bg
        im = im.convert("RGB")
        iw, ih = self.iw, self.ih
        im.thumbnail((iw, ih), getattr(Image, "Resampling", Image).LANCZOS)
        tile = Image.new("RGB", (iw, ih), (255, 255, 255))
        tile.paste(im, ((iw - im.width) // 2, (ih - im.height) // 2))
        mask = self._mask_cache.get((iw, ih))            # the rounded-corner mask is the same for every picture: make it once
        if mask is None:
            S = 4
            big = Image.new("L", (iw * S, ih * S), 0)
            try:
                ImageDraw.Draw(big).rounded_rectangle((0, 0, iw * S - 1, ih * S - 1), radius=px(10) * S, fill=255)
            except AttributeError:                   # very old Pillow: square corners
                big.paste(255, (0, 0, iw * S, ih * S))
            mask = self._mask_cache[(iw, ih)] = big.resize((iw, ih), getattr(Image, "Resampling", Image).LANCZOS)
        return tile, mask

    def _fetch_thumb(self, key, page=None):
        """key is a picture address, or 'page:<product page>' when the card had no picture of its own."""
        got = None
        try:
            if not key.startswith("page:"):
                got = self._load_image(key, page)
            if got is None and page:                    # broken or blocked picture: use the product page's own main photo
                alt = E.page_image(page)
                if alt and alt != key:
                    got = self._load_image(alt, page)
        except Exception:  # noqa: BLE001
            got = None
        if got is not None:
            self.pil_cache[key] = got
            self.q.put(lambda: self.attach_thumb(key))
        else:
            self.thumb_fail[key] = self.thumb_fail.get(key, 0) + 1
        self.thumb_pending.discard(key)

    def photo_for(self, u):
        key = (u, self.colour_pics, self.dark)
        if key not in self.photo_cache:
            tile, mask = self.pil_cache[u]
            img = tile if self.colour_pics else tile.convert("L").convert("RGB")
            out = Image.composite(img, Image.new("RGB", img.size, ui.rgb(self.P["bg"])), mask)
            self.photo_cache[key] = ImageTk.PhotoImage(out)
        return self.photo_cache[key]

    def attach_thumb(self, u):
        if u not in self.pil_cache:
            return
        photo = self.photo_for(u)
        for card in self.thumb_targets.get(u, []):
            try:
                card.set_photo(photo)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ side panel --
    def render_watch(self):
        if self.view != "watch":
            return
        sf = self.watch
        sf.clear()
        self.prune()
        inner, sym, con = sf.inner, self.sym(), E.db()
        items = self.sorted_items(con, con.execute("SELECT * FROM watchlist ORDER BY id").fetchall())
        hdr = self.frame(inner)
        hdr.pack(fill="x", padx=26, pady=(18, 2))
        self.label(hdr, "Watchlist", font=self.f_page).pack(side="left")
        self.button(hdr, "+ Add item", self.add_item, font=self.f_bold, pad=(16, 6), style="solid").pack(side="right")
        self.button(hdr, "Import list", self.import_list, pad=(14, 5), style="ghost").pack(side="right", padx=(0, 8))
        self.dropdown(hdr, "sort: ", WATCH_SORTS, lambda: self.watch_sort, self.set_watch_sort).pack(side="right", padx=(0, 8))
        self.dropdown(hdr, "auto: ", list(AUTO),
                      lambda: next((k for k, v in AUTO.items() if v == self.auto_minutes), "Off"),
                      self.set_auto).pack(side="right", padx=(0, 8))
        self.button(hdr, "Check now", self.start_check, pad=(14, 5)).pack(side="right", padx=(0, 8))
        all_folded = bool(items) and all(r["id"] in self.watch_folded for r in items)
        if items:
            self.button(hdr, "Expand all" if all_folded else "Collapse all",
                        lambda: self.fold_watch([r["id"] for r in items], not all_folded),
                        pad=(14, 5), style="ghost").pack(side="right", padx=(0, 8))
        last = con.execute("SELECT MAX(checked_at) FROM watchlist").fetchone()[0]
        self.label(inner, f"Last checked {fmt_time(last)}" if last else "Not checked yet", "muted",
                   font=self.f_small).pack(anchor="w", padx=26, pady=(0, 6))
        self.watch_prog = None
        if self.scanning:
            strip = self.frame(inner)
            strip.pack(fill="x", padx=26, pady=(2, 8))
            spin = self.reg(ui.Spinner(self, strip, 22), "redraw")
            spin.pack(side="left")
            spin.start()
            txt = self.label(strip, getattr(self, "check_text", "Checking your watchlist..."), font=self.f_small)
            txt.pack(side="left", padx=10)
            bar = self.reg(ui.ProgressBar(self, strip, 200), "redraw")
            bar.pack(side="left")
            bar.set(getattr(self, "check_frac", 0.0))
            self.watch_prog = (txt, bar)
        if not items:
            self.label(inner, "Nothing on your watchlist yet", font=self.f_big).pack(anchor="w", padx=26, pady=(26, 2))
            self.label(inner, "Add an item and you'll be alerted when it drops in price, hits your target, "
                              "or appears as a discounted OzBargain deal.", "muted", wraplength=520,
                       justify="left").pack(anchor="w", padx=26)
        last_folder = object()
        grouped = any((r["folder"] or "").strip() for r in items)
        for r in items:
            fol = (r["folder"] or "").strip()
            if grouped and fol != last_folder:
                last_folder = fol
                self.label(inner, (fol or "Unfiled").upper(), "muted", font=self.f_small_b).pack(anchor="w", padx=26, pady=(16, 0))
            self.watch_row(inner, r, sym, con)

        sh = self.frame(inner)
        sh.pack(fill="x", padx=26, pady=(26, 2))
        self.label(sh, "Saved searches", font=self.f_big).pack(side="left")
        self.button(sh, "+ Add", lambda: self.save_search_form(""), pad=(10, 3), style="ghost", font=self.f_small).pack(side="right")
        saved = con.execute("SELECT * FROM saved_searches ORDER BY id").fetchall()
        if not saved:
            self.label(inner, "Get alerted when anything new matches a search - e.g. router under $150 with 4 stars and up. "
                              "Use Save search on the results page.", "muted", font=self.f_small, wraplength=700,
                       justify="left").pack(anchor="w", padx=26, pady=(2, 6))
        for ss in saved:
            line = self.frame(inner)
            line.pack(fill="x", padx=26, pady=3)
            crit = ([f"under {E.money(sym, ss['max_price'])}"] if ss["max_price"] else []) + (
                [f"{ss['min_rating']:g}\u2605 and up"] if ss["min_rating"] else []) + (
                ["real discounts only"] if ss["deals_only"] else ["any price drop or listing"])
            self.label(line, ss["query"], font=self.f_bold).pack(side="left")
            self.label(line, "   " + "  \u00b7  ".join(crit), "muted", font=self.f_small).pack(side="left")
            self.button(line, "Remove", lambda i=ss["id"]: self.remove_saved(i), pad=(12, 3), style="ghost",
                        font=self.f_small).pack(side="right")

        head = self.frame(inner)
        head.pack(fill="x", padx=26, pady=(26, 2))
        self.label(head, "Recent deals", font=self.f_big).pack(side="left")
        self.button(head, "Clear", self.clear_deals, pad=(10, 3), style="ghost", font=self.f_small).pack(side="right")
        deals = con.execute("SELECT * FROM alerts ORDER BY sent_at DESC LIMIT 15").fetchall()
        if not deals:
            self.label(inner, "None yet - deals appear here when a check finds one.", "muted",
                       font=self.f_small).pack(anchor="w", padx=26, pady=(2, 20))
        for r in deals:
            self.frame(inner, "line", height=1).pack(fill="x", padx=26, pady=(8, 0))
            row = self.frame(inner)
            row.pack(fill="x", padx=26, pady=8)
            price = self.label(row, E.money(sym, r["price"]), "accent", font=self.f_big, width=10, anchor="nw")
            price.pack(side="left", anchor="n")
            mid = self.frame(row)
            mid.pack(side="left", fill="x", expand=True)
            t1 = self.label(mid, r["title"], font=self.f_bold, wraplength=560, justify="left")
            t1.pack(anchor="w")
            t2 = self.label(mid, f"{r['store']}  \u00b7  {fmt_time(r['sent_at'])}", "muted", font=self.f_small)
            t2.pack(anchor="w")
            t3 = self.label(mid, r["reasons"] or "", "accent", font=self.f_small, wraplength=560, justify="left")
            t3.pack(anchor="w")
            for w in (row, price, mid, t1, t2, t3):
                w.bind("<Button-1>", lambda e, u=r["url"]: self.open_url(u))
                w.configure(cursor="hand2")

    def mini_change(self, parent, prev, now, sym):
        """Tiny graph of just the move since the previous check: green line down = cheaper, red line up = dearer."""
        P = self.P
        col = P["accent"] if now < prev - 0.005 else P["alert"] if now > prev + 0.005 else P["muted"]
        w, h, pad = px(46), px(22), px(5)
        cv = self.reg(tk.Canvas(parent, width=w, height=h, bd=0, highlightthickness=0), "canvas")
        cv.pack(side="left", padx=(14, 6))
        y1, y2 = (h / 2, h / 2) if now == prev else ((pad, h - pad) if now < prev else (h - pad, pad))
        cv.create_line(pad, y1, w - pad, y2, fill=col, width=2, capstyle="round")
        r = px(2)
        cv.create_oval(pad - r, y1 - r, pad + r, y1 + r, fill=P["bg"], outline=col)
        cv.create_oval(w - pad - r, y2 - r, w - pad + r, y2 + r, fill=col, outline=col)
        if abs(now - prev) < 0.005:
            txt = "no change"
        else:
            pct = 100 * abs(now - prev) / prev if prev else 0
            sign = "\u25bc" if now < prev else "\u25b2"
            txt = f"{sign} {E.money(sym, abs(now - prev))} ({pct:.0f}%)"
        self.label(parent, txt, "accent" if col == P["accent"] else "alert" if col == P["alert"] else "muted",
                   font=self.f_small).pack(side="left")

    def fold_watch(self, ids, fold, render=True):
        for i in ids:
            (self.watch_folded.add if fold else self.watch_folded.discard)(i)
        E.set_setting(E.db(), "watch_folded", ",".join(str(i) for i in sorted(self.watch_folded)))
        if render:
            self.render_watch()

    def sorted_items(self, con, items):
        mode = self.watch_sort
        items = list(items)
        if mode == "Closest to target":
            gap = lambda r: ((r["best_price"] - r["max_price"]) / r["max_price"]
                             if r["max_price"] and r["best_price"] is not None else 9e9)
            items.sort(key=gap)
        elif mode == "Biggest drop":
            def drop(r):
                ps = [h["price"] for h in E.price_history(con, r["id"])]
                return -(100 * (ps[0] - ps[-1]) / ps[0]) if len(ps) > 1 and ps[0] else 0
            items.sort(key=drop)
        elif mode == "Last checked":
            items.sort(key=lambda r: -(r["checked_at"] or 0))
        elif mode == "Name":
            items.sort(key=lambda r: r["keywords"].lower())
        items.sort(key=lambda r: ((r["folder"] or "").strip() == "", (r["folder"] or "").strip().lower()))   # folders together
        return items

    def set_watch_sort(self, v):
        self.watch_sort = v
        E.set_setting(E.db(), "watch_sort", v)
        self.render_watch()

    def import_list(self):
        d = TextDialog(self, "import list", "One product per line: a name (like  sony wh-1000xm5) or a product link. "
                       "Links are read and added by product, not by store.").result
        if not d:
            return
        lines = [x for x in d.splitlines() if x.strip()]
        self.set_status(f"importing {len(lines)} item(s)...")
        cfg = E.get_settings(E.db())

        def work():
            try:
                res = E.import_items(E.db(), lines, cfg)
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                res = (0, 0, ["import crashed - see the error log"])
            self.q.put(lambda: self.import_done(res))
        threading.Thread(target=work, daemon=True).start()

    def import_done(self, res):
        added, dup, failed = res
        self.set_status("ready")
        self.render_watch()
        msg = f"Added {added} item(s)" + (f", {dup} already on your list" if dup else "")
        self.toast(msg)
        if failed:
            messagebox.showinfo("import list", "These lines couldn't be added:\n" + "\n".join(failed[:10]))

    def save_search_form(self, q):
        d = Form(self, "save search", [
            {"key": "query", "label": "search for", "default": q, "hint": "e.g.  router   or   sony wh-1000xm5"},
            {"key": "max", "label": "only under", "width": 10, "default": "", "hint": "Optional price cap, e.g. 150"},
            {"key": "stars", "label": "stars", "kind": "dropdown", "values": ["any", "3.5", "4", "4.5"], "default": "any",
             "hint": "Only alert for products rated at least this (checks reviews first)."},
            {"key": "deals", "label": "real discounts only", "kind": "check", "default": "1"}],
                 intro="You'll be alerted whenever a new product matches - without having to pick one exact item.",
                 validate=lambda d: None if E.parse_keywords(d["query"])[0] else "Enter something to search for.").result
        if not d:
            return
        try:
            mx = float(d["max"].lstrip("$").replace(",", "")) if d["max"].strip() else None
        except ValueError:
            mx = None
        con = E.db()
        con.execute("INSERT INTO saved_searches(query,max_price,min_rating,deals_only,created) VALUES(?,?,?,?,?)",
                    (d["query"].strip(), mx, None if d["stars"] == "any" else float(d["stars"]),
                     1 if d["deals"] == "1" else 0, time.time()))
        con.commit()
        self.toast("Search saved - you'll be alerted on every Watchlist check")
        if self.view == "watch":
            self.render_watch()

    def remove_saved(self, i):
        con = E.db()
        row = con.execute("SELECT * FROM saved_searches WHERE id=?", (i,)).fetchone()
        if not row:
            return
        saved = dict(row)
        con.execute("DELETE FROM saved_searches WHERE id=?", (i,))
        con.commit()
        self.render_watch()

        def undo():
            c = E.db()
            c.execute(f"INSERT OR REPLACE INTO saved_searches({','.join(saved)}) VALUES({','.join(':' + k for k in saved)})", saved)
            c.commit()
            self.render_watch()
        self.toast("Saved search removed", undo)

    def watch_row(self, parent, r, sym, con):
        self.frame(parent, "line", height=1).pack(fill="x", padx=26, pady=(12, 0))
        row = self.frame(parent)
        row.pack(fill="x", padx=26, pady=12)
        folded = r["id"] in self.watch_folded
        if folded:
            arrow = self.label(row, "\u25b8", "muted", font=self.f_bold, cursor="hand2", width=2)
            arrow.pack(side="left")
            name = self.label(row, r["keywords"], font=self.f_bold, cursor="hand2")
            name.pack(side="left")
            if r["best_price"] is not None:
                self.label(row, f"   {E.money(sym, r['best_price'])}  \u00b7  {r['best_store']}", "muted",
                           font=self.f_small).pack(side="left")
            if r["max_price"] is not None and r["best_price"] is not None and r["best_price"] <= r["max_price"]:
                self.label(row, "   \u2605 at target", "accent", font=self.f_small_b).pack(side="left")
            hist = E.price_history(con, r["id"])
            if len(hist) >= 2:
                self.mini_change(row, hist[-2]["price"], hist[-1]["price"], sym)
            for w in (arrow, name):
                w.bind("<Button-1>", lambda e, i=r["id"]: self.fold_watch([i], False))
            return
        row.columnconfigure(0, minsize=290)         # text on the left, then the figures + graph, buttons on the far right
        row.columnconfigure(1, minsize=px(8))       # fixed widths: the figures start at the same place in every row
        row.columnconfigure(2, minsize=px(540))
        row.columnconfigure(3, weight=1, minsize=px(170))     # last check + what triggers an alert, right of the graph
        row.columnconfigure(4, minsize=130)
        left = self.frame(row)
        left.grid(row=0, column=0, sticky="nw", padx=(0, 22))
        head = self.frame(left)
        head.pack(anchor="w")
        arrow = self.label(head, "\u25be", "muted", font=self.f_bold, cursor="hand2", width=2)
        arrow.pack(side="left", anchor="n")
        arrow.bind("<Button-1>", lambda e, i=r["id"]: self.fold_watch([i], True))
        kw = self.label(head, r["keywords"], font=self.f_bold, wraplength=240, justify="left", cursor="hand2")
        kw.pack(side="left")
        hit = r["max_price"] is not None and r["best_price"] is not None and r["best_price"] <= r["max_price"]
        trig = (f"Target {E.money(sym, r['max_price'])}" if r["max_price"] is not None
                else f"Any {r['min_drop_pct']:g}%+ sale or drop")
        best = (f"{E.money(sym, r['best_price'])}  \u00b7  {r['best_store']}"
                if r["best_price"] is not None else "Not checked yet")
        if hit:
            self.label(left, "\u2605 At or below your target", "accent", font=self.f_small_b).pack(anchor="w")
        bl = self.label(left, best, font=self.f_big if r["best_price"] is not None else self.f_small,
                        cursor="hand2")
        bl.pack(anchor="w", pady=(2, 0))
        flags = (["paused"] if r["paused"] else []) + (["alerts when back in stock"] if r["want_stock"] else []) + (
            [f"ignoring {r['ignore_stores']}"] if r["ignore_stores"] else [])
        if flags:
            self.label(left, "  \u00b7  ".join(flags), "muted", font=self.f_small, wraplength=240, justify="left").pack(anchor="w")
        for w in (kw, bl):
            w.bind("<Button-1>", lambda e, u=r["best_url"]: self.open_url(u))
        mid = self.frame(row)
        mid.grid(row=0, column=2, sticky="new")
        hist = E.price_history(con, r["id"])
        reg = E.regular_price(con, r["id"])
        txt = self.frame(mid)                            # the figures sit to the left of the graph; the graph uses the height
        mid.columnconfigure(0, minsize=px(262))          # the figures get a fixed column, so every graph starts and ends
        mid.columnconfigure(1, weight=1)                 # at the same place in every row
        txt.grid(row=0, column=0, sticky="nw", padx=(0, 16))
        ch = Chart(self, mid, [h["price"] for h in hist][-30:], height=120, on_click=lambda i=r["id"]: HistoryDialog(self, i),
                   lines=[(r["max_price"], "target"), (reg[0] if reg else None, "usual")], fixed_gutter=True)
        ch.cv.configure(width=px(290))
        ch.cv.grid(row=0, column=1, sticky="nsew")
        parts = history_text(sym, hist).split("\n")
        self.label(txt, parts[0], "muted", font=self.f_small, justify="left", wraplength=px(230)).pack(anchor="w")
        if len(parts) > 1:
            tail = parts[1].split(": ", 1)[-1]
            self.label(txt, parts[1], "accent" if tail.startswith("\u25bc") else "alert" if tail.startswith("\u25b2") else "muted",
                       font=self.f_small, justify="left", wraplength=px(230)).pack(anchor="w")
        if reg:
            line = f"Usual price (not on sale): {E.money(sym, reg[0])}"
            tone = "muted"
            if r["best_price"] and r["best_price"] < reg[0] * 0.98:
                line += f"   \u25bc now {100 * (reg[0] - r['best_price']) / reg[0]:.0f}% below"
                tone = "accent"
            elif r["best_price"] and r["best_price"] > reg[0] * 1.02:
                line += f"   \u25b2 now {100 * (r['best_price'] - reg[0]) / reg[0]:.0f}% above"
                tone = "alert"
            self.label(txt, line, tone, font=self.f_small, justify="left", wraplength=px(230)).pack(anchor="w")
        elif hist:
            self.label(txt, "Usual price: learning - needs a few more checks", "muted", font=self.f_small,
                       justify="left", wraplength=px(230)).pack(anchor="w")
        self.advice_lines(txt, E.buy_advice(r["best_price"], reg[0] if reg else None, hist, sym=sym), px(230))
        info = self.frame(row)
        info.grid(row=0, column=3, sticky="nw", padx=(16, 8))
        self.label(info, "Last checked", "muted", font=self.f_small).pack(anchor="w")
        when = fmt_time(r["checked_at"]) if r["checked_at"] else "Not checked yet"
        self.label(info, when, font=self.f_small, wraplength=px(160), justify="left").pack(anchor="w")
        self.label(info, "Alerts me on", "muted", font=self.f_small).pack(anchor="w", pady=(10, 0))
        self.label(info, trig, font=self.f_small, wraplength=px(160), justify="left").pack(anchor="w")
        right = self.frame(row)
        right.grid(row=0, column=4, sticky="ne")
        if r["best_url"]:
            self.button(right, "Open", lambda u=r["best_url"]: self.open_url(u), pad=(14, 4),
                        font=self.f_small).pack(anchor="e")
        self.button(right, "Recheck", lambda i=r["id"]: self.recheck_item(i), pad=(14, 4), style="ghost",
                    font=self.f_small).pack(anchor="e", pady=(4, 0))
        self.button(right, "Reset graph", lambda i=r["id"]: self.reset_graph(i), pad=(14, 4), style="ghost",
                    font=self.f_small).pack(anchor="e")
        self.button(right, "Resume" if r["paused"] else "Pause", lambda i=r["id"], p=r["paused"]: self.toggle_pause(i, p),
                    pad=(14, 4), style="ghost", font=self.f_small).pack(anchor="e")
        self.button(right, "Edit", lambda i=r["id"]: self.edit_item(i), pad=(14, 4), style="ghost",
                    font=self.f_small).pack(anchor="e")
        self.button(right, "Remove", lambda i=r["id"]: self.remove_item(i), pad=(14, 4), style="ghost",
                    font=self.f_small).pack(anchor="e")

    # ------------------------------------------------------------ about / dev --
    def dev_mode(self):
        return E.get_settings(E.db()).get("dev_mode", "0") == "1"

    def open_about(self):
        win = tk.Toplevel(self)
        win.title("About")
        win.transient(self)
        win.resizable(False, False)
        self.reg(win, "window")
        body = self.frame(win)
        body.pack(padx=28, pady=22)
        self.label(body, "Deals", font=self.f_page).pack(anchor="w")
        self.label(body, "Australian deal finder.", "muted").pack(anchor="w", pady=(2, 10))
        ver = self.label(body, f"Version {E.ENGINE_VERSION}", "muted", font=self.f_small)
        ver.pack(anchor="w")
        dev = self.frame(body)
        self.label(body, "Prices are read automatically - always check the shop before you buy.",
                   "muted", font=self.f_small, wraplength=360, justify="left").pack(anchor="w", pady=(10, 0))

        def build_dev():
            for w in dev.winfo_children():
                w.destroy()
            if not self.dev_mode():
                dev.pack_forget()
                return
            dev.pack(anchor="w", fill="x", pady=(16, 0), after=ver)
            self.label(dev, "Developer mode is on", "accent", font=self.f_small_b).pack(anchor="w")
            self.label(dev, "Creates a zip of the source list, their status and the error logs (no passwords, alert "
                       "details, watchlist or searches), copies a short summary to the clipboard and shows the file.",
                       "muted", font=self.f_small, wraplength=360, justify="left").pack(anchor="w", pady=(2, 8))
            row = self.frame(dev)
            row.pack(anchor="w")
            self.button(row, "Send diagnostics", lambda: self.make_diagnostics(win), pad=(14, 5)).pack(side="left")
            self.button(row, "Turn off", lambda: (self.set_dev_mode(False), build_dev()), pad=(14, 5),
                        style="ghost").pack(side="left", padx=(6, 0))

        def tap(_e=None):
            now = time.time()
            self._dev_clicks = self._dev_clicks + 1 if now - self._dev_t < 2.0 else 1
            self._dev_t = now
            if self.dev_mode():
                return
            if self._dev_clicks >= 10:
                self._dev_clicks = 0
                self.set_dev_mode(True)
                build_dev()
            elif self._dev_clicks >= 6:
                ver.configure(text=f"Version {E.ENGINE_VERSION}   ({10 - self._dev_clicks} more...)")
        ver.bind("<Button-1>", tap)
        build_dev()
        self.button(body, "close", win.destroy, pad=(14, 5), style="ghost").pack(anchor="e", pady=(16, 0))
        win.update_idletasks()
        win.geometry(f"+{self.winfo_rootx() + px(160)}+{self.winfo_rooty() + px(120)}")

    def set_dev_mode(self, on):
        E.set_setting(E.db(), "dev_mode", "1" if on else "0")
        self.apply_dev_tabs()
        self.set_status("developer mode " + ("on" if on else "off"))

    def make_diagnostics(self, parent):
        self.set_status("collecting diagnostics...")

        def work():
            try:
                path, summary = E.build_diagnostics()
                err = ""
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                path, summary, err = "", "", "could not build the diagnostics file - see deals_error.log"

            def finish():
                if err:
                    self.set_status(err)
                    return messagebox.showinfo("diagnostics", err)
                try:
                    self.clipboard_clear()
                    self.clipboard_append(summary)
                except tk.TclError:
                    pass
                try:
                    if sys.platform == "win32":
                        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
                    else:
                        webbrowser.open("file://" + os.path.dirname(path))
                except Exception:  # noqa: BLE001
                    pass
                self.set_status("diagnostics saved")
                messagebox.showinfo("diagnostics", "Saved, and a short summary is copied to your clipboard.\n\n"
                                    f"Attach this file in the chat:\n{path}")
            self.q.put(finish)
        threading.Thread(target=work, daemon=True).start()

    def advice_lines(self, parent, adv, wrap, padx=0):
        """The wait-or-buy verdict, what it is based on and what the item's own history says."""
        if not adv:
            return
        v = adv["verdict"]
        mark = {"buy": "\u2713 ", "wait": "\u23f3 ", "fair": "", "learning": ""}[v]
        tone = {"buy": "accent", "wait": "text", "fair": "muted", "learning": "muted"}[v]
        self.label(parent, f"{mark}{adv['headline']}", tone, font=self.f_small_b if v in ("buy", "wait") else self.f_small
                   ).pack(anchor="w", padx=padx, pady=(6, 0))
        for line in adv["detail"]:
            self.label(parent, line, "muted", font=self.f_small, wraplength=wrap, justify="left").pack(anchor="w", padx=padx)
        self.label(parent, adv["basis"], "muted", font=self.f_small).pack(anchor="w", padx=padx)

    # -------------------------------------------------------------- watchlist --
    def item_form(self, title, row=None, prefill=""):
        def validate(d):
            if not E.parse_keywords(d["keywords"])[0]:
                return "Enter at least one keyword (words starting with - only exclude)."
            if d["target"]:
                try:
                    if float(d["target"].lstrip("$").replace(",", "")) <= 0:
                        raise ValueError
                except ValueError:
                    return "Target price must be a number like 300."
            return None

        drop = f"{row['min_drop_pct']:g}%" if row else "10%"
        return Form(self, title, [
            {"key": "keywords", "label": "keywords", "default": row["keywords"] if row else prefill,
             "hint": "e.g.  sony wh-1000xm5 -case   (-word excludes)"},
            {"key": "target", "label": "target price", "width": 12,
             "default": f"{row['max_price']:g}" if row and row["max_price"] is not None else "",
             "hint": "Optional. Alert at or below this price. Blank = alert on any sale."},
            {"key": "drop", "label": "sale size", "kind": "dropdown", "values": DROPS,
             "default": drop if drop in DROPS else "10%", "hint": "Used when there's no target price."},
            {"key": "ignore", "label": "ignore stores", "width": 30, "default": (row["ignore_stores"] or "") if row else "",
             "hint": "Optional. Store names to skip for this item, separated by commas (e.g. kogan, catch)."},
            {"key": "stock", "label": "alert when back in stock", "kind": "check",
             "default": "1" if row and row["want_stock"] else "0"},
            {"key": "stockstore", "label": "back-in-stock store", "width": 24, "default": (row["stock_store"] or "") if row else "",
             "hint": "Optional. Only alert when it's back at this store (e.g. jb hi-fi). Blank = any store."},
            {"key": "folder", "label": "folder", "width": 24, "default": (row["folder"] or "") if row else "",
             "hint": "Optional. Group items together, e.g. Kitchen or Tech."},
            {"key": "paused", "label": "paused", "kind": "check", "default": "1" if row and row["paused"] else "0"},
        ], validate=validate).result

    def add_item(self, prefill=""):
        d = self.item_form("add to watchlist", prefill=prefill or self.query)
        if not d:
            return
        con = E.db()
        target = float(d["target"].lstrip("$").replace(",", "")) if d["target"] else None
        con.execute("INSERT INTO watchlist(keywords,max_price,min_drop_pct,ignore_stores,want_stock,paused,stock_store,folder) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (d["keywords"], target, float(d["drop"].rstrip("%")), d["ignore"].strip(),
                     1 if d["stock"] == "1" else 0, 1 if d["paused"] == "1" else 0, d["stockstore"].strip(), d["folder"].strip()))
        con.commit()
        self.render_watch()
        self.set_status("added - press 'check watchlist' to scan")

    def toggle_pause(self, i, paused):
        con = E.db()
        con.execute("UPDATE watchlist SET paused=? WHERE id=?", (0 if paused else 1, i))
        con.commit()
        self.render_watch()

    def edit_item(self, i):
        con = E.db()
        row = con.execute("SELECT * FROM watchlist WHERE id=?", (i,)).fetchone()
        if not row:
            return
        d = self.item_form("edit item", row=row)
        if not d:
            return
        target = float(d["target"].lstrip("$").replace(",", "")) if d["target"] else None
        con.execute("UPDATE watchlist SET keywords=?, max_price=?, min_drop_pct=?, ignore_stores=?, want_stock=?, "
                    "paused=?, stock_store=?, folder=? WHERE id=?",
                    (d["keywords"], target, float(d["drop"].rstrip("%")), d["ignore"].strip(),
                     1 if d["stock"] == "1" else 0, 1 if d["paused"] == "1" else 0, d["stockstore"].strip(),
                     d["folder"].strip(), i))
        con.commit()
        self.render_watch()

    def remove_item(self, i):
        con = E.db()
        row = con.execute("SELECT * FROM watchlist WHERE id=?", (i,)).fetchone()
        if not row:
            return
        saved = dict(row)
        con.execute("DELETE FROM watchlist WHERE id=?", (i,))
        con.commit()
        self.render_watch()

        def undo():
            c = E.db()
            cols = ",".join(saved)
            c.execute(f"INSERT OR REPLACE INTO watchlist({cols}) VALUES({','.join(':' + k for k in saved)})", saved)
            c.commit()
            self.render_watch()
        self.toast("Removed from your Watchlist", undo)

    def clear_deals(self):
        if messagebox.askyesno("clear", "Clear recent deals?\n(You may be re-alerted about ones already seen.)"):
            con = E.db()
            con.execute("DELETE FROM alerts")
            con.commit()
            self.mark_deals_seen()
            self.update_badge()
            self.render_watch()

    # --------------------------------------------------------------- checking --
    def start_check(self, only=None):
        if self.scanning:
            return self.set_status("already checking - try again in a moment")
        self.scanning, self.popups_shown = True, 0
        self.check_text, self.check_frac = "Checking your watchlist...", 0.0
        self.set_status("checking watchlist..." if only is None else "rechecking this item...")
        if self.view == "watch":
            self.render_watch()
        threading.Thread(target=self._check_worker, args=(only,), daemon=True).start()

    def recheck_item(self, i):
        self.start_check(only=i)

    def reset_graph(self, i):
        con = E.db()
        rows = E.reset_history(con, i)
        if not rows:
            return self.set_status("no history to reset yet")
        self.render_watch()

        def undo():
            E.restore_history(E.db(), rows)
            self.render_watch()
        self.toast("Price history cleared", undo)

    def _check_worker(self, only=None):
        try:
            n = E.run_check(log=lambda m: None, on_alert=lambda a: self.q.put(lambda: self.show_deal(a)),
                            progress=lambda d, t: self.q.put(lambda d=d, t=t: self.on_check_progress(d, t)), only_id=only)
            msg = f"checked {time.strftime('%H:%M')} - {n} new deal(s)"
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())
            msg = "check failed - see deals_error.log"
        self.q.put(lambda: self.check_done(msg))

    def on_check_progress(self, done, total):
        self.check_text = f"Checking your watchlist...  {done} of {total} lookups"
        self.check_frac = done / total if total else 0.0
        prog = getattr(self, "watch_prog", None)
        if self.scanning and prog:
            try:
                prog[0].configure(text=self.check_text)
                prog[1].set(self.check_frac)
            except tk.TclError:
                pass

    def check_done(self, msg):
        self.scanning = False
        self.set_status(msg)
        if self.auto_minutes:
            self.next_at = time.time() + self.auto_minutes * 60
        self.render_watch()
        self.update_badge()

    def tick(self):
        txt = None
        if self.scanning:
            txt = "checking..."
        elif self.auto_minutes and self.next_at:
            left = int(self.next_at - time.time())
            if left <= 0:
                self.start_check()
            else:
                txt = f"next check in {left // 60}m {left % 60:02d}s"
        if txt is not None and txt != self.next_var.get():     # only touch the label when the text really changed
            self.next_var.set(txt)
        self._ticks = getattr(self, "_ticks", 0) + 1
        if self._ticks % 60 == 30:
            try:
                self.maybe_digest()
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
        if self._ticks % 300 == 0:
            try:
                self.maybe_health()
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
        self.after(1000, self.tick)

    # ---------------------------------------------------- daily deals digest --
    def maybe_digest(self, force=False, host=None):
        """Once a day (if you opted in): look for fresh deals in the categories you chose and send them as one message.
        With force=True (the test button) it runs now and shows what it is doing."""
        if self._digest_busy:
            if force:
                messagebox.showinfo("digest", "A digest is already being built - one moment.")
            return
        s = E.get_settings(E.db())
        if not force and not E.digest_due(s):
            return
        cats = E.digest_cats(s)
        if force and not cats:
            return messagebox.showinfo("digest", "Pick at least one category first.")
        if self.scanning or self.searching or self.picking or getattr(self, "_testing_all", False):
            if force:
                messagebox.showinfo("digest", "Deals is busy with a search or check right now. Try again in a moment.")
            return                                             # wait until Deals is idle
        self._digest_busy = True
        stores = E.active_stores(E.db(), s.get("region") or self.region)
        if not stores:
            self._digest_busy = False
            return messagebox.showinfo("digest", "No sources are switched on. Open Sources > manage sources.") if force else None
        self.set_status("building your daily deals digest...")
        prog = None
        if force:
            host = host if host is not None and host.winfo_exists() else self
            prog = ProgressOverlay(self, host, "Building your digest", len(cats),
                                   "Searching just your categories. This can take a minute or two.")

        def step(i, n, cat):
            self.q.put(lambda: (prog.update(i, f"Looking for {cat} deals...") if prog else None,
                                self.set_status(f"digest: {cat} ({i + 1} of {n})")))

        def work():
            res, err = None, ""
            try:
                res = E.run_digest(stores, s, force=force, progress=step)
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                err = "the digest could not be built - see deals_error.log"

            def finish():
                self._digest_busy = False
                if prog:
                    prog.close()
                if res:
                    self.set_status(f"digest sent: {res['n']} deals")
                    if s.get("popups") == "1" or force:
                        self.show_digest(res)
                else:
                    self.set_status(err or "no strong deals found in your categories today")
                    if force:
                        messagebox.showinfo("digest", err or "Nothing strongly discounted in those categories right now, so "
                                            "no digest was sent. That is normal on a quiet day - try again tomorrow.")
            self.q.put(finish)
        threading.Thread(target=work, daemon=True).start()

    def show_search_report(self):
        """A plain account of the last search: which shops answered, how much came back and what was filtered."""
        text = E.LAST_SEARCH.get("text") or "No search report yet - run a search first."
        win = tk.Toplevel(self)
        win.title("Why these results?")
        win.transient(self)
        win.geometry(f"{px(760)}x{px(560)}+{self.winfo_rootx() + px(80)}+{self.winfo_rooty() + px(40)}")
        self.reg(win, "window")
        bar = self.frame(win)
        bar.pack(side="bottom", fill="x", padx=14, pady=10)

        def copy():
            try:
                self.clipboard_clear()
                self.clipboard_append(text)
                self.set_status("report copied")
            except tk.TclError:
                pass
        self.button(bar, "Copy", copy, style="solid").pack(side="right")
        self.button(bar, "Close", win.destroy).pack(side="right", padx=(0, 8))
        box = tk.Text(win, wrap="word", bd=0, highlightthickness=0, padx=px(14), pady=px(10), font=self.f_small)
        self.reg(box, "entry")
        box.configure(highlightthickness=0)
        box.insert("1.0", text)
        box.configure(state="disabled")
        box.pack(fill="both", expand=True)

    def show_digest(self, res):
        w = tk.Toplevel(self)
        w.title("Daily deals digest")
        w.attributes("-topmost", True)
        w.resizable(False, False)
        self.reg(w, "window")
        f = self.frame(w)
        f.pack(padx=16, pady=14)
        self.label(f, res["subject"], font=self.f_bold, wraplength=440, justify="left").pack(anchor="w")
        self.label(f, res["body"][:1400], "muted", font=self.f_small, wraplength=440, justify="left").pack(anchor="w", pady=(8, 0))
        bar = self.frame(f)
        bar.pack(anchor="e", pady=(12, 0))
        self.button(bar, "close", w.destroy).pack(side="left", padx=(0, 6))
        if res.get("url"):
            self.button(bar, "open first", lambda: (self.open_url(res["url"]), w.destroy())).pack(side="left")

    def open_digest(self):
        s = E.get_settings(E.db())
        sel = set(E.digest_cats(s))
        win = tk.Toplevel(self)
        win.title("Daily deals digest")
        win.transient(self)
        win.resizable(False, False)
        self.reg(win, "window")
        body = self.frame(win)
        body.pack(padx=24, pady=18)
        self.label(body, "Daily deals digest", font=self.f_big).pack(anchor="w")
        self.label(body, "Once a day, Deals searches only the categories you pick below and sends the best few in each as one "
                         "message (to your alert channels from Settings > alerts, and as a pop-up). Deals needs to be running "
                         "- keep it in the tray. Off unless you turn it on.", "muted", font=self.f_small, wraplength=480,
                   justify="left").pack(anchor="w", pady=(4, 12))
        top = self.frame(body)
        top.pack(anchor="w", fill="x")
        on = self.switch(top, s.get("digest_on") == "1")
        on.pack(side="left")
        self.label(top, "Send me a daily digest").pack(side="left", padx=10)
        hr = tk.StringVar(value=s.get("digest_hour", "8"))
        self.entry(top, hr, width=4).pack(side="right")
        self.label(top, "after hour (0-23)", "muted", font=self.f_small).pack(side="right", padx=8)
        self.label(body, f"Pick up to {E.DIGEST_MAX_CATS} categories:", font=self.f_small_b).pack(anchor="w", pady=(14, 4))
        grid = self.frame(body)
        grid.pack(anchor="w")
        count = self.label(body, "", "muted", font=self.f_small)
        count.pack(anchor="w", pady=(6, 0))
        sws = {}

        def upd():
            count.configure(text=f"{len(sel)} of {E.DIGEST_MAX_CATS} picked")

        def flip(cat, v):
            if v and len(sel) >= E.DIGEST_MAX_CATS:
                sws[cat].set(False)
                return self.toast(f"Up to {E.DIGEST_MAX_CATS} categories - switch another one off first")
            (sel.add if v else sel.discard)(cat)
            upd()
        for i, cat in enumerate(E.DAILY_CATS):
            cell = self.frame(grid)
            cell.grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 28), pady=3)
            sws[cat] = self.switch(cell, cat in sel, lambda v, c=cat: flip(c, v))
            sws[cat].pack(side="left")
            self.label(cell, cat, font=self.f_small).pack(side="left", padx=8)
        upd()

        def save(close=True):
            try:
                h = str(max(0, min(23, int(float(hr.get())))))
            except ValueError:
                h = "8"
            con = E.db()
            E.set_setting(con, "digest_on", "1" if on.get() else "0")
            E.set_setting(con, "digest_cats", json.dumps([c for c in E.DAILY_CATS if c in sel]))
            E.set_setting(con, "digest_hour", h)
            E.set_setting(con, "digest_sent", "")
            self.set_status("daily digest " + ("on" if on.get() and sel else "off"))
            if close:
                win.destroy()
        bar = self.frame(body)
        bar.pack(fill="x", pady=(16, 0))
        def test():
            if not sel:
                return messagebox.showinfo("digest", "Pick at least one category first.")
            save(False)
            self.maybe_digest(force=True, host=win)
        self.button(bar, "Send a test now", test, style="ghost").pack(side="left")
        self.button(bar, "cancel", win.destroy, style="ghost").pack(side="right")
        self.button(bar, "save", save, style="solid").pack(side="right", padx=(0, 6))
        win.update_idletasks()
        win.geometry(f"+{self.winfo_rootx() + px(140)}+{self.winfo_rooty() + px(60)}")

    def show_deal(self, a):
        self.render_watch()
        self.bell()
        if E.get_settings(E.db())["popups"] != "1" or self.popups_shown >= 5:
            return
        self.popups_shown += 1
        w = tk.Toplevel(self)
        w.title("Deal found")
        w.attributes("-topmost", True)
        w.resizable(False, False)
        self.reg(w, "window")
        f = self.frame(w)
        f.pack(padx=14, pady=12)
        self.label(f, f"{E.money(self.sym(), a['price'])}  {a['store']}", font=self.f_big).pack(anchor="w")
        self.label(f, a["title"], wraplength=380, justify="left").pack(anchor="w", pady=(4, 2))
        self.label(f, a["reasons"], "muted", font=self.f_small).pack(anchor="w")
        bar = self.frame(f)
        bar.pack(anchor="e", pady=(10, 0))
        self.button(bar, "dismiss", w.destroy).pack(side="left", padx=(0, 6))
        self.button(bar, "open", lambda: (self.open_url(a["url"]), w.destroy())).pack(side="left")

    # ----------------------------------------------------------------- stores --
    def test_stores(self, done=None, host=None):
        if getattr(self, "_testing_all", False):
            p = self._test_prog
            if p is not None and p.alive:
                p.show(host if host is not None and host.winfo_exists() else None)
                return self.set_status("testing - progress card brought back")
            return self.set_status("already testing - one moment")
        con = E.db()
        cfg = E.get_settings(con)
        cfg["region"] = cfg.get("region") or self.region
        stores = [dict(r) for r in con.execute("SELECT * FROM stores WHERE region=? OR custom=1", (cfg["region"],))]
        self.set_status(f"testing {len(stores)} sources...")
        self._testing_all = True
        host = host if host is not None and host.winfo_exists() else self
        prog = ProgressOverlay(self, host, "Testing sources", len(stores),
                               "A sample search at every shop. Shops that return nothing are marked in Sources.")
        self._test_prog = prog

        def work():
            results, bad = [], 0
            try:
                with ThreadPoolExecutor(max_workers=6) as ex:
                    futs = {ex.submit(lambda s=s: (s, *E.test_store(s, cfg=cfg))): s for s in stores}
                    for fut in as_completed(futs):
                        try:
                            r = fut.result()
                        except Exception:  # noqa: BLE001
                            s = futs[fut]
                            r = (s, "Error: test failed", False)
                        results.append(r)
                        bad += 0 if r[2] else 1
                        self.q.put(lambda n=len(results), nm=r[0]["name"], b=bad: (
                            prog.update(n, nm, b), self.set_status(f"testing sources... {n} of {len(stores)}")))
                c, now = E.db(), time.time()
                E.reset_health(c)                            # a full test gives every store a fresh chance
                for s, status, ok in results:
                    c.execute("UPDATE stores SET status=?, tested_at=? WHERE id=?", (status, now, s["id"]))
                    E.record_health(c, s["id"], ok)
                c.commit()
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())

            def finish():
                self._testing_all = False
                prog.close()
                self.tests_done(results, done)
            self.q.put(finish)

        threading.Thread(target=work, daemon=True).start()

    def verify_store(self, store_id, done=None, host=None):
        """Let a person pass a shop's bot check in a real browser window; Deals then reuses those cookies."""
        con = E.db()
        row = con.execute("SELECT * FROM stores WHERE id=?", (store_id,)).fetchone()
        if not row:
            return
        store = dict(row)
        if not messagebox.askokcancel(
                "verify " + store["name"],
                f"A browser window will open on {store['name']}.\n\nIf it shows a check (for example 'verify you are human'), "
                "complete it, look at a product page if you like, then CLOSE the window. Deals keeps that session and uses it "
                "for later searches, then tests the shop again.\n\nThis only works for checks a person can pass; shops "
                "that refuse all automated visits may still not work."):
            return
        url = (store.get("alt_url") or store["search_url"]).replace("{query}", E.sample_query(store).replace(" ", "+"))
        self.set_status(f"verify {store['name']} in the browser window, then close it...")

        def work():
            try:
                E.BROWSER.verify(url)
                err = ""
            except Exception as ex:  # noqa: BLE001
                log_error(traceback.format_exc())
                err = str(ex)[:120] or "the browser could not be opened"

            def finish():
                if err:
                    self.set_status("couldn't open the browser: " + err)
                    return messagebox.showinfo("verify", "Couldn't open a browser window: " + err)
                E.reset_site_failures()
                self.test_store_one(store_id, done, host=host)
            self.q.put(finish)
        threading.Thread(target=work, daemon=True).start()

    def test_store_one(self, store_id, done=None, host=None):
        """Test a single shop with a sample search that suits what it sells, showing each step as it happens."""
        con = E.db()
        row = con.execute("SELECT * FROM stores WHERE id=?", (store_id,)).fetchone()
        if not row:
            return
        store, cfg = dict(row), E.get_settings(con)
        cfg["region"] = cfg.get("region") or self.region
        host = host if host is not None and host.winfo_exists() else self
        prog = ProgressOverlay(self, host, "Testing " + store["name"], None,
                               "A sample search, the same way Deals searches this shop.")
        prog.step("Starting...")
        self.set_status(f"testing {store['name']}...")

        def work():
            def step(t):
                self.q.put(lambda t=t: (prog.step(t), self.set_status(f"{store['name']}: {t.lower()}")))
            status, ok = E.test_store(store, cfg=cfg, step=step)
            c = E.db()
            c.execute("UPDATE stores SET status=?, tested_at=? WHERE id=?", (status, time.time(), store_id))
            c.execute("UPDATE stores SET fail_streak=0, skip_until=0 WHERE id=?", (store_id,))
            if ok:
                c.execute("UPDATE stores SET enabled=1 WHERE id=?", (store_id,))     # it works: make sure it is on
            else:
                E.record_health(c, store_id, False)
            c.commit()

            def finish():
                prog.close()
                self.set_status(f"{store['name']}: {status}")
                if done:
                    done()
            self.q.put(finish)

        threading.Thread(target=work, daemon=True).start()

    def tests_done(self, results, done):
        bad = [s for s, _, ok in results if not ok]
        self.set_status(f"tested {len(results)} sources: {len(results) - len(bad)} ok, {len(bad)} not working")
        if bad and messagebox.askyesno(
                "switch off broken sources?",
                f"{len(bad)} of {len(results)} sources returned nothing (blocked, bot-check page, or they need "
                "JavaScript - the reason is shown in Sources).\n\nSwitch them off so searches are faster? "
                "You can switch them back on."):
            c = E.db()
            for s in bad:
                c.execute("UPDATE stores SET enabled=0 WHERE id=?", (s["id"],))
            c.commit()
        if done:
            done()

    def reset_stores(self):
        if messagebox.askyesno("reset", "Restore the built-in store list? Custom stores are kept."):
            E.reset_catalog(E.db())

    def add_store(self, done=None):
        def validate(d):
            if not d["name"]:
                return "Give the store a name."
            if "{query}" not in d["url"] or not d["url"].startswith("http"):
                return "The search address must start with http and contain {query} where the search word goes."
            sel = [d["item"], d["title"], d["price"]]
            if any(sel) and not all(sel):
                return "For manual selectors fill in card, title and price (or leave all three blank)."
            return None

        d = Form(self, "add custom store", [
            {"key": "name", "label": "store name"},
            {"key": "url", "label": "search address", "width": 44,
             "hint": "Search the store's site, copy the address, replace the search word with {query}."},
            {"key": "item", "label": "card selector", "hint": "Optional CSS selectors. Leave these 4 blank to auto-detect."},
            {"key": "title", "label": "title selector"}, {"key": "price", "label": "price selector"},
            {"key": "was", "label": "old price selector"},
        ], ok_text="add", validate=validate).result
        if not d:
            return
        con = E.db()
        try:
            con.execute("INSERT INTO stores(name,region,search_url,item,title,price,was_price,custom) "
                        "VALUES(?,?,?,?,?,?,?,1)",
                        (d["name"], "Custom", d["url"], d["item"] or None, d["title"] or None,
                         d["price"] or None, d["was"] or None))
            con.commit()
        except Exception:  # noqa: BLE001
            return messagebox.showerror("store", "A custom store with that name already exists.")
        self.set_status("store added - testing it...")
        self.test_stores(done)

    # ----------------------------------------------------------------- alerts --
    def open_alerts(self):
        AlertsDialog(self)

    def toggle_health(self):
        con = E.db()
        on = E.get_settings(con).get("health_auto", "1") != "0"
        E.set_setting(con, "health_auto", "0" if on else "1")
        messagebox.showinfo("Deals", "Weekly source check is now " + ("off." if on else "on. Deals will quietly test every "
                            "source about once a week and tell you if any stop working."))

    def export_report(self):
        dest = filedialog.asksaveasfilename(title="Save Watchlist report", defaultextension=".html",
                                            initialfile="watchlist-report.html")
        if dest:
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(E.watch_report_html(E.db(), self.sym()))
            self.set_status("report saved - open it in your browser to print or share")

    def check_updates(self, silent=False):
        con = E.db()
        url = E.get_settings(con).get("update_url", "")
        if FROZEN:
            url = "github-releases"                              # the installed app always checks its GitHub releases
        if not url and not silent:
            try:
                d = Form(self, "check for updates", [{"key": "url", "label": "update address", "width": 44, "default": ""}],
                         intro="Deals can check a web address for a newer version. Put a text file online (e.g. a GitHub raw "
                               "link) whose first line is the newest engine version number and second line is the download page. "
                               "Leave blank to skip.").result
                url = (d or {}).get("url", "").strip()
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                from tkinter import simpledialog
                url = (simpledialog.askstring("check for updates", "Update address (a link to a text file with the newest "
                                              "version number on the first line):", parent=self) or "").strip()
            if not url:
                return
            E.set_setting(con, "update_url", url)
        if not url:
            return
        if not silent:
            self.set_status(f"checking for updates...  (you have version {E.ENGINE_VERSION})")

        def work():
            m = E.fetch_update_manifest(E.get_settings(E.db()))
            self.q.put(lambda: self.update_result(m, silent))
        threading.Thread(target=work, daemon=True).start()

    def update_result(self, m, silent):
        self.set_status("ready")
        try:
            E.set_setting(E.db(), "update_checked", str(time.time()))
        except Exception:  # noqa: BLE001
            pass
        if m is None:
            return None if silent else messagebox.showinfo(
                "updates", f"Couldn't read that update address.\n\nYou have version {E.ENGINE_VERSION}.")
        latest = m["version"]
        if latest > E.ENGINE_VERSION:
            self.show_update(m)                                     # "Later" only lasts until the next launch
        elif not silent:
            messagebox.showinfo("updates", f"You have the newest version.\n\nYou have: version {E.ENGINE_VERSION}\n"
                                f"Newest: version {latest}")

    # ---- the big "update available" page ----
    def show_update(self, m):
        if getattr(self, "_updating", False):                    # a download is under way: leave its page alone
            return
        self.hide_update()
        P = self.P
        ov = tk.Frame(self, bg=P["bg"], bd=0, highlightthickness=0)
        ov.place(x=0, y=0, relwidth=1, relheight=1)
        ov.lift()
        self._update_ov = ov
        box = tk.Frame(ov, bg=P["bg"], bd=0, highlightthickness=1, highlightbackground=P["border"], padx=px(40), pady=px(32))
        box.place(relx=0.5, rely=0.45, anchor="center")

        def lab(text, font, fg=None, **kw):
            w = tk.Label(box, text=text, font=font, bg=P["bg"], fg=fg or P["fg"], bd=0, anchor="w", justify="left", **kw)
            w.pack(anchor="w")
            return w
        lab("A new version of Deals is ready", self.f_page)
        lab(f"Version {m['version']}   (you have {E.ENGINE_VERSION})", self.f_big, P["accent"]).pack_configure(pady=(6, 14))
        notes = []
        if m.get("notes"):
            lab("What's new", self.f_small_b, P["muted"])
            for n in m["notes"][:8]:
                w = lab("\u2022  " + n, self.f_norm, wraplength=px(520))
                w.pack_configure(pady=(2, 0))
                notes.append(w)
        self._update_msg = lab("", self.f_small, P["muted"], wraplength=px(520))
        self._update_msg.pack_configure(pady=(16, 0))
        bar = tk.Frame(box, bg=P["bg"])
        bar.pack(anchor="w", pady=(18, 0))
        self._update_bar = bar
        frozen = FROZEN
        if frozen:
            self._upd(text="Deals will download the update, check it, and restart itself. "
                                            "Your watchlist and settings are kept.")
            self.button(bar, "Update now", lambda: self.run_update(m), pad=(22, 9), style="solid", font=self.f_bold).pack(side="left")
        else:
            self.button(bar, "Update now", lambda: self.run_update(m), pad=(22, 9), style="solid", font=self.f_bold).pack(side="left")
            self._upd(text="Your current files are backed up first, so you can always go back.")
        self.button(bar, "Later", lambda: self.update_later(m), pad=(20, 9), style="ghost").pack(side="left", padx=(10, 0))
        if m.get("page"):
            self.button(bar, "View on GitHub", lambda: self.open_url(m["page"]), pad=(14, 9), style="ghost",
                        font=self.f_small).pack(side="left", padx=(10, 0))

        # Fit the page to the window: text wraps to the window's width, and when the window is short the longer
        # "what's new" lines are left out (the buttons always stay on screen) and come back as the window grows.
        wrapped = notes + [self._update_msg]

        def fit(_e=None):
            try:
                ow, oh = ov.winfo_width(), ov.winfo_height()
                if ow < 50 or oh < 50:
                    return
                wl = max(px(200), min(px(520), ow - px(80) - 2 * px(24)))
                for w in wrapped:
                    if int(float(str(w.cget("wraplength")))) != wl:
                        w.configure(wraplength=wl)
                for w in notes:
                    if not w.winfo_manager():
                        w.pack(anchor="w", pady=(2, 0), before=self._update_msg)
                box.update_idletasks()
                shown = list(notes)
                while shown and box.winfo_reqheight() > oh - px(24):
                    shown.pop().pack_forget()
                    box.update_idletasks()
            except tk.TclError:
                pass
        ov.bind("<Configure>", fit)
        self._update_fit = fit
        self.after(30, fit)

    def _upd(self, **kw):
        """Change the update page's message; quietly do nothing if that page has already gone."""
        try:
            self._update_msg.configure(**kw)
            self.after(10, self._update_fit)             # a longer message may need room
        except (tk.TclError, AttributeError):
            pass

    def hide_update(self):
        ov = getattr(self, "_update_ov", None)
        if ov is not None:
            try:
                ov.destroy()
            except tk.TclError:
                pass
        self._update_ov = None

    def update_later(self, m):
        E.set_setting(E.db(), "update_later", f"{m['version']}:{time.strftime('%Y%m%d')}")
        self.hide_update()
        self.set_status(f"update to version {m['version']} postponed - Help > check for updates when you're ready")

    def run_update(self, m):
        if getattr(self, "_updating", False):
            return
        self._updating = True
        for w in self._update_bar.winfo_children():
            w.destroy()
        self._upd(text="Downloading the update...  please don't close Deals.", fg=self.P["fg"])
        self.tray_status("downloading an update...")

        last = {"p": -1}

        def prog(i, n):
            if FROZEN:                                           # bytes so far / total bytes
                pct = i * 100 // max(n, 1)
                if pct == last["p"]:                             # one update per percent, not one per chunk
                    return
                last["p"] = pct
                self.q.put(lambda: self._upd(
                    text=f"Downloading the update...  {pct}%  ({i / 1048576:.0f} of {n / 1048576:.0f} MB)"))
            else:
                self.q.put(lambda: self._upd(text=f"Downloading the update...  file {min(i + 1, n)} of {n}"))

        def work():
            try:
                ok, msg = E.download_installer(m, progress=prog) if FROZEN else E.download_update(m, progress=prog)
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                ok, msg = False, "something went wrong - see Help > open error log. Your files were not changed."
            self.q.put(lambda: self.update_done(m, ok, msg))
        threading.Thread(target=work, daemon=True).start()

    def update_done(self, m, ok, msg):
        self._updating = False
        for w in self._update_bar.winfo_children():
            w.destroy()
        if ok and FROZEN:                                        # msg is the verified installer's path
            self.tray_status(f"installing update {m['version']}...")
            self._upd(text=f"\u2713 Verified. Installing version {m['version']} - Deals will close and reopen "
                                            "by itself in a few seconds.", fg=self.P["accent"])
            def launch():
                E.prepare_for_installer()                        # browser + helper processes must be gone first
                try:
                    E.run_installer(msg)
                except OSError:
                    log_error(traceback.format_exc())
                    self.q.put(lambda: self._upd(text="Couldn't start the installer - it was saved here, so you can run it "
                                                 "yourself:\n" + msg, fg=self.P["alert"]))
                    return
                self.q.put(lambda: self.after(700, self.exit_for_update))
            threading.Thread(target=launch, daemon=True).start()
            return
        if not ok:
            self._upd(text="The update didn't install: " + msg, fg=self.P["alert"])
            self.button(self._update_bar, "Try again", lambda: self.run_update(m), pad=(20, 9), style="solid").pack(side="left")
            self.button(self._update_bar, "Close", self.hide_update, pad=(20, 9), style="ghost").pack(side="left", padx=(10, 0))
            return
        self._upd(text=f"\u2713 Updated to version {m['version']}. " + msg + "\nRestart Deals to start using it.",
                                   fg=self.P["accent"])
        self.button(self._update_bar, "Restart now", self.restart_app, pad=(22, 9), style="solid",
                    font=self.f_bold).pack(side="left")
        self.button(self._update_bar, "Later", self.hide_update, pad=(20, 9), style="ghost").pack(side="left", padx=(10, 0))

    def restart_app(self):
        try:
            args = sys.argv[1:] if FROZEN else sys.argv
            subprocess.Popen([sys.executable] + args, cwd=os.path.dirname(os.path.abspath(sys.argv[0])) or None,
                             env=E.clean_env())
        except OSError:
            log_error(traceback.format_exc())
            return messagebox.showinfo("restart", "Couldn't restart automatically - please close and reopen Deals.")
        self.after(300, self.on_close)

    def sync_shop_list(self, silent=False):
        """Fetch the shared shop list from GitHub (new shops and fixed search addresses) without a new release."""
        if getattr(self, "_syncing", False):
            return
        self._syncing = True
        if not silent:
            self.set_status("updating the shop list...")

        def work():
            try:
                changed, msg = E.sync_remote_catalog(E.get_settings(E.db()), force=not silent)
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                changed, msg = False, "couldn't update the shop list"

            def done():
                self._syncing = False
                if changed:
                    self.set_status(msg)
                    self.refresh_store_views()
                elif not silent:
                    self.set_status(msg)
            self.q.put(done)
        threading.Thread(target=work, daemon=True).start()

    def refresh_store_views(self):
        """Re-draw the Sources window if it is open."""
        for w in self.winfo_children():
            if isinstance(w, StoresDialog):
                try:
                    w.refresh()
                except Exception:  # noqa: BLE001
                    pass

    def auto_update_check(self):
        """Every time Deals starts, quietly look for a new version."""
        try:
            st = E.get_settings(E.db())
            if st.get("update_url") or FROZEN:                       # every launch, a few seconds after start-up
                self.check_updates(silent=True)
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())

    def maybe_health(self):
        """About once a week, quietly test every source and say so if some have stopped working."""
        if self.scanning or self.searching or self.picking or getattr(self, "_health", False):
            return
        con = E.db()
        st = E.get_settings(con)
        if st.get("health_auto", "1") == "0":
            return
        last = float(st.get("health_at") or 0)
        if not last:
            return E.set_setting(con, "health_at", str(time.time()))
        if time.time() - last < 7 * 86400:
            return
        E.set_setting(con, "health_at", str(time.time()))
        self.run_health(silent=True)
        if st.get("update_url"):
            self.check_updates(silent=True)

    def run_health(self, silent=False):
        if self.searching or self.picking or getattr(self, "_health", False):
            return self.set_status("busy - try again in a moment")
        if not silent and not messagebox.askyesno("check sources", "Test every source with a sample search to see which ones still work?\n"
                                                   "This takes a minute or two."):
            return
        self._health, self._health_silent = True, silent
        con = E.db()
        cfg = E.get_settings(con)
        cfg["region"] = cfg.get("region") or self.region
        stores = E.active_stores(con, cfg["region"])
        self.set_status(f"testing {len(stores)} sources...")
        prog = None if silent else ProgressOverlay(self, self, "Checking sources", len(stores),
                                                   "A sample search at every shop that is switched on.")

        def work():
            try:
                res = E.health_check(stores, cfg, progress=lambda d, t: self.q.put(
                    lambda d=d, t=t: (prog.update(d) if prog else None, self.set_status(f"testing sources... {d} of {t}"))))
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                res = []

            def finish():
                if prog:
                    prog.close()
                self.health_done(res)
            self.q.put(finish)
        threading.Thread(target=work, daemon=True).start()

    def health_done(self, res):
        self._health = False
        self.set_status("ready")
        if getattr(self, "_health_silent", False):
            self._health_silent = False
            bad = [r for r in res if r["status"] != "ok"]
            if bad and len(bad) >= 3:
                self.toast(f"{len(bad)} of {len(res)} sources need a look - Settings > check all sources", secs=12)
            return
        if not res:
            return messagebox.showinfo("check sources", "The test couldn't run - see Help > open error log.")
        ok = [r for r in res if r["status"] == "ok"]
        bad = [r for r in res if r["status"] != "ok"]
        names = {"none": "page loads but no products found (layout may have changed)", "few": "only a few products",
                 "blocked": "blocked us", "botcheck": "bot check", "needsjs": "needs browser mode", "error": "error",
                 "timeout": "too slow"}
        lines = [f"- {r['name']}: {names.get(r['status'], r['status'])}" for r in bad[:30]]
        snaps = sum(1 for r in bad if r.get("snap"))
        msg = f"{len(ok)} of {len(res)} sources work.\n" + ("\nNeeds a look:\n" + "\n".join(lines) if lines else "\nEverything is working.")
        if len(bad) > 30:
            msg += f"\n...and {len(bad) - 30} more"
        if snaps:
            msg += f"\n\nSaved the page from {snaps} source(s) to the 'snapshots' folder so a changed layout can be fixed."
        messagebox.showinfo("check sources", msg)

    def run_repair(self):
        if self.searching or self.picking or getattr(self, "_health", False) or getattr(self, "_repairing", False):
            return self.set_status("busy - try again in a moment")
        con = E.db()
        n = con.execute("SELECT COUNT(*) FROM stores WHERE status LIKE 'Search URL%' OR status LIKE 'No products%' "
                        "OR status LIKE 'Error%'").fetchone()[0]
        if not n:
            return messagebox.showinfo("repair sources", "No broken sources to repair. Run Sources > test all sources first "
                                       "if you haven't lately.")
        if not messagebox.askyesno("repair broken sources", f"{n} source(s) aren't finding products. Deals will look for each "
                                   "shop's real search address and switch it back on if it finds one. This can take a few minutes. Continue?"):
            return
        self._repairing = True
        cfg = E.get_settings(con)
        self.set_status("repairing sources...")
        prog = ProgressOverlay(self, self, "Repairing sources", n,
                               "Looking for each shop's real search address. This can take a few minutes.")

        def work():
            try:
                res = E.repair_sources(E.db(), cfg, progress=lambda d, t: self.q.put(
                    lambda d=d, t=t: (setattr(prog, "total", max(t, 1)), prog.update(d, "", None), self.set_status(f"repairing sources... {d} of {t}"))))
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                res = []

            def finish():
                prog.close()
                self.repair_done(res)
            self.q.put(finish)
        threading.Thread(target=work, daemon=True).start()

    def repair_done(self, res):
        self._repairing = False
        self.set_status("ready")
        fixed = [r["name"] for r in res if r["ok"]]
        left = [r["name"] for r in res if not r["ok"]]
        msg = f"Repaired {len(fixed)} of {len(res)} source(s)."
        if fixed:
            msg += "\n\nBack on: " + ", ".join(fixed)
        if left:
            msg += "\n\nCouldn't fix: " + ", ".join(left[:25]) + ("..." if len(left) > 25 else "") + \
                   "\n(These shops block automated searches or build pages Deals can't read yet. StaticICE covers many of them.)"
        messagebox.showinfo("repair sources", msg)
        try:
            self.test_stores()
        except Exception:  # noqa: BLE001
            pass

    def run_selftest(self):
        try:
            import selftest
            problems = selftest.run()
        except ImportError:
            return messagebox.showinfo("self-check", "selftest.py isn't in the Deals folder.")
        except Exception:  # noqa: BLE001
            log_error(traceback.format_exc())
            return messagebox.showinfo("self-check", "The self-check crashed - see Help > open error log.")
        messagebox.showinfo("self-check", "All price-reading checks passed." if not problems else
                            "Some checks failed:\n" + "\n".join(problems[:15]))

    def open_hidden(self):
        cur = E.get_settings(E.db()).get("blocked", "ebay")
        d = Form(self, "hidden sites", [
            {"key": "blocked", "label": "sites to hide", "default": "" if cur == "none" else cur, "width": 34,
             "hint": "Words from a store's name or web address, separated by commas. Anything from these sites "
                     "is removed from every search and alert. Leave empty to show everything."}],
                 intro="eBay is hidden by default to cut clutter.").result
        if d is not None:
            val = d["blocked"].strip()
            E.set_setting(E.db(), "blocked", val if val else "none")
            self.set_status("hidden sites saved")

    def set_browser(self, on):
        E.set_setting(E.db(), "browser", "1" if on else "0")
        self.refresh_browser_row()

    def refresh_browser_row(self):
        d = self.stores_dialog
        try:
            if d is not None and d.winfo_exists():
                d.update_browser_row()
        except tk.TclError:
            pass

    def first_run_browser(self):
        con = E.db()
        s = E.get_settings(con)
        if s.get("browser_asked") == "1" or E.BrowserEngine.installed():
            return
        E.set_setting(con, "browser_asked", "1")
        if messagebox.askyesno(
                "read JavaScript stores?",
                "Many stores only show prices after their page runs JavaScript, and some block plain requests. "
                "To read those, deals can drive a hidden browser.\n\nIt uses Microsoft Edge or Chrome if you have "
                "them; otherwise it downloads about 150 MB once.\n\nSet it up now?"):
            self.install_browser()

    def install_browser(self):
        if getattr(self, "installing", False):
            return
        self.installing = True
        self.set_status("setting up browser mode - this can take a few minutes...")

        def work():
            try:
                ok, msg = E.install_browser(log=lambda m: self.q.put(lambda m=m: self.set_status("browser setup: " + m)))
            except Exception:  # noqa: BLE001
                log_error(traceback.format_exc())
                ok, msg = False, "setup failed - see deals_error.log"
            self.q.put(lambda: self.browser_done(ok, msg))

        threading.Thread(target=work, daemon=True).start()

    def browser_done(self, ok, msg):
        self.installing = False
        self.set_status("browser mode " + ("is ready" if ok else "setup failed"))
        self.refresh_browser_row()
        messagebox.showinfo("browser mode", ("Browser mode is " + msg + ".") if ok else
                            "Couldn't set up browser mode: " + msg +
                            "\n\nYou can retry from Sources > manage sources.")

    def send_test(self, data):
        s = E.get_settings(E.db())
        s.update(data)
        chans = [n for n, ok in (("ntfy", s.get("ntfy")), ("discord", s.get("discord")),
                                 ("telegram", s.get("tg_token") and s.get("tg_chat")),
                                 ("email", s.get("email_host") and s.get("email_to"))) if ok]
        self.show_deal({"price": 0.0, "store": "test", "title": "This is a test - pop-ups work.",
                        "reasons": "no action needed", "url": ""})

        def work():
            E.notify(s, "Deals test", "If you see this, alerts work.", None, lambda m: None)
            msg = ("test sent to: " + ", ".join(chans)) if chans else "pop-up works; add ntfy etc. for phone alerts"
            self.q.put(lambda: self.set_status(msg))

        threading.Thread(target=work, daemon=True).start()


def main():
    try:
        E.lower_priority()
        try:
            sys.setswitchinterval(0.002)              # background threads hand the window its turn sooner (default 5 ms)
        except Exception:  # noqa: BLE001
            pass
        E.start_resource_log()
        App().mainloop()
    except Exception:  # noqa: BLE001
        err = traceback.format_exc()
        log_error(err)
        if sys.platform == "win32" and "--classic" not in sys.argv:
            try:                                           # the custom window frame may be the cause: try the normal one
                args = (sys.argv[1:] if FROZEN else sys.argv) + ["--classic"]
                subprocess.Popen([sys.executable] + args, env=E.clean_env())
                return
            except Exception:  # noqa: BLE001
                pass
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("Deals hit a problem", err[-1500:] + "\n\n(saved to deals_error.log)")
        except Exception:  # noqa: BLE001
            print(err)


if __name__ == "__main__":
    main()
