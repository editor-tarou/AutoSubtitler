#!/usr/bin/env python3
"""
autosubtitle_gui.py — Smart subtitle generator with presets & Premiere XML export

Requirements:
    pip install openai-whisper torch stable-ts

Run:
    python autosubtitle_gui.py
"""

import os, re, sys, json, threading, tkinter as tk, base64
from tkinter import filedialog, colorchooser, messagebox, font as tkfont
from pathlib import Path



# ── paths ─────────────────────────────────────────────────────────────────────

APP_DIR      = Path(os.path.dirname(os.path.abspath(__file__)))
PRESETS_FILE = APP_DIR / "presets.json"

AUTHOR = 'Made by Kormány "EditorTarou" Róbert Károly  •  2026 04 20'

# Embedded 32×32 app icon (PNG, base64)
_ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAASklEQVR4nGPgpzFgoJMFL/67Ux2N"
    "WkCaBTSP5OFiwQcqgWFsAS3AUIjkEWUBLcBQiGT8YTXMLKAFGLUAAmheJ49aMPAW4AE0twAAyQjN"
    "GD3kLboAAAAASUVORK5CYII="
)


# ── dependency check ──────────────────────────────────────────────────────────

def check_dependencies():
    missing = []
    for pkg, imp in [("openai-whisper","whisper"), ("torch","torch"), ("stable-ts","stable_whisper")]:
        try:
            __import__(imp)
        except ImportError:
            missing.append(pkg)
    return missing


# ── font enumeration ──────────────────────────────────────────────────────────

_SYSTEM_FONTS = None

def get_system_fonts():
    global _SYSTEM_FONTS
    if _SYSTEM_FONTS is None:
        try:
            families = sorted(set(tkfont.families()))
        except Exception:
            families = ["Arial", "Georgia", "Impact", "Helvetica", "Verdana"]
        _SYSTEM_FONTS = [f for f in families if f and not f.startswith("@")]
    return _SYSTEM_FONTS


# ── preset defaults ───────────────────────────────────────────────────────────

PRESET_DEFAULTS = {
    "caps": False, "letter_spacing": 0, "line_height": 100,
    "x_offset": 50, "y_offset": 85, "text_align": "Center", "max_width": 80,
    "safe_zone": True, "show_safe_zone": False,
}

DEFAULT_PRESETS = [
    {**PRESET_DEFAULTS,
     "name":"Clean White","font":"Arial","size":72,"bold":False,"italic":False,
     "color":"#FFFFFF","outline":True,"outline_color":"#000000","outline_w":4,
     "shadow":False,"shadow_color":"#000000","position":"bottom","builtin":True},
    {**PRESET_DEFAULTS,
     "name":"Bold Impact","font":"Impact","size":88,"bold":True,"italic":False,
     "color":"#FFFF00","outline":True,"outline_color":"#000000","outline_w":6,
     "shadow":False,"shadow_color":"#000000","position":"bottom","builtin":True},
    {**PRESET_DEFAULTS,
     "name":"Cinematic","font":"Georgia","size":64,"bold":False,"italic":True,
     "color":"#FFFFFF","outline":False,"outline_color":"#000000","outline_w":3,
     "shadow":True,"shadow_color":"#000000","position":"bottom","builtin":True},
    {**PRESET_DEFAULTS,
     "name":"Minimal Top","font":"Helvetica Neue","size":60,"bold":False,"italic":False,
     "color":"#FFFFFF","outline":True,"outline_color":"#333333","outline_w":2,
     "shadow":False,"shadow_color":"#000000","position":"top","builtin":True,
     "y_offset":10},
]


def load_presets():
    if PRESETS_FILE.exists():
        try:
            presets = json.loads(PRESETS_FILE.read_text())
            for p in presets:
                for k, v in PRESET_DEFAULTS.items():
                    p.setdefault(k, v)
            return presets
        except Exception:
            pass
    return [dict(p) for p in DEFAULT_PRESETS]


def save_presets(presets):
    PRESETS_FILE.write_text(json.dumps(presets, indent=2))


# ── segmentation ──────────────────────────────────────────────────────────────

SEG_STYLES = {
    "Punchy  - 1-3 words":    {"max_words": 3,  "pause_gap": 0.15},
    "Balanced - 3-5 words":   {"max_words": 5,  "pause_gap": 0.30},
    "Full - natural phrases": {"max_words": 10, "pause_gap": 0.50},
}
MODELS = ["tiny", "base", "small", "medium", "large"]


def segment_words(words, cfg):
    max_words, pause_gap = cfg["max_words"], cfg["pause_gap"]
    phrases, current = [], []
    for w in words:
        word = w["word"].strip()
        if not word:
            continue
        if current and w["start"] - current[-1]["end"] >= pause_gap:
            phrases.append(current); current = []
        current.append({"word": word, "start": w["start"], "end": w["end"]})
        if re.search(r"[.,!?;:]$", word):
            phrases.append(current); current = []
    if current:
        phrases.append(current)
    cards = []
    for phrase in phrases:
        while len(phrase) > max_words:
            cards.append(phrase[:max_words]); phrase = phrase[max_words:]
        if phrase:
            cards.append(phrase)
    return cards


# ── subtitle export (SRT / VTT) ───────────────────────────────────────────────

def _fmt_srt_ts(s):
    """Seconds → HH:MM:SS,mmm"""
    ms  = int(round(s * 1000))
    hh  = ms // 3_600_000;  ms -= hh * 3_600_000
    mm  = ms //    60_000;  ms -= mm *    60_000
    ss  = ms //     1_000;  ms -= ss *     1_000
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _fmt_vtt_ts(s):
    """Seconds → HH:MM:SS.mmm  (WebVTT uses dot, not comma)"""
    return _fmt_srt_ts(s).replace(",", ".")


def _card_times(cards, i):
    """Return (start_sec, end_sec) for card i."""
    start = cards[i][0]["start"]
    end   = cards[i+1][0]["start"] if i + 1 < len(cards) else cards[i][-1]["end"]
    # ensure minimum 100 ms duration so Premiere doesn't drop the cue
    if end - start < 0.1:
        end = start + 0.1
    return start, end


def cards_to_srt(cards, preset):
    """Standard SRT — universally supported, Premiere imports via Captions > SRT."""
    caps = preset.get("caps", False)
    lines = []
    for i, card in enumerate(cards):
        text  = " ".join(w["word"] for w in card).strip()
        if caps:
            text = text.upper()
        start, end = _card_times(cards, i)
        lines.append(str(i + 1))
        lines.append(f"{_fmt_srt_ts(start)} --> {_fmt_srt_ts(end)}")
        lines.append(text)
        lines.append("")          # blank line between cues
    return "\n".join(lines)


def cards_to_vtt(cards, preset):
    """WebVTT — supports inline positioning cues for Premiere's caption track."""
    caps  = preset.get("caps", False)
    x_off = preset.get("x_offset", 50)
    y_off = preset.get("y_offset", 85)
    align = preset.get("text_align", "Center").lower()

    lines = ["WEBVTT", ""]
    for i, card in enumerate(cards):
        text  = " ".join(w["word"] for w in card).strip()
        if caps:
            text = text.upper()
        start, end = _card_times(cards, i)

        # VTT positioning cue settings
        pos_line = f"line:{y_off}% position:{x_off}% align:{align}"
        lines.append(f"{i + 1}")
        lines.append(f"{_fmt_vtt_ts(start)} --> {_fmt_vtt_ts(end)} {pos_line}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


# ── design tokens ─────────────────────────────────────────────────────────────

BG       = "#0f0f0f"
SURFACE  = "#1a1a1a"
SURFACE2 = "#242424"
SURFACE3 = "#2e2e2e"
BORDER   = "#363636"
ACCENT   = "#e8ff47"
TEXT     = "#f0f0f0"
MUTED    = "#606060"
MUTED2   = "#484848"
SUCCESS  = "#4ade80"
ERROR    = "#f87171"

FUI   = ("Segoe UI", 10)
FMONO = ("Consolas", 10)
FBIG  = ("Segoe UI", 17, "bold")
FSM   = ("Segoe UI", 9)
FXSM  = ("Segoe UI", 8)
FBOLD = ("Segoe UI", 10, "bold")

PREVIEW_TEXT    = "This is a subtitle preview"

# 3×3 grid: (label, x, y)
GRID_POSITIONS = [
    ("top-left",     0,  10), ("top-center",    50,  10), ("top-right",   100,  10),
    ("mid-left",     0,  50), ("mid-center",    50,  50), ("mid-right",   100,  50),
    ("bottom-left",  0,  85), ("bottom-center", 50,  85), ("bottom-right",100,  85),
]


# ── splash screen ─────────────────────────────────────────────────────────────

class SplashScreen(tk.Toplevel):
    """Animated frameless splash screen shown while the app initialises."""
    W, H = 460, 295

    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=BG)
        self.attributes("-topmost", True)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{self.W}x{self.H}+{(sw-self.W)//2}+{(sh-self.H)//2}")

        # Outer accent border
        outer = tk.Frame(self, bg=ACCENT, padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=BG)
        inner.pack(fill="both", expand=True)

        # Top accent stripe
        tk.Frame(inner, bg=ACCENT, height=4).pack(fill="x")

        body = tk.Frame(inner, bg=BG)
        body.pack(fill="both", expand=True, padx=38, pady=28)

        # Logo
        row = tk.Frame(body, bg=BG)
        row.pack(anchor="w")
        tk.Label(row, text="Auto",     font=("Segoe UI",28,"bold"), bg=BG, fg=TEXT  ).pack(side="left")
        tk.Label(row, text="Subtitle", font=("Segoe UI",28,"bold"), bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(row, text=" *",       font=("Segoe UI",28,"bold"), bg=BG, fg=ACCENT).pack(side="left")

        tk.Label(body, text="Smart subtitles for Adobe Premiere Pro",
                 font=FSM, bg=BG, fg=MUTED).pack(anchor="w", pady=(4, 0))

        tk.Frame(body, bg=BG, height=22).pack()

        self._status_var = tk.StringVar(value="Starting…")
        tk.Label(body, textvariable=self._status_var,
                 font=FXSM, bg=BG, fg=MUTED).pack(anchor="w")

        # Progress bar (canvas-based so we can animate it precisely)
        pb_wrap = tk.Frame(body, bg=BORDER, height=4)
        pb_wrap.pack(fill="x", pady=(6, 0))
        pb_wrap.pack_propagate(False)
        self._pb = tk.Canvas(pb_wrap, bg=BORDER, height=4, highlightthickness=0, bd=0)
        self._pb.pack(fill="both", expand=True)
        self._bar = self._pb.create_rectangle(0, 0, 0, 4, fill=ACCENT, outline="")
        self._progress = 0.0
        self._target   = 0.0
        self._anim_id  = None

        tk.Frame(body, bg=BG, height=16).pack()
        tk.Label(body, text=AUTHOR, font=FXSM, bg=BG, fg=MUTED2).pack(anchor="w")

        self.update()

    def advance_to(self, frac, msg=""):
        self._target = min(1.0, frac)
        self._status_var.set(msg)
        if self._anim_id:
            self.after_cancel(self._anim_id)
        self._step()

    def _step(self):
        if self._progress < self._target:
            self._progress = min(self._progress + 0.018, self._target)
            self._draw_bar()
            self._anim_id = self.after(16, self._step)
        else:
            self.update()

    def _draw_bar(self):
        self._pb.update_idletasks()
        w = self._pb.winfo_width()
        if w > 1:
            self._pb.coords(self._bar, 0, 0, int(w * self._progress), 4)
        self.update()

    def close(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
        self.destroy()


# ── tutorial overlay ──────────────────────────────────────────────────────────

class TutorialOverlay(tk.Toplevel):
    """Dynamic step-by-step tutorial with spotlight, pulse & typing animation."""

    CARD_W = 300
    CARD_H = 215
    MARGIN = 14
    PAD    = 8
    TRANS  = "#fe01fe"   # key color made transparent on Windows

    def __init__(self, app):
        super().__init__(app)
        self.app        = app
        self.step_index = 0
        self._pulse_job = None
        self._type_job  = None
        self._pulse_ph  = 0.0
        self._pulse_rect = None

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.wm_attributes("-transparentcolor", self.TRANS)
        except Exception:
            pass

        self._sync()
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.steps = self._build_steps()
        self._render_step()
        self._pulse_loop()

    # ── geometry ──────────────────────────────────────────────────────────────

    def _sync(self):
        self.app.update_idletasks()
        x = self.app.winfo_rootx()
        y = self.app.winfo_rooty()
        w = self.app.winfo_width()
        h = self.app.winfo_height()
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._W, self._H = w, h

    # ── steps ─────────────────────────────────────────────────────────────────

    def _build_steps(self):
        a = self.app
        return [
            {"w": lambda: a._file_label,
             "title": "📁  File Picker",
             "body": "Click this area to browse and load your audio or video file.\nSupports MP3, MP4, WAV, M4A, MOV, AAC, FLAC and more."},
            {"w": lambda: a._pmenu,
             "title": "🎨  Caption Preset",
             "body": "Choose a visual style for your captions. Each preset defines the font, size, colour, outline and screen position."},
            {"w": lambda: a._edit_btn,
             "title": "✏️  Preset Controls",
             "body": "New — create a custom style from scratch.\nEdit — tweak the selected preset.\nDelete — remove a custom preset permanently."},
            {"w": lambda: a._preview,
             "title": "👁  Style Summary",
             "body": "A live summary of the active preset: font name, size, colour, outline and shadow settings shown at a glance."},
            {"w": lambda: a._seg_om,
             "title": "✂️  Segmentation Style",
             "body": "Controls how many words appear per subtitle card.\n• Punchy = 1-3 words  (fast cuts)\n• Balanced = 3-5 words  (recommended)\n• Full = natural phrases"},
            {"w": lambda: a._model_om,
             "title": "🧠  Whisper Model",
             "body": "Larger models are more accurate but slower.\n• tiny / base — quick preview\n• medium — best daily balance\n• large — maximum accuracy"},
            {"w": lambda: a._lang_om,
             "title": "🌐  Language",
             "body": "Set the spoken language to improve accuracy, or leave on 'auto' and Whisper will detect it automatically from the audio."},
            {"w": lambda: a._fmt_frame,
             "title": "📄  Output Format",
             "body": "SRT — universal, import directly into Premiere via a caption track.\nVTT — embeds precise X / Y position cues from your preset."},
            {"w": lambda: a._btn,
             "title": "🚀  Generate!",
             "body": "Click to start transcription. The subtitle file is saved next to your source with _captions.srt or .vtt appended to the filename."},
            {"w": lambda: a._log,
             "title": "📋  Log Output",
             "body": "Live progress and status messages appear here during transcription. Errors, word counts and Premiere tips all show in this panel."},
        ]

    # ── widget rect ───────────────────────────────────────────────────────────

    def _wrect(self, widget):
        widget.update_idletasks()
        ox = self.app.winfo_rootx()
        oy = self.app.winfo_rooty()
        return (widget.winfo_rootx() - ox,
                widget.winfo_rooty() - oy,
                widget.winfo_width(),
                widget.winfo_height())

    # ── render ────────────────────────────────────────────────────────────────

    def _render_step(self):
        if self._type_job:
            self.after_cancel(self._type_job)
            self._type_job = None
        self.canvas.delete("all")
        self._pulse_rect = None

        step = self.steps[self.step_index]
        try:
            widget = step["w"]()
        except Exception:
            self._next(); return

        OW, OH = self._W, self._H
        wx, wy, ww, wh = self._wrect(widget)

        P  = self.PAD
        sx = max(0, wx - P);      sy = max(0, wy - P)
        sr = min(OW, wx+ww+P);    sb = min(OH, wy+wh+P)

        # ── 4-rect dark overlay around spotlight ──────────────────────────────
        DARK = "#0a0a0a"
        self.canvas.create_rectangle(0,  0,  OW, sy,  fill=DARK, outline="")
        self.canvas.create_rectangle(0,  sb, OW, OH,  fill=DARK, outline="")
        self.canvas.create_rectangle(0,  sy, sx, sb,  fill=DARK, outline="")
        self.canvas.create_rectangle(sr, sy, OW, sb,  fill=DARK, outline="")

        # ── Spotlight hole (transparent on Windows, absent on others) ─────────
        self.canvas.create_rectangle(sx, sy, sr, sb,
                                     fill=self.TRANS, outline="")

        # ── Animated pulse border ─────────────────────────────────────────────
        self._pulse_rect = self.canvas.create_rectangle(
            sx-3, sy-3, sr+3, sb+3, outline=ACCENT, width=2, fill="")

        # ── Skip button ───────────────────────────────────────────────────────
        skip = self.canvas.create_text(OW-14, 14,
                                       text="✕  Skip Tutorial",
                                       font=FSM, fill=MUTED, anchor="ne")
        skip_bg = self.canvas.create_rectangle(
            *self.canvas.bbox(skip), fill=DARK, outline="")
        self.canvas.tag_lower(skip_bg, skip)
        for tag in (skip, skip_bg):
            self.canvas.tag_bind(tag, "<Button-1>", lambda e: self._close())
            self.canvas.tag_bind(tag, "<Enter>",
                lambda e: self.canvas.itemconfig(skip, fill=TEXT))
            self.canvas.tag_bind(tag, "<Leave>",
                lambda e: self.canvas.itemconfig(skip, fill=MUTED))

        # ── Card placement ────────────────────────────────────────────────────
        cx, cy = self._card_pos(sx, sy, sr-sx, sb-sy, OW, OH)
        CW, CH = self.CARD_W, self.CARD_H
        cpad   = 16

        # Card shadow
        self.canvas.create_rectangle(cx+4, cy+4, cx+CW+4, cy+CH+4,
                                     fill="#000000", outline="")
        # Card body
        self.canvas.create_rectangle(cx, cy, cx+CW, cy+CH,
                                     fill=SURFACE, outline=BORDER, width=1)
        # Accent top stripe
        self.canvas.create_rectangle(cx, cy, cx+CW, cy+3,
                                     fill=ACCENT, outline="")

        # Counter
        total   = len(self.steps)
        counter = f"Step {self.step_index+1} of {total}"
        self.canvas.create_text(cx+cpad, cy+cpad+2,
                                text=counter, font=FXSM, fill=MUTED, anchor="w")

        # Title (typing animation)
        title_id = self.canvas.create_text(
            cx+cpad, cy+cpad+18,
            text="", font=FBOLD, fill=ACCENT, anchor="w")
        self._type_text(title_id, step["title"], speed=22)

        # Body
        self.canvas.create_text(
            cx+cpad, cy+cpad+40,
            text=step["body"], font=FSM, fill=TEXT,
            anchor="nw", width=CW - cpad*2)

        # Subtle connector line
        mid_sx = (sx+sr)//2;  mid_sy = (sy+sb)//2
        mid_cx = cx + CW//2;  mid_cy = cy + CH//2
        self.canvas.create_line(mid_sx, mid_sy, mid_cx, mid_cy,
                                fill=MUTED2, dash=(3, 6), width=1)

        # ── Progress dots ─────────────────────────────────────────────────────
        dot_y = cy + CH - 14
        ds    = 11
        dx0   = cx + CW//2 - (total*ds)//2
        for i in range(total):
            col = ACCENT if i == self.step_index else SURFACE3
            self.canvas.create_oval(dx0+i*ds, dot_y-3,
                                    dx0+i*ds+6, dot_y+3,
                                    fill=col, outline="")

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_y   = cy + CH - 46
        is_last = (self.step_index == total - 1)

        if self.step_index > 0:
            self._draw_btn(cx+cpad,       btn_y, 72, 26,
                           "← Back", SURFACE2, BORDER, TEXT, self._prev)

        lbl = "✓  Done" if is_last else "Next  →"
        self._draw_btn(cx+CW-cpad-82, btn_y, 82, 26,
                       lbl, ACCENT, "", "#0f0f0f", self._next)

    # ── button helper ─────────────────────────────────────────────────────────

    def _draw_btn(self, x, y, w, h, text, bg, outline, fg, cmd):
        r = self.canvas.create_rectangle(x, y, x+w, y+h,
                                         fill=bg, outline=outline or bg,
                                         width=1 if outline else 0)
        t = self.canvas.create_text(x+w//2, y+h//2, text=text,
                                    font=FSM, fill=fg)
        hover_bg = SURFACE3 if bg != ACCENT else "#d4eb2a"
        for tag in (r, t):
            self.canvas.tag_bind(tag, "<Button-1>", lambda e, c=cmd: c())
            self.canvas.tag_bind(tag, "<Enter>",
                lambda e, rid=r: self.canvas.itemconfig(rid, fill=hover_bg))
            self.canvas.tag_bind(tag, "<Leave>",
                lambda e, rid=r, orig=bg: self.canvas.itemconfig(rid, fill=orig))

    # ── typing animation ──────────────────────────────────────────────────────

    def _type_text(self, item_id, full_text, i=0, speed=22):
        if i <= len(full_text):
            try:
                self.canvas.itemconfig(item_id, text=full_text[:i])
            except Exception:
                return
            if i < len(full_text):
                self._type_job = self.after(
                    speed, lambda: self._type_text(item_id, full_text, i+1, speed))

    # ── pulse animation ───────────────────────────────────────────────────────

    def _pulse_loop(self):
        import math
        self._pulse_ph = (self._pulse_ph + 0.12) % (2*math.pi)
        t = (math.sin(self._pulse_ph) + 1) / 2
        r = min(255, int(0xe8 + t*0x17))
        g = 255
        b = min(255, int(0x47 + t*0x30))
        color = f"#{r:02x}{g:02x}{b:02x}"
        width = 2 + t*2
        if self._pulse_rect:
            try:
                self.canvas.itemconfig(self._pulse_rect,
                                       outline=color, width=width)
            except Exception:
                pass
        self._pulse_job = self.after(40, self._pulse_loop)

    # ── card placement ────────────────────────────────────────────────────────

    def _card_pos(self, sx, sy, sw, sh, OW, OH):
        CW, CH, M = self.CARD_W, self.CARD_H, self.MARGIN
        if sx + sw + M + CW <= OW:            # right
            return sx+sw+M, max(8, min(sy+sh//2-CH//2, OH-CH-8))
        if sx - M - CW >= 0:                   # left
            return sx-M-CW, max(8, min(sy+sh//2-CH//2, OH-CH-8))
        cx = max(8, min(sx+sw//2-CW//2, OW-CW-8))
        if sy + sh + M + CH <= OH:             # below
            return cx, sy+sh+M
        return cx, max(8, sy-M-CH)             # above

    # ── navigation ───────────────────────────────────────────────────────────

    def _next(self):
        if self.step_index < len(self.steps)-1:
            self.step_index += 1
            self._render_step()
        else:
            self._close()

    def _prev(self):
        if self.step_index > 0:
            self.step_index -= 1
            self._render_step()

    def _close(self):
        for job in (self._pulse_job, self._type_job):
            if job:
                try: self.after_cancel(job)
                except: pass
        self.destroy()


# ── scrollable frame ──────────────────────────────────────────────────────────

class ScrollFrame(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        bg = kw.get("bg", BG)
        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._sb = tk.Scrollbar(self, orient="vertical",
                                command=self._canvas.yview,
                                bg=SURFACE2, troughcolor=BG,
                                relief="flat", bd=0, width=6,
                                highlightthickness=0)
        self.inner = tk.Frame(self._canvas, bg=bg)
        self._win = self._canvas.create_window((0,0), window=self.inner, anchor="nw")
        self._canvas.configure(yscrollcommand=self._sb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._sb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Enter>", self._bind_wheel)
        self._canvas.bind("<Leave>", self._unbind_wheel)

    def _on_inner_configure(self, e):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._win, width=e.width)

    def _bind_wheel(self, e):
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, e):
        self._canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, e):
        self._canvas.yview_scroll(int(-1*(e.delta/120)), "units")


# ── preset editor ─────────────────────────────────────────────────────────────

class PresetEditor(tk.Toplevel):
    def __init__(self, parent, preset=None, on_save=None):
        super().__init__(parent)
        self.title("Edit Preset")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("870x660")
        self.on_save = on_save
        self.grab_set()

        p = preset or {**PRESET_DEFAULTS,
            "name":"My Preset","font":"Arial","size":72,"bold":False,"italic":False,
            "color":"#FFFFFF","outline":True,"outline_color":"#000000","outline_w":4,
            "shadow":False,"shadow_color":"#000000","position":"bottom","builtin":False}
        for k, v in PRESET_DEFAULTS.items():
            p.setdefault(k, v)

        self.vars = {
            "name":           tk.StringVar(value=p["name"]),
            "font":           tk.StringVar(value=p["font"]),
            "size":           tk.IntVar(value=p["size"]),
            "bold":           tk.BooleanVar(value=p.get("bold", False)),
            "italic":         tk.BooleanVar(value=p.get("italic", False)),
            "caps":           tk.BooleanVar(value=p.get("caps", False)),
            "letter_spacing": tk.IntVar(value=p.get("letter_spacing", 0)),
            "line_height":    tk.IntVar(value=p.get("line_height", 100)),
            "color":          tk.StringVar(value=p.get("color","#FFFFFF")),
            "outline":        tk.BooleanVar(value=p.get("outline",True)),
            "outline_color":  tk.StringVar(value=p.get("outline_color","#000000")),
            "outline_w":      tk.IntVar(value=p.get("outline_w",4)),
            "shadow":         tk.BooleanVar(value=p.get("shadow",False)),
            "shadow_color":   tk.StringVar(value=p.get("shadow_color","#000000")),
            "position":       tk.StringVar(value=p.get("position","bottom")),
            "x_offset":       tk.IntVar(value=p.get("x_offset",50)),
            "y_offset":       tk.IntVar(value=p.get("y_offset",85)),
            "text_align":     tk.StringVar(value=p.get("text_align","Center")),
            "max_width":      tk.IntVar(value=p.get("max_width",80)),
            "safe_zone":      tk.BooleanVar(value=p.get("safe_zone",True)),
            "show_safe_zone": tk.BooleanVar(value=p.get("show_safe_zone",False)),
        }

        for v in self.vars.values():
            v.trace_add("write", lambda *_: self.after_idle(self._refresh_preview))

        self._tab_frames = {}
        self._tab_btns   = {}
        self._grid_btns  = {}
        self._active_tab = "Style"

        self._build_shell()
        self._show_tab("Style")
        self.after(100, self._refresh_preview)

    # ── shell (header + tabs + footer) ───────────────────────────────────────

    def _build_shell(self):
        # ── Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=22, pady=(18, 0))
        tk.Label(hdr, text="Edit Preset", font=FBIG, bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text=" — ", font=FBIG, bg=BG, fg=MUTED).pack(side="left")
        tk.Label(hdr, textvariable=self.vars["name"], font=FBIG, bg=BG, fg=ACCENT).pack(side="left")

        # Name row
        nr = tk.Frame(self, bg=BG)
        nr.pack(fill="x", padx=22, pady=(6, 14))
        tk.Label(nr, text="Name", font=FSM, bg=BG, fg=MUTED, width=6, anchor="w").pack(side="left")
        tk.Entry(nr, textvariable=self.vars["name"], font=FUI,
                 bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", bd=0, highlightthickness=1,
                 highlightbackground=BORDER, width=30).pack(side="left", ipady=5, ipadx=6)

        # ── Tab bar
        tab_bar = tk.Frame(self, bg=BG)
        tab_bar.pack(fill="x", padx=22)

        for name in ("Style", "Position"):
            frame = tk.Frame(tab_bar, bg=BG)
            frame.pack(side="left")
            btn = tk.Button(frame, text=name,
                            font=("Segoe UI", 10),
                            relief="flat", bd=0, padx=14, pady=8,
                            cursor="hand2", bg=BG,
                            command=lambda n=name: self._show_tab(n))
            btn.pack(side="left")
            self._tab_btns[name] = btn

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Content area
        self._content_area = tk.Frame(self, bg=BG)
        self._content_area.pack(fill="both", expand=True)

        self._tab_frames["Style"]    = self._build_style_tab(self._content_area)
        self._tab_frames["Position"] = self._build_position_tab(self._content_area)

        # ── Footer
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=22, pady=12)
        tk.Button(foot, text="Save Preset", font=FBOLD,
                  bg=ACCENT, fg="#0f0f0f",
                  activebackground="#d4eb2a", activeforeground="#0f0f0f",
                  relief="flat", bd=0, padx=22, pady=10, cursor="hand2",
                  command=self._save).pack(side="left", padx=(0,8))
        tk.Button(foot, text="Cancel", font=FBOLD,
                  bg=SURFACE2, fg=TEXT,
                  activebackground=SURFACE3, activeforeground=TEXT,
                  relief="flat", bd=0, padx=22, pady=10, cursor="hand2",
                  command=self.destroy).pack(side="left")
        tk.Label(foot, text="* Premiere XML will include all style properties",
                 font=FXSM, bg=BG, fg=MUTED).pack(side="right")

    def _show_tab(self, name):
        for n, f in self._tab_frames.items():
            f.place_forget()
        self._tab_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)
        self._active_tab = name
        for n, btn in self._tab_btns.items():
            if n == name:
                btn.config(fg=ACCENT, activeforeground=ACCENT)
            else:
                btn.config(fg=MUTED, activeforeground=TEXT)

    # ── widget helpers ────────────────────────────────────────────────────────

    def _color_widget(self, parent, var):
        """Swatch + hex entry."""
        f = tk.Frame(parent, bg=BG)
        swatch = tk.Label(f, bg=var.get(), width=2, cursor="hand2",
                          relief="flat", bd=0)
        swatch.pack(side="left", padx=(0,6), ipady=6, ipadx=3)
        entry = tk.Entry(f, textvariable=var, font=FUI,
                         bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
                         relief="flat", bd=0, highlightthickness=1,
                         highlightbackground=BORDER, width=9)
        entry.pack(side="left", ipady=5, ipadx=4)

        def pick(_=None):
            c = colorchooser.askcolor(color=var.get(), parent=self)
            if c and c[1]:
                var.set(c[1].upper())
        swatch.bind("<Button-1>", pick)

        def sync_swatch(*_):
            try: swatch.config(bg=var.get())
            except Exception: pass
        var.trace_add("write", sync_swatch)
        return f

    def _pill_toggle(self, parent, text, var):
        """Boolean toggle pill."""
        btn = tk.Button(parent, text=text, font=("Segoe UI", 9),
                        relief="flat", bd=0, padx=11, pady=5, cursor="hand2")
        def refresh(*_):
            if var.get():
                btn.config(bg=ACCENT, fg="#0f0f0f",
                           activebackground=ACCENT, activeforeground="#0f0f0f")
            else:
                btn.config(bg=SURFACE3, fg=TEXT,
                           activebackground=SURFACE2, activeforeground=TEXT)
        var.trace_add("write", refresh)
        refresh()
        btn.config(command=lambda: var.set(not var.get()))
        return btn

    def _option_pills(self, parent, options, var):
        """Mutually exclusive pill group."""
        f = tk.Frame(parent, bg=BG)
        btns = {}

        def select(val):
            var.set(val)
            for v, b in btns.items():
                if v == val:
                    b.config(bg=ACCENT, fg="#0f0f0f",
                             activebackground=ACCENT, activeforeground="#0f0f0f")
                else:
                    b.config(bg=SURFACE3, fg=TEXT,
                             activebackground=SURFACE2, activeforeground=TEXT)

        for label in options:
            is_active = (var.get() == label)
            b = tk.Button(f, text=label,
                          font=("Segoe UI", 9),
                          bg=ACCENT if is_active else SURFACE3,
                          fg="#0f0f0f" if is_active else TEXT,
                          activebackground=ACCENT if is_active else SURFACE2,
                          activeforeground="#0f0f0f" if is_active else TEXT,
                          relief="flat", bd=0, padx=11, pady=5, cursor="hand2",
                          command=lambda v=label: select(v))
            b.pack(side="left", padx=(0,4))
            btns[label] = b

        return f

    def _spinbox(self, parent, var, from_, to, width=5):
        sb = tk.Spinbox(parent, from_=from_, to=to, textvariable=var,
                        font=FUI, bg=SURFACE2, fg=TEXT,
                        buttonbackground=SURFACE3,
                        relief="flat", bd=0,
                        highlightthickness=1, highlightbackground=BORDER,
                        width=width, insertbackground=ACCENT)
        sb.pack(side="left", ipady=4, padx=(0,8))
        return sb

    def _section_lbl(self, parent, text):
        tk.Label(parent, text=text, font=("Segoe UI", 8),
                 bg=BG, fg=MUTED).pack(anchor="w", pady=(14,6))

    def _dur_row(self, parent, var):
        r = tk.Frame(parent, bg=BG)
        r.pack(fill="x", pady=(0,8))
        tk.Label(r, text="Duration", font=FSM, bg=BG, fg=MUTED,
                 width=10, anchor="w").pack(side="left")
        s = tk.Scale(r, variable=var, from_=0.05, to=2.0, resolution=0.05,
                     orient="horizontal", bg=BG, fg=TEXT, troughcolor=SURFACE2,
                     highlightthickness=0, bd=0, length=180,
                     sliderrelief="flat", sliderlength=10, showvalue=False)
        s.pack(side="left", padx=(0,6))
        lbl = tk.Label(r, font=FSM, bg=BG, fg=TEXT, width=4, anchor="w")
        lbl.pack(side="left")
        def update(*_): lbl.config(text=f"{var.get():.1f}s")
        var.trace_add("write", update); update()

    # ── Style tab ─────────────────────────────────────────────────────────────

    def _build_style_tab(self, parent):
        frame = tk.Frame(parent, bg=BG)

        left  = tk.Frame(frame, bg=BG, width=310)
        left.pack(side="left", fill="y", padx=(18,8), pady=12)
        left.pack_propagate(False)

        sep = tk.Frame(frame, bg=BORDER, width=1)
        sep.pack(side="left", fill="y", pady=12)

        right = tk.Frame(frame, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(12,18), pady=12)

        # ── Left: scrollable controls
        sf = ScrollFrame(left, bg=BG)
        sf.pack(fill="both", expand=True)
        inn = sf.inner

        # TYPOGRAPHY
        self._section_lbl(inn, "TYPOGRAPHY")

        # Font
        fr = tk.Frame(inn, bg=BG)
        fr.pack(fill="x", pady=(0,8))
        tk.Label(fr, text="Font", font=FSM, bg=BG, fg=MUTED, width=14, anchor="w").pack(side="left")
        self._font_entry_widget(fr)

        # Size + toggles
        sr = tk.Frame(inn, bg=BG)
        sr.pack(fill="x", pady=(0,8))
        tk.Label(sr, text="Size (pt)", font=FSM, bg=BG, fg=MUTED, width=14, anchor="w").pack(side="left")
        self._spinbox(sr, self.vars["size"], 20, 200, 4)
        tg = tk.Frame(sr, bg=BG)
        tg.pack(side="left")
        self._pill_toggle(tg, "Bold",   self.vars["bold"]).pack(side="left", padx=(0,3))
        self._pill_toggle(tg, "Italic", self.vars["italic"]).pack(side="left", padx=(0,3))
        self._pill_toggle(tg, "Caps",   self.vars["caps"]).pack(side="left")

        # Letter spacing / line height
        lsr = tk.Frame(inn, bg=BG)
        lsr.pack(fill="x", pady=(0,8))
        tk.Label(lsr, text="Letter spacing", font=FSM, bg=BG, fg=MUTED,
                 width=14, anchor="w").pack(side="left")
        self._spinbox(lsr, self.vars["letter_spacing"], -20, 100, 4)
        self._spinbox(lsr, self.vars["line_height"], 50, 200, 4)
        tk.Label(lsr, text="%", font=FSM, bg=BG, fg=MUTED).pack(side="left")

        # COLOUR
        self._section_lbl(inn, "COLOUR")

        cr = tk.Frame(inn, bg=BG)
        cr.pack(fill="x", pady=(0,8))
        tk.Label(cr, text="Text", font=FSM, bg=BG, fg=MUTED, width=14, anchor="w").pack(side="left")
        self._color_widget(cr, self.vars["color"]).pack(side="left")

        # Outline
        tk.Checkbutton(inn, text="Outline", variable=self.vars["outline"],
                       font=FSM, bg=BG, fg=TEXT, selectcolor=SURFACE2,
                       activebackground=BG, activeforeground=TEXT,
                       command=self._refresh_preview).pack(anchor="w", pady=(0,4))

        od = tk.Frame(inn, bg=BG)
        od.pack(fill="x", pady=(0,4), padx=(16,0))
        tk.Label(od, text="Color", font=FSM, bg=BG, fg=MUTED, width=12, anchor="w").pack(side="left")
        self._color_widget(od, self.vars["outline_color"]).pack(side="left")

        ow = tk.Frame(inn, bg=BG)
        ow.pack(fill="x", pady=(0,8), padx=(16,0))
        tk.Label(ow, text="Width", font=FSM, bg=BG, fg=MUTED, width=12, anchor="w").pack(side="left")
        self._spinbox(ow, self.vars["outline_w"], 1, 20, 4)

        # Shadow
        tk.Checkbutton(inn, text="Shadow", variable=self.vars["shadow"],
                       font=FSM, bg=BG, fg=TEXT, selectcolor=SURFACE2,
                       activebackground=BG, activeforeground=TEXT,
                       command=self._refresh_preview).pack(anchor="w", pady=(0,4))

        sd = tk.Frame(inn, bg=BG)
        sd.pack(fill="x", pady=(0,8), padx=(16,0))
        tk.Label(sd, text="Color", font=FSM, bg=BG, fg=MUTED, width=12, anchor="w").pack(side="left")
        self._color_widget(sd, self.vars["shadow_color"]).pack(side="left")

        # ── Right: 16:9 preview canvas
        hdr_row = tk.Frame(right, bg=BG)
        hdr_row.pack(fill="x")
        tk.Label(hdr_row, text="16:9 preview", font=FXSM, bg=BG, fg=MUTED).pack(side="left")

        canvas_outer = tk.Frame(right, bg=SURFACE, highlightthickness=1,
                                highlightbackground=BORDER)
        canvas_outer.pack(fill="both", expand=True)

        self._preview_canvas = tk.Canvas(canvas_outer, bg="#161616",
                                          highlightthickness=0, relief="flat")
        self._preview_canvas.pack(fill="both", expand=True)
        self._preview_canvas.bind("<Configure>", lambda e: self.after_idle(self._refresh_preview))

        return frame

    def _font_entry_widget(self, parent):
        """Font selector using a styled OptionMenu dropdown."""
        frame = tk.Frame(parent, bg=BG)
        frame.pack(side="left")

        fonts = get_system_fonts()
        # Ensure the current value is in the list
        current = self.vars["font"].get()
        if current not in fonts:
            fonts = [current] + fonts

        # Build OptionMenu
        om = tk.OptionMenu(frame, self.vars["font"], *fonts)
        om.config(
            bg=SURFACE2, fg=TEXT,
            activebackground=SURFACE3, activeforeground=ACCENT,
            relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            font=FUI, indicatoron=True, pady=5, padx=8,
            width=18,
        )
        om["menu"].config(
            bg=SURFACE, fg=TEXT,
            activebackground=ACCENT, activeforeground="#0f0f0f",
            font=FUI, relief="flat", bd=0,
        )
        om.pack(fill="x")
        return frame

    # ── Position tab ─────────────────────────────────────────────────────────

    def _build_position_tab(self, parent):
        frame = tk.Frame(parent, bg=BG)

        left  = tk.Frame(frame, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(24,16), pady=12)
        right = tk.Frame(frame, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(16,24), pady=12)

        # ── Left: position grid + fine-tune
        self._section_lbl(left, "SCREEN POSITION")

        pos_row = tk.Frame(left, bg=BG)
        pos_row.pack(anchor="w", pady=(0,16))

        # 3×3 grid
        gf = tk.Frame(pos_row, bg=BG)
        gf.pack(side="left", padx=(0,24))
        tk.Label(gf, text="Grid", font=FXSM, bg=BG, fg=MUTED).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0,6))

        cur_x = self.vars["x_offset"].get()
        cur_y = self.vars["y_offset"].get()

        def make_grid_cmd(gname, gx, gy):
            def fn():
                self.vars["x_offset"].set(gx)
                self.vars["y_offset"].set(gy)
                for n, b in self._grid_btns.items():
                    b.config(bg=ACCENT if n == gname else SURFACE2)
            return fn

        for i, (gname, gx, gy) in enumerate(GRID_POSITIONS):
            ri = (i // 3) + 1
            ci = i % 3
            is_sel = (cur_x == gx and cur_y == gy)
            b = tk.Button(gf, width=3, height=1,
                          bg=ACCENT if is_sel else SURFACE2,
                          activebackground=ACCENT,
                          relief="flat", bd=0,
                          highlightthickness=1, highlightbackground=BORDER,
                          cursor="hand2",
                          command=make_grid_cmd(gname, gx, gy))
            b.grid(row=ri, column=ci, padx=2, pady=2)
            self._grid_btns[gname] = b

        # Fine-tune
        ft = tk.Frame(pos_row, bg=BG)
        ft.pack(side="left")
        tk.Label(ft, text="Fine-tune (%)", font=FXSM, bg=BG, fg=MUTED).pack(anchor="w", pady=(0,6))

        xr = tk.Frame(ft, bg=BG)
        xr.pack(anchor="w", pady=(0,6))
        tk.Label(xr, text="X offset", font=FSM, bg=BG, fg=MUTED, width=8, anchor="w").pack(side="left")

        x_entry = tk.Entry(xr, textvariable=self.vars["x_offset"],
                           font=FUI, bg=SURFACE2, fg=TEXT,
                           insertbackground=ACCENT, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=BORDER,
                           width=6)
        x_entry.pack(side="left", ipady=5, ipadx=4)

        yr = tk.Frame(ft, bg=BG)
        yr.pack(anchor="w", pady=(0,6))
        tk.Label(yr, text="Y offset", font=FSM, bg=BG, fg=MUTED, width=8, anchor="w").pack(side="left")

        y_entry = tk.Entry(yr, textvariable=self.vars["y_offset"],
                           font=FUI, bg=SURFACE2, fg=TEXT,
                           insertbackground=ACCENT, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=BORDER,
                           width=6)
        y_entry.pack(side="left", ipady=5, ipadx=4)

        tk.Label(ft, text="0,0 = top-left   100,100 = bottom-right",
                 font=FXSM, bg=BG, fg=MUTED2).pack(anchor="w", pady=(4,0))

        # ── Right: alignment + max width + safe zone
        self._section_lbl(right, "TEXT ALIGNMENT")
        self._option_pills(right, ["Left", "Center", "Right"],
                           self.vars["text_align"]).pack(anchor="w", pady=(0,14))

        self._section_lbl(right, "MAX WIDTH")
        mwr = tk.Frame(right, bg=BG)
        mwr.pack(anchor="w", pady=(0,4))
        tk.Label(mwr, text="% of screen", font=FSM, bg=BG, fg=MUTED).pack(side="left", padx=(0,8))
        mw_sl = tk.Scale(mwr, variable=self.vars["max_width"],
                          from_=20, to=100, orient="horizontal",
                          bg=BG, fg=MUTED, troughcolor=SURFACE2,
                          highlightthickness=0, bd=0, length=160,
                          sliderrelief="flat", sliderlength=10, showvalue=False)
        mw_sl.pack(side="left")
        mw_lbl = tk.Label(mwr, font=FSM, bg=BG, fg=TEXT, width=3)
        mw_lbl.pack(side="left", padx=(4,0))
        tk.Label(mwr, text="%", font=FSM, bg=BG, fg=MUTED).pack(side="left")
        def upd_mw(*_): mw_lbl.config(text=str(self.vars["max_width"].get()))
        self.vars["max_width"].trace_add("write", upd_mw); upd_mw()

        self._section_lbl(right, "SAFE ZONE")
        tk.Checkbutton(right, text="Snap to broadcast safe area",
                       variable=self.vars["safe_zone"],
                       font=FSM, bg=BG, fg=TEXT, selectcolor=SURFACE2,
                       activebackground=BG).pack(anchor="w", pady=(0,6))
        tk.Checkbutton(right, text="Show safe zone in preview",
                       variable=self.vars["show_safe_zone"],
                       font=FSM, bg=BG, fg=TEXT, selectcolor=SURFACE2,
                       activebackground=BG).pack(anchor="w")

        return frame

    # ── preview renderer ──────────────────────────────────────────────────────

    def _alpha_color(self, hex_color, alpha):
        """Blend hex_color toward canvas bg (#161616) by alpha."""
        try:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
        except Exception:
            return hex_color
        bg_r, bg_g, bg_b = 0x16, 0x16, 0x16
        a = max(0.0, min(1.0, alpha))
        nr = int(r * a + bg_r * (1 - a))
        ng = int(g * a + bg_g * (1 - a))
        nb = int(b * a + bg_b * (1 - a))
        return f"#{nr:02x}{ng:02x}{nb:02x}"

    def _refresh_preview(self, *_):
        if not hasattr(self, "_preview_canvas"):
            return
        c = self._preview_canvas
        c.delete("all")

        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 10 or ch < 10:
            return

        # Draw background grid (subtle)
        for gx in range(0, cw, 40):
            c.create_line(gx, 0, gx, ch, fill="#1e1e1e", width=1)
        for gy in range(0, ch, 40):
            c.create_line(0, gy, cw, gy, fill="#1e1e1e", width=1)

        # Safe zone overlay
        if self.vars.get("show_safe_zone") and self.vars["show_safe_zone"].get():
            m = 0.1
            c.create_rectangle(
                int(cw*m), int(ch*m), int(cw*(1-m)), int(ch*(1-m)),
                outline="#334433", width=1, dash=(4,4))

        font_name  = self.vars["font"].get() or "Arial"
        size_pt    = self.vars["size"].get()
        bold       = self.vars["bold"].get()
        italic     = self.vars["italic"].get()
        color      = self.vars["color"].get()
        outline    = self.vars["outline"].get()
        outline_c  = self.vars["outline_color"].get()
        outline_w  = self.vars["outline_w"].get()
        shadow     = self.vars["shadow"].get()
        shadow_c   = self.vars["shadow_color"].get()
        x_off      = self.vars["x_offset"].get()
        y_off      = self.vars["y_offset"].get()

        preview_size = max(10, min(size_pt // 4, 30))
        weight = "bold" if bold else "normal"
        slant  = "italic" if italic else "roman"

        try:
            fnt = tkfont.Font(family=font_name, size=preview_size,
                              weight=weight, slant=slant)
        except Exception:
            fnt = tkfont.Font(size=preview_size)

        text = PREVIEW_TEXT
        if self.vars["caps"].get():
            text = text.upper()

        x = int(cw * x_off / 100)
        y = int(ch * y_off / 100)

        if outline:
            ow_px = max(1, outline_w // 2)
            for dx in range(-ow_px, ow_px+1):
                for dy in range(-ow_px, ow_px+1):
                    if dx == 0 and dy == 0:
                        continue
                    c.create_text(x+dx, y+dy, text=text,
                                  font=fnt, fill=outline_c, anchor="center")
        if shadow:
            c.create_text(x+2, y+2, text=text, font=fnt,
                          fill=shadow_c, anchor="center")
        c.create_text(x, y, text=text, font=fnt, fill=color, anchor="center")

        # Position badge (bottom-right)
        x_label = x_off
        y_label = y_off
        # Determine position name
        pos_name = "custom"
        for gname, gx, gy in GRID_POSITIONS:
            if gx == x_label and gy == y_label:
                pos_name = gname; break
        badge_txt = f"position: {pos_name}"
        bx, by = cw - 8, ch - 8
        # Badge background
        text_id = c.create_text(bx, by, text=badge_txt, font=("Segoe UI", 8),
                                 fill="#0f0f0f", anchor="se")
        bb = c.bbox(text_id)
        if bb:
            c.create_rectangle(bb[0]-4, bb[1]-3, bb[2]+4, bb[3]+3,
                               fill="#e8ff47", outline="", tags="badge_bg")
            c.tag_raise(text_id)
            c.itemconfig(text_id, fill="#0f0f0f")
        c.tag_lower("badge_bg")

    # ── save ──────────────────────────────────────────────────────────────────

    def destroy(self):
        super().destroy()

    def _save(self):
        result = {k: v.get() for k, v in self.vars.items()}
        result["builtin"] = False
        y = result.get("y_offset", 85)
        result["position"] = "top" if y <= 20 else ("center" if y <= 60 else "bottom")
        if self.on_save:
            self.on_save(result)
        self.destroy()


# ── main app ──────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()          # hidden until splash finishes

        # ── Splash screen ──────────────────────────────────────────────────
        splash = SplashScreen(self)
        splash.update()

        # Icon
        try:
            self._icon_img = tk.PhotoImage(data=_ICON_B64)
            self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        self.title("AutoSubtitle")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("620x800")

        splash.advance_to(0.20, "Loading interface…")
        self.file_path  = tk.StringVar(value="")
        self.seg_style  = tk.StringVar(value=list(SEG_STYLES.keys())[1])
        self.model_var  = tk.StringVar(value="medium")
        self.lang_var   = tk.StringVar(value="auto")
        self.format_var = tk.StringVar(value="SRT")
        self.preset_var = tk.StringVar()
        self.running    = False

        splash.advance_to(0.45, "Scanning system fonts…")
        get_system_fonts()   # pre-warm font cache

        splash.advance_to(0.70, "Loading presets…")
        self.presets = load_presets()

        splash.advance_to(0.85, "Building interface…")
        self._build()

        splash.advance_to(0.95, "Checking dependencies…")
        self._refresh_presets()
        self._check_deps()

        splash.advance_to(1.00, "Ready!")
        self.after(380, lambda: (splash.close(), self.deiconify()))

    def _build(self):
        # header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=24, pady=(28, 0))
        tk.Label(hdr, text="AutoSubtitle", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text=" *", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left")
        tk.Button(hdr, text="?  Tutorial", font=FSM,
                  bg=SURFACE2, fg=ACCENT,
                  activebackground=SURFACE3, activeforeground=ACCENT,
                  relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
                  command=lambda: TutorialOverlay(self)).pack(side="right")
        tk.Label(self, text="Smart subtitles for Adobe Premiere Pro",
                 font=FSM, bg=BG, fg=MUTED).pack(anchor="w", padx=24, pady=(4, 2))
        tk.Label(self, text=AUTHOR,
                 font=FXSM, bg=BG, fg=MUTED2).pack(anchor="w", padx=24, pady=(0, 24))

        self._div()

        # file picker
        self._section("Audio / Video File")
        drop = tk.Frame(self, bg=SURFACE, cursor="hand2",
                        highlightthickness=1, highlightbackground=BORDER)
        drop.pack(fill="x", padx=24, pady=(0, 16))
        drop.bind("<Button-1>", lambda e: self._browse())
        drop.bind("<Enter>", lambda e: drop.config(highlightbackground=ACCENT))
        drop.bind("<Leave>", lambda e: drop.config(highlightbackground=BORDER))
        self._file_label = tk.Label(
            drop, text="Click to choose file  *  mp3  mp4  wav  m4a  mov",
            font=FUI, bg=SURFACE, fg=MUTED, pady=22, cursor="hand2")
        self._file_label.pack()
        self._file_label.bind("<Button-1>", lambda e: self._browse())

        self._div()

        # caption preset
        self._section("Caption Preset")
        prow = tk.Frame(self, bg=BG)
        prow.pack(fill="x", padx=24, pady=(0, 8))
        prow.columnconfigure(0, weight=1)

        self._pmenu = tk.OptionMenu(prow, self.preset_var, "")
        self._style_om(self._pmenu)
        self._pmenu.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        btns = tk.Frame(prow, bg=BG)
        btns.grid(row=0, column=1)
        tk.Button(btns, text="New", font=FSM, bg=SURFACE2, fg=TEXT,
                  activebackground=BORDER, relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2", command=self._new_preset).pack(side="left", padx=(0, 4))
        self._edit_btn = tk.Button(btns, text="Edit", font=FSM, bg=SURFACE2, fg=TEXT,
                  activebackground=BORDER, relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2", command=self._edit_preset)
        self._edit_btn.pack(side="left", padx=(0, 4))
        self._del_btn = tk.Button(btns, text="Delete", font=FSM, bg=SURFACE2, fg=ERROR,
                  activebackground=BORDER, relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2", command=self._delete_preset)
        self._del_btn.pack(side="left")

        self._preview = tk.Label(self, text="", font=FSM, bg=SURFACE2, fg=MUTED,
                                  anchor="w", pady=8, padx=12)
        self._preview.pack(fill="x", padx=24, pady=(8, 16))
        self.preset_var.trace_add("write", lambda *_: self._update_preview())

        self._div()

        # transcription settings
        self._section("Transcription Settings")
        opts = tk.Frame(self, bg=BG)
        opts.pack(fill="x", padx=24, pady=(0, 16))
        opts.columnconfigure(0, weight=1)
        opts.columnconfigure(1, weight=1)
        self._seg_om   = self._lom(opts, "Seg. Style", list(SEG_STYLES.keys()), self.seg_style, 0, 0)
        self._model_om = self._lom(opts, "Model",      MODELS,                  self.model_var, 0, 1)

        langs = ["auto","en","hu","de","fr","es","it","pt","pl","ru","zh","ja","ko"]
        bot_row = tk.Frame(self, bg=BG)
        bot_row.pack(fill="x", padx=24, pady=(0, 20))
        bot_row.columnconfigure(0, weight=1)
        bot_row.columnconfigure(1, weight=0)

        # Language (left, grows)
        lf = tk.Frame(bot_row, bg=BG)
        lf.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        tk.Label(lf, text="Language", font=FSM, bg=BG, fg=MUTED).pack(anchor="w")
        lm = tk.OptionMenu(lf, self.lang_var, *langs)
        self._style_om(lm)
        lm.pack(fill="x", pady=(4, 0))
        self._lang_om = lm

        # Output format (right, fixed width)
        ff = tk.Frame(bot_row, bg=BG)
        ff.grid(row=0, column=1, sticky="n")
        self._fmt_frame = ff
        tk.Label(ff, text="Format", font=FSM, bg=BG, fg=MUTED).pack(anchor="w")
        fmt_row = tk.Frame(ff, bg=BG)
        fmt_row.pack(anchor="w", pady=(4, 0))
        for fmt in ("SRT", "VTT"):
            tk.Radiobutton(
                fmt_row, text=fmt, variable=self.format_var, value=fmt,
                font=FUI, bg=BG, fg=TEXT, selectcolor=SURFACE2,
                activebackground=BG, activeforeground=TEXT,
            ).pack(side="left", padx=(0, 10))

        self._div()

        # generate
        self._btn = tk.Button(self, text="Generate Subtitles  →",
                              font=FBOLD, bg=ACCENT, fg="#0f0f0f",
                              activebackground="#d4eb2a", activeforeground="#0f0f0f",
                              relief="flat", bd=0, pady=14, cursor="hand2",
                              command=self._run)
        self._btn.pack(fill="x", padx=24, pady=(0, 24))

        # log
        self._section("Log")
        lf = tk.Frame(self, bg=SURFACE2, highlightthickness=1, highlightbackground=BORDER)
        lf.pack(fill="x", padx=24, pady=(0, 24))
        self._log = tk.Text(lf, height=7, font=FMONO, bg=SURFACE2, fg=TEXT,
                            insertbackground=ACCENT, relief="flat", bd=0,
                            padx=12, pady=10, state="disabled", wrap="word")
        self._log.pack(fill="x")
        self._log.tag_config("accent",  foreground=ACCENT)
        self._log.tag_config("success", foreground=SUCCESS)
        self._log.tag_config("error",   foreground=ERROR)
        self._log.tag_config("muted",   foreground=MUTED)

    def _div(self):
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=24, pady=(0, 20))

    def _section(self, label):
        tk.Label(self, text=label.upper(), font=FSM, bg=BG, fg=MUTED).pack(
            anchor="w", padx=24, pady=(0, 8))

    def _lom(self, parent, label, values, var, row, col):
        f = tk.Frame(parent, bg=BG)
        f.grid(row=row, column=col, sticky="ew",
               padx=(0, 12) if col == 0 else 0, pady=(0, 8))
        tk.Label(f, text=label, font=FSM, bg=BG, fg=MUTED).pack(anchor="w")
        m = tk.OptionMenu(f, var, *values)
        self._style_om(m)
        m.pack(fill="x", pady=(4, 0))
        return m

    def _style_om(self, m):
        m.config(bg=SURFACE, fg=TEXT, activebackground=SURFACE2, activeforeground=ACCENT,
                 relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER,
                 font=FUI, indicatoron=True, pady=8, padx=12)
        m["menu"].config(bg=SURFACE, fg=TEXT, activebackground=ACCENT,
                         activeforeground="#0f0f0f", font=FUI, relief="flat", bd=0)

    # ── presets ───────────────────────────────────────────────────────────────

    def _refresh_presets(self):
        menu = self._pmenu["menu"]
        menu.delete(0, "end")
        for p in self.presets:
            menu.add_command(label=p["name"],
                             command=lambda n=p["name"]: self.preset_var.set(n))
        if self.presets:
            cur   = self.preset_var.get()
            names = [p["name"] for p in self.presets]
            self.preset_var.set(cur if cur in names else names[0])

    def _current_preset(self):
        name = self.preset_var.get()
        return next((p for p in self.presets if p["name"] == name), None)

    def _update_preview(self):
        p = self._current_preset()
        if not p:
            return
        parts = [
            f"Font: {p['font']} {p['size']}pt",
            ("Bold " if p.get("bold") else "") + ("Italic" if p.get("italic") else ""),
            f"Color: {p['color']}",
            f"Outline: {'yes' if p.get('outline') else 'no'}",
            f"Shadow: {'yes' if p.get('shadow') else 'no'}",
            f"Position: {p.get('x_offset',50)},{p.get('y_offset',85)}",
        ]
        self._preview.config(text="  *  ".join(s for s in parts if s.strip()))
        builtin = p.get("builtin", False)
        self._edit_btn.config(state="disabled" if builtin else "normal",
                              fg=MUTED if builtin else TEXT)
        self._del_btn.config(state="disabled" if builtin else "normal",
                             fg=MUTED if builtin else ERROR)

    def _new_preset(self):
        PresetEditor(self, on_save=self._save_new)

    def _save_new(self, preset):
        if any(p["name"] == preset["name"] for p in self.presets):
            messagebox.showerror("Name taken", f'"{preset["name"]}" already exists.')
            return
        self.presets.append(preset)
        save_presets(self.presets)
        self._refresh_presets()
        self.preset_var.set(preset["name"])

    def _edit_preset(self):
        p = self._current_preset()
        if not p or p.get("builtin"):
            return
        PresetEditor(self, preset=p,
                     on_save=lambda u: self._save_edited(p["name"], u))

    def _save_edited(self, old_name, updated):
        for i, p in enumerate(self.presets):
            if p["name"] == old_name:
                self.presets[i] = updated; break
        save_presets(self.presets)
        self._refresh_presets()
        self.preset_var.set(updated["name"])

    def _delete_preset(self):
        p = self._current_preset()
        if not p or p.get("builtin"):
            return
        if messagebox.askyesno("Delete", f'Delete "{p["name"]}"?'):
            self.presets = [x for x in self.presets if x["name"] != p["name"]]
            save_presets(self.presets)
            self._refresh_presets()

    # ── file & log ────────────────────────────────────────────────────────────

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Choose audio or video file",
            filetypes=[("Media files", "*.mp3 *.mp4 *.wav *.m4a *.mov *.aac *.flac *.ogg"),
                       ("All files", "*.*")])
        if path:
            self.file_path.set(path)
            self._file_label.config(text=f"  {os.path.basename(path)}", fg=TEXT)
            self._log_clear()
            self._log_write(f"File: {os.path.basename(path)}\n", "muted")

    def _check_deps(self):
        missing = check_dependencies()
        if missing:
            self._log_write("Missing packages:\n", "error")
            self._log_write(f"  pip install {' '.join(missing)}\n", "accent")
            self._btn.config(state="disabled", bg=BORDER, fg=MUTED)

    def _log_clear(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    def _log_write(self, text, tag=None):
        self._log.config(state="normal")
        self._log.insert("end", text, tag or "")
        self._log.see("end")
        self._log.config(state="disabled")

    # ── run ───────────────────────────────────────────────────────────────────

    def _run(self):
        if self.running:
            return
        path = self.file_path.get()
        if not path or not os.path.exists(path):
            self._log_clear()
            self._log_write("No file selected.\n", "error")
            return
        preset = self._current_preset()
        if not preset:
            self._log_clear()
            self._log_write("No preset selected.\n", "error")
            return
        self.running = True
        self._btn.config(state="disabled", text="Working...", bg=BORDER, fg=MUTED)
        self._log_clear()
        threading.Thread(target=self._transcribe, args=(preset,), daemon=True).start()

    def _transcribe(self, preset):
        import torch, stable_whisper
        path     = self.file_path.get()
        seg_cfg  = SEG_STYLES[self.seg_style.get()]
        model_id = self.model_var.get()
        lang     = self.lang_var.get()
        fmt      = self.format_var.get()          # "SRT" or "VTT"
        ext      = ".srt" if fmt == "SRT" else ".vtt"
        out_path = os.path.splitext(path)[0] + "_captions" + ext
        device   = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            self._log_write(f"Loading Whisper '{model_id}' on {device}...\n", "muted")
            model = stable_whisper.load_model(model_id, device=device)

            self._log_write("Transcribing with precise timing...\n", "muted")
            opts = dict(word_timestamps=True, regroup=False)
            if lang != "auto":
                opts["language"] = lang
            result = model.transcribe(path, **opts)

            detected = result.language if hasattr(result, "language") else "unknown"
            self._log_write(f"Language: {detected}\n", "muted")

            all_words = []
            for seg in result.segments:
                for w in seg.words:
                    word = w.word.strip()
                    if word:
                        all_words.append({"word": word, "start": w.start, "end": w.end})

            if not all_words:
                self._log_write("No speech detected.\n", "error")
                self._finish()
                return

            self._log_write(f"Words found: {len(all_words)}\n", "muted")
            cards = segment_words(all_words, seg_cfg)
            self._log_write(f"Cards: {len(cards)}\n", "muted")

            if fmt == "SRT":
                content = cards_to_srt(cards, preset)
            else:
                content = cards_to_vtt(cards, preset)

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)

            self._log_write(f"\n✓ Done!  {len(cards)} caption cards\n", "success")
            self._log_write(f"  Saved: {out_path}\n", "accent")

            if fmt == "SRT":
                self._log_write(
                    "\nIn Premiere: File > Import, then drag the .srt\n"
                    "onto a caption track. Right-click the track >\n"
                    "Convert to Graphics to apply a .mogrt style.\n", "muted")
            else:
                self._log_write(
                    "\nIn Premiere: File > Import, then drag the .vtt\n"
                    "onto a caption track. Position cues are embedded.\n"
                    "Right-click the track > Convert to Graphics\n"
                    "to apply a .mogrt style.\n", "muted")

        except Exception as e:
            self._log_write(f"\nError: {e}\n", "error")

        self._finish()

    def _finish(self):
        self.running = False
        self._btn.config(state="normal", text="Generate Subtitles  →",
                         bg=ACCENT, fg="#0f0f0f")


if __name__ == "__main__":
    App().mainloop()