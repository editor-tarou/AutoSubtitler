"""
tutorial.py — the interactive walkthrough overlay that highlights UI widgets
one by one and explains what they do.

The overlay is a borderless Toplevel that sits exactly over the main window.
On Windows, a transparent colour key is used to punch a "spotlight" hole
through the dark overlay so the highlighted widget is visible underneath.
"""

import math
import tkinter as tk

from .theme import (
    BG, SURFACE, SURFACE2, SURFACE3, BORDER, ACCENT, TEXT, MUTED, MUTED2,
    FSM, FXSM, FBOLD,
)


class TutorialOverlay(tk.Toplevel):

    CARD_W = 300
    CARD_H = 215
    MARGIN = 14
    PAD    = 8
    TRANS  = "#fe01fe"   # transparent colour key (Windows)

    def __init__(self, app: tk.Tk):
        super().__init__(app)
        self.app        = app
        self.step_index = 0
        self._pulse_job  = None
        self._type_job   = None
        self._pulse_ph   = 0.0
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

    def _sync(self) -> None:
        self.app.update_idletasks()
        x = self.app.winfo_rootx()
        y = self.app.winfo_rooty()
        w = self.app.winfo_width()
        h = self.app.winfo_height()
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._W, self._H = w, h

    # ── step definitions ──────────────────────────────────────────────────────

    def _build_steps(self) -> list[dict]:
        a = self.app
        return [
            {
                "w":     lambda: a._file_label,
                "title": "📁  File Picker",
                "body":  "Click this area to browse and load your audio or video file.\n"
                         "Supports MP3, MP4, WAV, M4A, MOV, AAC, FLAC and more.",
            },
            {
                "w":     lambda: a._pmenu,
                "title": "🎨  Caption Preset",
                "body":  "Choose a visual style for your captions. Each preset defines "
                         "the font, size, colour, outline and screen position.",
            },
            {
                "w":     lambda: a._edit_btn,
                "title": "✏️  Preset Controls",
                "body":  "New — create a custom style from scratch.\n"
                         "Edit — tweak the selected preset.\n"
                         "Delete — remove a custom preset permanently.",
            },
            {
                "w":     lambda: a._preview,
                "title": "👁  Style Summary",
                "body":  "A live summary of the active preset: font name, size, colour, "
                         "outline and shadow settings shown at a glance.",
            },
            {
                "w":     lambda: a._seg_om,
                "title": "✂️  Segmentation Style",
                "body":  "Controls how many words appear per subtitle card.\n"
                         "• Punchy = 1-3 words  (fast cuts)\n"
                         "• Balanced = 3-5 words  (recommended)\n"
                         "• Full = natural phrases",
            },
            {
                "w":     lambda: a._model_om,
                "title": "🧠  Whisper Model",
                "body":  "Larger models are more accurate but slower.\n"
                         "• tiny / base — quick preview\n"
                         "• medium — best daily balance\n"
                         "• large — maximum accuracy",
            },
            {
                "w":     lambda: a._lang_om,
                "title": "🌐  Language",
                "body":  "Set the spoken language to improve accuracy, or leave on 'auto' "
                         "and Whisper will detect it automatically from the audio.",
            },
            {
                "w":     lambda: a._fmt_frame,
                "title": "📄  Output Format",
                "body":  "SRT — universal, import directly into Premiere via a caption track.\n"
                         "VTT — embeds precise X / Y position cues from your preset.",
            },
            {
                "w":     lambda: a._btn,
                "title": "🚀  Generate!",
                "body":  "Click to start transcription. The subtitle file is saved next to "
                         "your source with _captions.srt or .vtt appended to the filename.",
            },
            {
                "w":     lambda: a._log,
                "title": "📋  Log Output",
                "body":  "Live progress and status messages appear here during transcription. "
                         "Errors, word counts and Premiere tips all show in this panel.",
            },
        ]

    # ── widget bounding box ───────────────────────────────────────────────────

    def _wrect(self, widget: tk.Widget) -> tuple[int, int, int, int]:
        widget.update_idletasks()
        ox = self.app.winfo_rootx()
        oy = self.app.winfo_rooty()
        return (
            widget.winfo_rootx() - ox,
            widget.winfo_rooty() - oy,
            widget.winfo_width(),
            widget.winfo_height(),
        )

    # ── render ────────────────────────────────────────────────────────────────

    def _render_step(self) -> None:
        if self._type_job:
            self.after_cancel(self._type_job)
            self._type_job = None
        self.canvas.delete("all")
        self._pulse_rect = None

        step = self.steps[self.step_index]
        try:
            widget = step["w"]()
        except Exception:
            self._next()
            return

        OW, OH = self._W, self._H
        wx, wy, ww, wh = self._wrect(widget)
        P  = self.PAD
        sx = max(0, wx - P);      sy = max(0, wy - P)
        sr = min(OW, wx+ww+P);    sb = min(OH, wy+wh+P)

        # Dark overlay — 4 rectangles around the spotlight hole
        DARK = "#0a0a0a"
        self.canvas.create_rectangle(0,  0,  OW, sy,  fill=DARK, outline="")
        self.canvas.create_rectangle(0,  sb, OW, OH,  fill=DARK, outline="")
        self.canvas.create_rectangle(0,  sy, sx, sb,  fill=DARK, outline="")
        self.canvas.create_rectangle(sr, sy, OW, sb,  fill=DARK, outline="")

        # Transparent "hole" (Windows only — on other platforms just clear)
        self.canvas.create_rectangle(sx, sy, sr, sb, fill=self.TRANS, outline="")

        # Animated pulse border around the spotlight
        self._pulse_rect = self.canvas.create_rectangle(
            sx-3, sy-3, sr+3, sb+3, outline=ACCENT, width=2, fill="")

        # Skip button (top-right)
        skip = self.canvas.create_text(OW-14, 14,
                                       text="✕  Skip Tutorial",
                                       font=FSM, fill=MUTED, anchor="ne")
        skip_bg = self.canvas.create_rectangle(
            *self.canvas.bbox(skip), fill=DARK, outline="")
        self.canvas.tag_lower(skip_bg, skip)
        for tag in (skip, skip_bg):
            self.canvas.tag_bind(tag, "<Button-1>", lambda _e: self._close())
            self.canvas.tag_bind(tag, "<Enter>",
                lambda _e: self.canvas.itemconfig(skip, fill=TEXT))
            self.canvas.tag_bind(tag, "<Leave>",
                lambda _e: self.canvas.itemconfig(skip, fill=MUTED))

        # Card
        cx, cy = self._card_pos(sx, sy, sr-sx, sb-sy, OW, OH)
        CW, CH = self.CARD_W, self.CARD_H
        cpad   = 16

        self.canvas.create_rectangle(cx+4, cy+4, cx+CW+4, cy+CH+4,
                                     fill="#000000", outline="")
        self.canvas.create_rectangle(cx,   cy,   cx+CW,   cy+CH,
                                     fill=SURFACE, outline=BORDER, width=1)
        self.canvas.create_rectangle(cx,   cy,   cx+CW,   cy+3,
                                     fill=ACCENT, outline="")

        total   = len(self.steps)
        counter = f"Step {self.step_index + 1} of {total}"
        self.canvas.create_text(cx+cpad, cy+cpad+2,
                                text=counter, font=FXSM, fill=MUTED, anchor="w")

        title_id = self.canvas.create_text(cx+cpad, cy+cpad+18,
                                           text="", font=FBOLD, fill=ACCENT, anchor="w")
        self._type_text(title_id, step["title"], speed=22)

        self.canvas.create_text(cx+cpad, cy+cpad+40,
                                text=step["body"], font=FSM, fill=TEXT,
                                anchor="nw", width=CW - cpad*2)

        mid_sx = (sx+sr)//2;  mid_sy = (sy+sb)//2
        mid_cx = cx + CW//2;  mid_cy = cy + CH//2
        self.canvas.create_line(mid_sx, mid_sy, mid_cx, mid_cy,
                                fill=MUTED2, dash=(3, 6), width=1)

        # Progress dots
        dot_y = cy + CH - 14
        ds    = 11
        dx0   = cx + CW//2 - (total * ds)//2
        for i in range(total):
            col = ACCENT if i == self.step_index else SURFACE3
            self.canvas.create_oval(dx0+i*ds, dot_y-3, dx0+i*ds+6, dot_y+3,
                                    fill=col, outline="")

        # Prev / Next buttons
        btn_y   = cy + CH - 46
        is_last = self.step_index == total - 1

        if self.step_index > 0:
            self._draw_btn(cx+cpad,       btn_y, 72, 26,
                           "← Back", SURFACE2, BORDER, TEXT, self._prev)

        lbl = "✓  Done" if is_last else "Next  →"
        self._draw_btn(cx+CW-cpad-82, btn_y, 82, 26,
                       lbl, ACCENT, "", "#0f0f0f", self._next)

    # ── canvas button helper ──────────────────────────────────────────────────

    def _draw_btn(self, x, y, w, h, text, bg, outline, fg, cmd) -> None:
        r = self.canvas.create_rectangle(
            x, y, x+w, y+h,
            fill=bg, outline=outline or bg, width=1 if outline else 0,
        )
        t = self.canvas.create_text(x+w//2, y+h//2, text=text, font=FSM, fill=fg)
        hover_bg = SURFACE3 if bg != ACCENT else "#d4eb2a"
        for tag in (r, t):
            self.canvas.tag_bind(tag, "<Button-1>", lambda _e, c=cmd: c())
            self.canvas.tag_bind(tag, "<Enter>",
                lambda _e, rid=r: self.canvas.itemconfig(rid, fill=hover_bg))
            self.canvas.tag_bind(tag, "<Leave>",
                lambda _e, rid=r, orig=bg: self.canvas.itemconfig(rid, fill=orig))

    # ── typing animation ──────────────────────────────────────────────────────

    def _type_text(self, item_id: int, full_text: str, i: int = 0, speed: int = 22) -> None:
        if i <= len(full_text):
            try:
                self.canvas.itemconfig(item_id, text=full_text[:i])
            except Exception:
                return
            if i < len(full_text):
                self._type_job = self.after(
                    speed, lambda: self._type_text(item_id, full_text, i + 1, speed))

    # ── pulse animation ───────────────────────────────────────────────────────

    def _pulse_loop(self) -> None:
        self._pulse_ph = (self._pulse_ph + 0.12) % (2 * math.pi)
        t = (math.sin(self._pulse_ph) + 1) / 2
        r = min(255, int(0xe8 + t * 0x17))
        g = 255
        b = min(255, int(0x47 + t * 0x30))
        color = f"#{r:02x}{g:02x}{b:02x}"
        width = 2 + t * 2
        if self._pulse_rect:
            try:
                self.canvas.itemconfig(self._pulse_rect, outline=color, width=width)
            except Exception:
                pass
        self._pulse_job = self.after(40, self._pulse_loop)

    # ── card placement ────────────────────────────────────────────────────────

    def _card_pos(self, sx, sy, sw, sh, OW, OH) -> tuple[int, int]:
        CW, CH, M = self.CARD_W, self.CARD_H, self.MARGIN
        if sx + sw + M + CW <= OW:
            return sx+sw+M, max(8, min(sy+sh//2-CH//2, OH-CH-8))
        if sx - M - CW >= 0:
            return sx-M-CW, max(8, min(sy+sh//2-CH//2, OH-CH-8))
        cx = max(8, min(sx+sw//2-CW//2, OW-CW-8))
        if sy + sh + M + CH <= OH:
            return cx, sy+sh+M
        return cx, max(8, sy-M-CH)

    # ── navigation ────────────────────────────────────────────────────────────

    def _next(self) -> None:
        if self.step_index < len(self.steps) - 1:
            self.step_index += 1
            self._render_step()
        else:
            self._close()

    def _prev(self) -> None:
        if self.step_index > 0:
            self.step_index -= 1
            self._render_step()

    def _close(self) -> None:
        for job in (self._pulse_job, self._type_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self.destroy()
