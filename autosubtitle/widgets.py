import tkinter as tk
from tkinter import colorchooser, font as tkfont

from .theme import (
    BG, SURFACE, SURFACE2, SURFACE3, BORDER, ACCENT, TEXT, MUTED,
    FUI, FSM, FXSM,
)


# ── font cache ────────────────────────────────────────────────────────────────
# scanning fonts on startup is slow (~200ms on my machine), so cache it
_SYSTEM_FONTS: list[str] | None = None


def get_system_fonts() -> list[str]:
    """Return a sorted, deduplicated list of the system's font families."""
    global _SYSTEM_FONTS
    if _SYSTEM_FONTS is None:
        try:
            families = sorted(set(tkfont.families()))
        except Exception:
            # tkfont.families() can fail before a Tk root exists — just give fallbacks
            families = ["Arial", "Georgia", "Impact", "Helvetica", "Verdana"]
        _SYSTEM_FONTS = [f for f in families if f and not f.startswith("@")]
    return _SYSTEM_FONTS


# ── scrollable frame ──────────────────────────────────────────────────────────

class ScrollFrame(tk.Frame):
    """
    A tk.Frame that can scroll vertically.

    Use `scroll_frame.inner` as the parent for anything you want inside it.
    """

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        bg = kw.get("bg", BG)

        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self._sb = tk.Scrollbar(
            self, orient="vertical", command=self._canvas.yview,
            bg=SURFACE2, troughcolor=BG, relief="flat", bd=0, width=6,
            highlightthickness=0,
        )
        self.inner = tk.Frame(self._canvas, bg=bg)
        self._win  = self._canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self._canvas.configure(yscrollcommand=self._sb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._sb.pack(side="right", fill="y")

        self.inner.bind("<Configure>",  self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Enter>",     self._bind_wheel)
        self._canvas.bind("<Leave>",     self._unbind_wheel)

    def _on_inner_configure(self, _e):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._win, width=e.width)

    def _bind_wheel(self, _e):
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _e):
        self._canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")


# ── shared widget helpers ─────────────────────────────────────────────────────

def style_optionmenu(menu: tk.OptionMenu) -> None:
    """Apply the app's dark theme to a tk.OptionMenu widget."""
    menu.config(
        bg=SURFACE, fg=TEXT,
        activebackground=SURFACE2, activeforeground=ACCENT,
        relief="flat", bd=0,
        highlightthickness=1, highlightbackground=BORDER,
        font=FUI, indicatoron=True, pady=8, padx=12,
    )
    menu["menu"].config(
        bg=SURFACE, fg=TEXT,
        activebackground=ACCENT, activeforeground="#0f0f0f",
        font=FUI, relief="flat", bd=0,
    )


def color_widget(parent: tk.Widget, var: tk.StringVar) -> tk.Frame:
    """A colour swatch + hex entry that opens a colour-picker on click."""
    frame = tk.Frame(parent, bg=BG)
    swatch = tk.Label(frame, bg=var.get(), width=2, cursor="hand2",
                      relief="flat", bd=0)
    swatch.pack(side="left", padx=(0, 6), ipady=6, ipadx=3)

    entry = tk.Entry(
        frame, textvariable=var, font=FUI,
        bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
        relief="flat", bd=0, highlightthickness=1,
        highlightbackground=BORDER, width=9,
    )
    entry.pack(side="left", ipady=5, ipadx=4)

    def pick(_=None):
        c = colorchooser.askcolor(color=var.get(), parent=parent)
        if c and c[1]:
            var.set(c[1].upper())

    swatch.bind("<Button-1>", pick)

    def sync_swatch(*_):
        try:
            swatch.config(bg=var.get())
        except Exception:
            pass

    var.trace_add("write", sync_swatch)
    return frame


def pill_toggle(parent: tk.Widget, text: str, var: tk.BooleanVar) -> tk.Button:
    """A button that toggles a BooleanVar and updates its own style."""
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


def option_pills(parent: tk.Widget, options: list[str], var: tk.StringVar) -> tk.Frame:
    """A row of mutually-exclusive pill buttons backed by a StringVar."""
    frame = tk.Frame(parent, bg=BG)
    btns: dict[str, tk.Button] = {}

    def select(val: str):
        var.set(val)
        for v, b in btns.items():
            if v == val:
                b.config(bg=ACCENT, fg="#0f0f0f",
                         activebackground=ACCENT, activeforeground="#0f0f0f")
            else:
                b.config(bg=SURFACE3, fg=TEXT,
                         activebackground=SURFACE2, activeforeground=TEXT)

    for label in options:
        is_active = var.get() == label
        b = tk.Button(
            frame, text=label, font=("Segoe UI", 9),
            bg=ACCENT if is_active else SURFACE3,
            fg="#0f0f0f" if is_active else TEXT,
            activebackground=ACCENT if is_active else SURFACE2,
            activeforeground="#0f0f0f" if is_active else TEXT,
            relief="flat", bd=0, padx=11, pady=5, cursor="hand2",
            command=lambda v=label: select(v),
        )
        b.pack(side="left", padx=(0, 4))
        btns[label] = b

    return frame


def spinbox(parent: tk.Widget, var: tk.IntVar,
            from_: int, to: int, width: int = 5) -> tk.Spinbox:
    # used to return the frame too, but nothing ever needed it — simplified
    sb = tk.Spinbox(
        parent, from_=from_, to=to, textvariable=var,
        font=FUI, bg=SURFACE2, fg=TEXT,
        buttonbackground=SURFACE3, relief="flat", bd=0,
        highlightthickness=1, highlightbackground=BORDER,
        width=width, insertbackground=ACCENT,
    )
    sb.pack(side="left", ipady=4, padx=(0, 8))
    return sb


def section_label(parent: tk.Widget, text: str) -> None:
    """Small grey ALL-CAPS section header, packed to the left."""
    tk.Label(parent, text=text, font=("Segoe UI", 8),
             bg=BG, fg=MUTED).pack(anchor="w", pady=(14, 6))
