"""
ui_kit - the app's look and feel.

  * DPI scaling, so the window is crisp on high-resolution screens
  * anti-aliased rounded shapes (drawn at 4x and shrunk with Pillow; plain canvas shapes without Pillow)
  * rounded buttons, an iOS-style switch, a pill text field, a slim scrollbar, smooth wheel scrolling,
    and a price chart
  * a title bar that matches the theme (Windows 10/11) and a generated app icon
"""
from __future__ import annotations

import ctypes
import math
import sys
import tkinter as tk
from tkinter import font as tkfont

HAS_PIL = False
Image = ImageDraw = ImageTk = None
UI = 1.0            # screen scale: 1.0 = 96 dpi
SS = 4              # supersampling factor for anti-aliased shapes
_CACHE: dict = {}
_PATCHED = False


# --------------------------------------------------------------------------- #
# Setup
# --------------------------------------------------------------------------- #
def load_pil() -> bool:
    global HAS_PIL, Image, ImageDraw, ImageTk
    try:
        from PIL import Image as _I, ImageDraw as _D, ImageTk as _T
        Image, ImageDraw, ImageTk, HAS_PIL = _I, _D, _T, True
    except Exception:  # noqa: BLE001
        HAS_PIL = False
    return HAS_PIL


def enable_dpi_awareness():
    """Call before any Tk window exists. Without it Windows blurs the whole app on scaled screens."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass
    try:                                    # own taskbar identity (so the app's icon is used)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Deals.App.1")
    except Exception:  # noqa: BLE001
        pass


def init_scale(root) -> float:
    global UI
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except Exception:  # noqa: BLE001
        dpi = 96.0
    UI = 1.0 if sys.platform == "darwin" else max(1.0, min(3.0, dpi / 96.0))
    return UI


def px(n) -> int:
    return int(round(n * UI))


_PADS = ("padx", "pady", "ipadx", "ipady")


def _scaled(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return px(v)
    if isinstance(v, (tuple, list)):
        return tuple(px(x) if isinstance(x, (int, float)) else x for x in v)
    return v


def patch_geometry():
    """On scaled screens, multiply every pack()/grid() padding by the scale so layouts keep their proportions."""
    global _PATCHED
    if _PATCHED or UI < 1.01:
        return
    _PATCHED = True
    for cls, names in ((tk.Pack, ("pack", "pack_configure")), (tk.Grid, ("grid", "grid_configure"))):
        orig = getattr(cls, names[1])

        def make(orig):
            def configure(self, cnf=None, **kw):
                cnf = dict(cnf or {})
                for d in (cnf, kw):
                    for k in _PADS:
                        if k in d:
                            d[k] = _scaled(d[k])
                return orig(self, cnf, **kw)
            return configure

        new = make(orig)
        for n in names:
            setattr(cls, n, new)


# --------------------------------------------------------------------------- #
# Colour helpers
# --------------------------------------------------------------------------- #
def rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a, b, t: float):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# --------------------------------------------------------------------------- #
# Anti-aliased shapes
# --------------------------------------------------------------------------- #
def can_aa() -> bool:
    return HAS_PIL and hasattr(ImageDraw.ImageDraw, "rounded_rectangle")


def _resample():
    return getattr(Image, "Resampling", Image).LANCZOS


def _remember(key, photo):
    if len(_CACHE) > 800:
        _CACHE.clear()
    _CACHE[key] = photo
    return photo


def aa_rrect(w, h, r, fill, outline, bw, bg):
    """Smooth rounded rectangle blended onto the background colour."""
    key = ("rr", w, h, r, fill, outline, bw, bg)
    ph = _CACHE.get(key)
    if ph is None:
        S = SS
        big = Image.new("RGB", (w * S, h * S), rgb(bg))
        d = ImageDraw.Draw(big)
        box = (0, 0, w * S - 1, h * S - 1)
        if outline and outline != fill and bw > 0:
            d.rounded_rectangle(box, radius=r * S, fill=rgb(outline))
            d.rounded_rectangle((bw * S, bw * S, w * S - 1 - bw * S, h * S - 1 - bw * S),
                                radius=max(0, r - bw) * S, fill=rgb(fill))
        else:
            d.rounded_rectangle(box, radius=r * S, fill=rgb(fill))
        ph = _remember(key, ImageTk.PhotoImage(big.resize((w, h), _resample())))
    return ph


def aa_pill(w, h, fill):
    """Smooth pill with a transparent surround (for badges that sit on pictures)."""
    key = ("pill", w, h, fill)
    ph = _CACHE.get(key)
    if ph is None:
        S = SS
        m = Image.new("L", (w * S, h * S), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=h * S // 2, fill=255)
        img = Image.new("RGBA", (w, h), rgb(fill) + (255,))
        img.putalpha(m.resize((w, h), _resample()))
        ph = _remember(key, ImageTk.PhotoImage(img))
    return ph


def aa_switch(w, h, d, pos, off, on, knob_off, knob_on, bg):
    key = ("sw", w, h, d, round(pos, 2), off, on, knob_off, knob_on, bg)
    ph = _CACHE.get(key)
    if ph is None:
        S, m = SS, max(1, (h - d) // 2)
        big = Image.new("RGB", (w * S, h * S), rgb(bg))
        dr = ImageDraw.Draw(big)
        dr.rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=h * S // 2, fill=mix(rgb(off), rgb(on), pos))
        x = (m + pos * (w - 2 * m - d)) * S
        y = m * S
        shadow = mix(rgb(bg), (0, 0, 0), 0.22)
        dr.ellipse((x, y + S, x + d * S, y + d * S + S), fill=mix(rgb(off), shadow, 0.5))
        dr.ellipse((x, y, x + d * S, y + d * S), fill=mix(rgb(knob_off), rgb(knob_on), pos))
        ph = _remember(key, ImageTk.PhotoImage(big.resize((w, h), _resample())))
    return ph


def rrect(cv, x1, y1, x2, y2, r, **kw):
    """Plain canvas rounded rectangle (fallback when Pillow isn't available)."""
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r,
           x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
           x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def draw_rrect(cv, x, y, w, h, r, fill, outline, bw, bg, tags=None):
    """Draw a rounded rectangle at (x, y): an anti-aliased image if possible, else a canvas polygon."""
    w, h, r = int(w), int(h), int(r)
    if can_aa():
        ph = aa_rrect(w, h, r, fill, outline, bw, bg)
        cv.__dict__.setdefault("_keep", []).append(ph)
        return cv.create_image(x, y, image=ph, anchor="nw", tags=tags)
    return rrect(cv, x + 1, y + 1, x + w - 1, y + h - 1, r, fill=fill, outline=outline or fill, width=1, tags=tags)


def draw_pill(cv, x, y, w, h, fill):
    w, h = int(w), int(h)
    if can_aa():
        ph = aa_pill(w, h, fill)
        cv.__dict__.setdefault("_keep", []).append(ph)
        return cv.create_image(x, y, image=ph, anchor="nw")
    return rrect(cv, x, y, x + w, y + h, h / 2, fill=fill, outline=fill)


# --------------------------------------------------------------------------- #
# Widgets
# --------------------------------------------------------------------------- #
class RoundButton(tk.Canvas):
    """Pill-shaped button. style: outline | solid | ghost."""

    def __init__(self, app, parent, text, command, font, pad=(12, 4), style="outline"):
        self.app, self.label_text, self.command = app, text, command
        self.font_, self.pad, self.style_, self.hover = font, pad, style, False
        self.badge = False                      # red notification dot in the top-right corner
        self.fobj = tkfont.Font(font=font)
        super().__init__(parent, bd=0, highlightthickness=0, cursor="hand2")
        self._fit()
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.bind("<Button-1>", lambda e: self.command() if self.command else None)
        self.redraw()

    def _fit(self):
        self.bw = self.fobj.measure(self.label_text) + 2 * px(self.pad[0])
        self.bh = self.fobj.metrics("linespace") + 2 * px(self.pad[1])
        tk.Canvas.configure(self, width=self.bw, height=self.bh)

    def _hover(self, on):
        self.hover = on
        self.redraw()

    def redraw(self):
        P = self.app.P
        tk.Canvas.configure(self, bg=P["bg"])
        self.delete("all")
        self._keep = []
        if self.style_ == "solid":
            fill = P["muted"] if self.hover else P["fg"]
            outline, tcol = fill, P["bg"]
        elif self.style_ == "ghost":
            fill = P["hover"] if self.hover else P["bg"]
            outline, tcol = fill, P["fg"]
        else:
            fill = P["hover"] if self.hover else P["bg"]
            outline, tcol = (P["fg"] if self.hover else P["border"]), P["fg"]
        draw_rrect(self, 0, 0, self.bw, self.bh, self.bh // 2, fill, outline, max(1, px(1)), P["bg"])
        self.create_text(self.bw / 2, self.bh / 2, text=self.label_text, font=self.font_, fill=tcol)
        if self.badge:
            d, ring = px(9), px(2)
            x, y = self.bw - px(8) - d, px(5)
            draw_pill(self, x - ring, y - ring, d + 2 * ring, d + 2 * ring, fill)        # gap around the dot
            draw_pill(self, x, y, d, d, P["alert"])

    def configure(self, cnf=None, **kw):
        if "text" in kw:
            self.label_text = kw.pop("text")
            self._fit()
        if cnf or kw:
            tk.Canvas.configure(self, cnf, **kw)
        self.redraw()

    config = configure


class Switch(tk.Canvas):
    """iOS-style on/off switch with a sliding knob."""

    def __init__(self, app, parent, value=False, command=None):
        self.W, self.H, self.D = px(44), px(26), px(20)
        super().__init__(parent, width=self.W, height=self.H, bd=0, highlightthickness=0, cursor="hand2")
        self.app, self.value, self.command = app, bool(value), command
        self.pos = 1.0 if self.value else 0.0
        self.bind("<Button-1>", lambda e: self.toggle())
        self.redraw()

    def get(self):
        return self.value

    def set(self, value):
        self.value = bool(value)
        self.pos = 1.0 if self.value else 0.0
        self.redraw()

    def toggle(self):
        self.value = not self.value
        self._animate()
        if self.command:
            self.command(self.value)

    def _animate(self):
        target = 1.0 if self.value else 0.0
        self.pos += (target - self.pos) * 0.5
        done = abs(target - self.pos) < 0.04
        if done:
            self.pos = target
        try:
            self.redraw()
            if not done:
                self.after(14, self._animate)
        except tk.TclError:
            pass

    def redraw(self):
        P, dark = self.app.P, self.app.dark
        off = "#3a3a3a" if dark else "#d9d9d9"
        knob_off, knob_on = ("#d0d0d0", "#000000") if dark else ("#ffffff", "#ffffff")
        tk.Canvas.configure(self, bg=P["bg"])
        self.delete("all")
        self._keep = []
        if can_aa():
            ph = aa_switch(self.W, self.H, self.D, self.pos, off, P["fg"], knob_off, knob_on, P["bg"])
            self._keep.append(ph)
            self.create_image(0, 0, image=ph, anchor="nw")
            return
        track = P["fg"] if self.pos >= 0.5 else off
        rrect(self, 1, 1, self.W - 1, self.H - 1, self.H / 2, fill=track, outline=track)
        m = (self.H - self.D) / 2
        x = m + self.pos * (self.W - 2 * m - self.D)
        self.create_oval(x, m, x + self.D, m + self.D, fill=knob_on if self.pos >= 0.5 else knob_off, outline="")


class PillEntry(tk.Canvas):
    """Rounded text field. Key bindings and focus go to the inner entry."""

    def __init__(self, app, parent, var, width=30, show="", font=None, big=False):
        self.app, self.font_ = app, font or app.f_norm
        f = tkfont.Font(font=self.font_)
        self.ph = f.metrics("linespace") + px(18 if big else 12)
        self.w = f.measure("0") * width + 2 * px(14)
        super().__init__(parent, height=self.ph, width=self.w, bd=0, highlightthickness=0)
        self.focused = False
        self.entry = tk.Entry(self, textvariable=var, show=show, font=self.font_, relief="flat", bd=0,
                              highlightthickness=0)
        self.win = self.create_window(self.ph / 2, self.ph / 2, window=self.entry, anchor="w")
        tk.Canvas.bind(self, "<Configure>", self._cfg)
        tk.Canvas.bind(self, "<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda e: self._focus(True))
        self.entry.bind("<FocusOut>", lambda e: self._focus(False))
        self.redraw()

    def bind(self, seq=None, func=None, add=None):
        return self.entry.bind(seq, func, add)

    def focus_set(self):
        self.entry.focus_set()

    def _focus(self, on):
        self.focused = on
        self.redraw()

    def _cfg(self, e):
        self.w = e.width
        self.itemconfigure(self.win, width=int(max(10, e.width - self.ph)))
        self.redraw()

    def redraw(self):
        P = self.app.P
        tk.Canvas.configure(self, bg=P["bg"])
        self.entry.configure(bg=P["bg"], fg=P["fg"], insertbackground=P["fg"],
                             selectbackground=P["fg"], selectforeground=P["bg"])
        self.delete("pill")
        self._keep = []
        draw_rrect(self, 0, 0, self.w, self.ph, self.ph // 2, P["bg"], P["fg"] if self.focused else P["border"],
                   max(1, px(1)), P["bg"], tags="pill")
        self.tag_lower("pill")


def _sun(d, cx, cy, D, col):
    r = 0.16 * D
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
    for k in range(8):
        a = math.radians(k * 45)
        d.line((cx + math.cos(a) * 0.27 * D, cy + math.sin(a) * 0.27 * D,
                cx + math.cos(a) * 0.40 * D, cy + math.sin(a) * 0.40 * D), fill=col, width=max(2, int(0.055 * D)))


def _moon(d, cx, cy, D, col, under):
    r = 0.28 * D
    d.ellipse((cx - 0.03 * D - r, cy - r, cx - 0.03 * D + r, cy + r), fill=col)
    r2, ox, oy = 0.24 * D, 0.11 * D, 0.09 * D
    d.ellipse((cx + ox - r2, cy - oy - r2, cx + ox + r2, cy - oy + r2), fill=under)


def aa_theme(w, h, pos, track, border, knob, icon_on, icon_off, bg):
    key = ("th", w, h, round(pos, 2), track, border, knob, icon_on, icon_off, bg)
    ph = _CACHE.get(key)
    if ph is None:
        S, bw = SS, max(1, round(UI))
        big = Image.new("RGB", (w * S, h * S), rgb(bg))
        dr = ImageDraw.Draw(big)
        dr.rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=h * S // 2, fill=rgb(border))
        dr.rounded_rectangle((bw * S, bw * S, w * S - 1 - bw * S, h * S - 1 - bw * S),
                             radius=(h // 2 - bw) * S, fill=rgb(track))
        m = max(2, int(h * 0.12))
        dd = h - 2 * m
        kx = (m + pos * (w - 2 * m - dd)) * S
        dr.ellipse((kx, m * S, kx + dd * S, (m + dd) * S), fill=rgb(knob))
        cl, cr, cy, D = (m + dd / 2) * S, (w - m - dd / 2) * S, h / 2 * S, dd * S
        sun_on_knob = pos < 0.5
        _sun(dr, cl, cy, D, rgb(icon_on if sun_on_knob else icon_off))
        _moon(dr, cr, cy, D, rgb(icon_off if sun_on_knob else icon_on), rgb(track if sun_on_knob else knob))
        ph = _remember(key, ImageTk.PhotoImage(big.resize((w, h), _resample())))
    return ph


class ThemeToggle(tk.Canvas):
    """Light/dark switch drawn as one pill with a sun and a moon. Built at the same height as the other
    top-bar controls so everything lines up."""

    def __init__(self, app, parent, value, command, height):
        self.h = int(height)
        self.w = int(self.h * 2.1)
        super().__init__(parent, width=self.w, height=self.h, bd=0, highlightthickness=0, cursor="hand2")
        self.app, self.value, self.command = app, bool(value), command
        self.pos = 1.0 if self.value else 0.0
        self.bind("<Button-1>", lambda e: self.toggle())
        self.redraw()

    def get(self):
        return self.value

    def set(self, value):
        self.value = bool(value)
        self.pos = 1.0 if self.value else 0.0
        self.redraw()

    def toggle(self):
        self.value = not self.value
        self._animate()
        if self.command:
            self.command(self.value)

    def _animate(self):
        target = 1.0 if self.value else 0.0
        self.pos += (target - self.pos) * 0.5
        done = abs(target - self.pos) < 0.04
        if done:
            self.pos = target
        try:
            self.redraw()
            if not done:
                self.after(14, self._animate)
        except tk.TclError:
            pass

    def redraw(self):
        P = self.app.P
        tk.Canvas.configure(self, bg=P["bg"])
        self.delete("all")
        self._keep = []
        if can_aa():
            ph = aa_theme(self.w, self.h, self.pos, P["hover"], P["border"], P["fg"], P["bg"], P["muted"], P["bg"])
            self._keep.append(ph)
            self.create_image(0, 0, image=ph, anchor="nw")
            return
        rrect(self, 1, 1, self.w - 1, self.h - 1, self.h / 2, fill=P["hover"], outline=P["border"])
        m = self.h * 0.12
        dd = self.h - 2 * m
        x = m + self.pos * (self.w - 2 * m - dd)
        self.create_oval(x, m, x + dd, m + dd, fill=P["fg"], outline="")


def aa_spinner(size, k, n, fg, track, bg):
    key = ("sp", size, k, n, fg, track, bg)
    ph = _CACHE.get(key)
    if ph is None:
        S = SS
        big = Image.new("RGB", (size * S, size * S), rgb(bg))
        dr = ImageDraw.Draw(big)
        pad, wid = size * 0.10 * S, max(2, int(size * 0.09 * S))
        box = (pad, pad, size * S - pad, size * S - pad)
        dr.arc(box, 0, 360, fill=rgb(track), width=wid)
        start = k * 360.0 / n
        dr.arc(box, start, start + 110, fill=rgb(fg), width=wid)
        r, c = (size * S - 2 * pad) / 2 - wid / 2, size * S / 2
        for ang in (start, start + 110):
            x, y = c + r * math.cos(math.radians(ang)), c + r * math.sin(math.radians(ang))
            dr.ellipse((x - wid / 2, y - wid / 2, x + wid / 2, y + wid / 2), fill=rgb(fg))
        ph = _remember(key, ImageTk.PhotoImage(big.resize((size, size), _resample())))
    return ph


class Spinner(tk.Canvas):
    """A small animated activity ring."""
    FRAMES = 24

    def __init__(self, app, parent, size=44):
        self.size = px(size)
        super().__init__(parent, width=self.size, height=self.size, bd=0, highlightthickness=0)
        self.app, self.k, self.job = app, 0, None
        self.redraw()

    def start(self):
        if self.job is None:
            self._tick()

    def stop(self):
        if self.job is not None:
            try:
                self.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    def _tick(self):
        self.k = (self.k + 1) % self.FRAMES
        try:
            self.redraw()
            self.job = self.after(40, self._tick)
        except tk.TclError:
            self.job = None

    def redraw(self):
        P = self.app.P
        tk.Canvas.configure(self, bg=P["bg"])
        self.delete("all")
        self._keep = []
        if can_aa():
            ph = aa_spinner(self.size, self.k, self.FRAMES, P["fg"], P["border"], P["bg"])
            self._keep.append(ph)
            self.create_image(0, 0, image=ph, anchor="nw")
        else:
            pad = self.size * 0.12
            self.create_arc(pad, pad, self.size - pad, self.size - pad, start=-self.k * 360 / self.FRAMES,
                            extent=110, style="arc", outline=P["fg"], width=max(2, px(3)))


class ProgressBar(tk.Canvas):
    """A thin rounded progress bar. set(0..1)."""

    def __init__(self, app, parent, width=320, height=6):
        self.app, self.frac = app, 0.0
        self.bh, self.bw = px(height), px(width)
        super().__init__(parent, width=self.bw, height=self.bh, bd=0, highlightthickness=0)
        tk.Canvas.bind(self, "<Configure>", self._cfg)
        self.redraw()

    def _cfg(self, e):
        self.bw = e.width
        self.redraw()

    def set(self, frac):
        self.frac = max(0.0, min(1.0, float(frac)))
        self.redraw()

    def redraw(self):
        P = self.app.P
        tk.Canvas.configure(self, bg=P["bg"])
        self.delete("all")
        self._keep = []
        draw_rrect(self, 0, 0, self.bw, self.bh, self.bh // 2, P["border"], P["border"], 0, P["bg"])
        if self.frac > 0:
            draw_rrect(self, 0, 0, max(self.bh, self.frac * self.bw), self.bh, self.bh // 2, P["fg"], P["fg"], 0, P["border"])


class SlimScrollbar(tk.Canvas):
    """A thin rounded scrollbar that only shows when there is something to scroll."""

    def __init__(self, app, parent, command):
        self.app, self.command = app, command
        self.lo, self.hi, self.drag = 0.0, 1.0, None
        super().__init__(parent, width=px(12), bd=0, highlightthickness=0)
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))

    def set(self, lo, hi):
        self.lo, self.hi = float(lo), float(hi)
        self.redraw()

    def _span(self):
        h = max(1, self.winfo_height())
        top = self.lo * h
        bot = max(self.hi * h, top + px(32))
        return h, top, bot

    def redraw(self):
        P = self.app.P
        tk.Canvas.configure(self, bg=P["bg"])
        self.delete("all")
        self._keep = []
        if self.hi - self.lo >= 0.999:
            return
        h, top, bot = self._span()
        draw_rrect(self, px(4), top, px(5), bot - top, px(2), P["border"], P["border"], 0, P["bg"])

    def _press(self, e):
        h, top, bot = self._span()
        if top <= e.y <= bot:
            self.drag = (e.y, self.lo)
        else:
            self.command("moveto", max(0.0, e.y / h - (self.hi - self.lo) / 2))

    def _move(self, e):
        if self.drag:
            h = max(1, self.winfo_height())
            self.command("moveto", max(0.0, min(1.0, self.drag[1] + (e.y - self.drag[0]) / h)))


class ScrollFrame:
    """A scrollable area with eased (smooth) wheel scrolling and a slim scrollbar."""

    def __init__(self, app, parent):
        self.app = app
        self.outer = app.frame(parent)
        self.canvas = app.reg(tk.Canvas(self.outer, bd=0, highlightthickness=0), "canvas")
        self.sb = app.reg(SlimScrollbar(app, self.outer, self.canvas.yview), "redraw")
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = app.frame(self.canvas)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resize)
        self.on_width = None
        self._target, self._animating = 0.0, False
        app.scrollers[str(self.canvas)] = self

    def _resize(self, e):
        self.canvas.itemconfigure(self.win, width=e.width)
        if self.on_width:
            self.on_width(e.width)

    def clear(self):
        for ch in self.inner.winfo_children():
            ch.destroy()
        self.canvas.yview_moveto(0)
        self._target, self._animating = 0.0, False

    def _content(self):
        box = self.canvas.bbox("all")
        total = (box[3] - box[1]) if box else 0
        return total, max(0, total - self.canvas.winfo_height())

    def scroll(self, e):
        if getattr(e, "num", None) == 4:
            d = -1
        elif getattr(e, "num", None) == 5:
            d = 1
        else:
            d = -1 if e.delta > 0 else 1
        total, room = self._content()
        if total <= 0 or room <= 0:
            return
        self._tot = total                      # measured once per wheel click, not on every animation frame
        if not self._animating:
            self._target = self.canvas.yview()[0] * total
        self._target = min(room, max(0.0, self._target + d * px(90)))
        if not self._animating:
            self._animating = True
            self._tick()

    def _tick(self):
        total = getattr(self, "_tot", 0)
        if total <= 0:
            self._animating = False
            return
        cur = self.canvas.yview()[0] * total
        diff = self._target - cur
        try:
            if abs(diff) < 1.0:
                self.canvas.yview_moveto(self._target / total)
                self._animating = False
                return
            self.canvas.yview_moveto((cur + diff * 0.28) / total)
            self.canvas.after(16, self._tick)
        except tk.TclError:
            self._animating = False


class Chart:
    """Smooth price-history line chart (oldest to newest) with a soft fill; the last point turns accent
    coloured when the price has fallen."""

    def __init__(self, app, parent, points, height=40, on_click=None):
        self.app, self.points = app, points
        self.cv = app.reg(tk.Canvas(parent, height=px(height), bd=0, highlightthickness=0), "canvas")
        self.cv.bind("<Configure>", lambda e: self.draw(e.width, e.height))
        if on_click:
            self.cv.bind("<Button-1>", lambda e: on_click())
            self.cv.configure(cursor="hand2")

    def pack(self, **kw):
        self.cv.pack(**kw)

    def draw(self, w, h):
        cv, P, pts, pad = self.cv, self.app.P, self.points, px(6)
        cv.delete("all")
        cv._keep = []
        if w < 20 or h < 10:
            return
        if len(pts) < 2:
            cv.create_line(pad, h // 2, w - pad, h // 2, fill=P["border"], dash=(2, 3))
            if pts:
                r = px(3)
                cv.create_oval(w - pad - 2 * r, h // 2 - r, w - pad, h // 2 + r, fill=P["fg"], outline=P["fg"])
            return
        lo, hi, n = min(pts), max(pts), len(pts)
        coords = []
        for i, v in enumerate(pts):
            x = pad + (w - 2 * pad) * i / (n - 1)
            y = h / 2 if hi == lo else (h - pad) - (h - 2 * pad) * (v - lo) / (hi - lo)
            coords.append((x, y))
        dot = P["accent"] if pts[-1] < pts[0] else P["fg"]
        if can_aa() and w > 0 and h > 0:
            S = SS
            big = Image.new("RGB", (w * S, h * S), rgb(P["bg"]))
            dr = ImageDraw.Draw(big)
            tint = mix(rgb(P["bg"]), rgb(P["fg"]), 0.07)
            dr.polygon([(x * S, y * S) for x, y in coords] + [(coords[-1][0] * S, h * S), (coords[0][0] * S, h * S)],
                       fill=tint)
            line = [(x * S, y * S) for x, y in coords]
            try:
                dr.line(line, fill=rgb(P["fg"]), width=max(S, int(1.7 * UI * S)), joint="curve")
            except TypeError:
                dr.line(line, fill=rgb(P["fg"]), width=max(S, int(1.7 * UI * S)))
            if n <= 24:
                rr = 2.2 * UI * S
                for x, y in coords[:-1]:
                    dr.ellipse((x * S - rr, y * S - rr, x * S + rr, y * S + rr), fill=rgb(P["bg"]), outline=rgb(P["fg"]),
                               width=max(1, int(UI * S * 0.8)))
            x, y = coords[-1]
            ro, ri = 4.6 * UI * S, 3.2 * UI * S
            dr.ellipse((x * S - ro, y * S - ro, x * S + ro, y * S + ro), fill=rgb(P["bg"]))
            dr.ellipse((x * S - ri, y * S - ri, x * S + ri, y * S + ri), fill=rgb(dot))
            ph = ImageTk.PhotoImage(big.resize((w, h), _resample()))
            cv._keep.append(ph)
            cv.create_image(0, 0, image=ph, anchor="nw")
            return
        flat = [c for xy in coords for c in xy]
        cv.create_line(*flat, fill=P["fg"], width=max(1, px(1)))
        x, y = coords[-1]
        r = px(3)
        cv.create_oval(x - r, y - r, x + r, y + r, fill=dot, outline=dot)


# --------------------------------------------------------------------------- #
# Window chrome
# --------------------------------------------------------------------------- #
def style_titlebar(win, dark: bool, bg: str, fg: str, border: str):
    """Make the Windows title bar match the app (dark mode + caption colours on Windows 11)."""
    if sys.platform != "win32":
        return
    try:
        win.update_idletasks()
        hwnd = int(win.wm_frame(), 16)
        dwm = ctypes.windll.dwmapi

        def attr(a, v):
            dwm.DwmSetWindowAttribute(hwnd, a, ctypes.byref(ctypes.c_int(v)), 4)

        def colorref(h):
            r, g, b = rgb(h)
            return r | (g << 8) | (b << 16)

        for a in (20, 19):                                 # immersive dark mode (20 = current, 19 = early Win10)
            attr(a, 1 if dark else 0)
        attr(35, colorref(bg))                             # caption colour (Windows 11)
        attr(36, colorref(fg))                             # caption text
        attr(34, colorref(border))                         # window border
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)   # repaint the frame
    except Exception:  # noqa: BLE001
        pass


def make_icon(size: int = 256):
    """A black rounded square with a white D and a small emerald dot."""
    if not HAS_PIL:
        return None
    S, n = 4, size * 4
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink = (10, 10, 10, 255)
    d.rounded_rectangle((0, 0, n - 1, n - 1), radius=int(n * 0.22), fill=ink)
    x0, y0, x1, y1 = n * 0.30, n * 0.25, n * 0.72, n * 0.75
    r = (y1 - y0) / 2
    d.rectangle((x0, y0, x1 - r, y1), fill="white")
    d.pieslice((x1 - 2 * r, y0, x1, y1), -90, 90, fill="white")
    t = n * 0.085
    ir = r - t
    d.rectangle((x0 + t, y0 + t, x1 - r, y1 - t), fill=ink)
    d.pieslice((x1 - r - ir, y0 + t, x1 - r + ir, y1 - t), -90, 90, fill=ink)
    dr = n * 0.075
    d.ellipse((n * 0.80 - dr, n * 0.22 - dr, n * 0.80 + dr, n * 0.22 + dr), fill=(16, 185, 129, 255))
    return im.resize((size, size), _resample())
