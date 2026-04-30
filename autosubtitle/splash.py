import tkinter as tk

from .paths  import AUTHOR
from .theme  import BG, ACCENT, TEXT, MUTED, MUTED2, BORDER, FSM, FXSM, _ICON_B64


class SplashScreen(tk.Toplevel):
    W, H = 460, 295

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=BG)
        self.attributes("-topmost", True)

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{self.W}x{self.H}+{(sw - self.W) // 2}+{(sh - self.H) // 2}")

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
        tk.Label(row, text="Auto",     font=("Segoe UI", 28, "bold"), bg=BG, fg=TEXT  ).pack(side="left")
        tk.Label(row, text="Subtitle", font=("Segoe UI", 28, "bold"), bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(row, text=" *",       font=("Segoe UI", 28, "bold"), bg=BG, fg=ACCENT).pack(side="left")

        tk.Label(body, text="Smart subtitles for Adobe Premiere Pro",
                 font=FSM, bg=BG, fg=MUTED).pack(anchor="w", pady=(4, 0))

        tk.Frame(body, bg=BG, height=22).pack()

        self._status_var = tk.StringVar(value="Starting…")
        tk.Label(body, textvariable=self._status_var, font=FXSM, bg=BG, fg=MUTED).pack(anchor="w")

        pb_wrap = tk.Frame(body, bg=BORDER, height=4)
        pb_wrap.pack(fill="x", pady=(6, 0))
        pb_wrap.pack_propagate(False)

        self._pb      = tk.Canvas(pb_wrap, bg=BORDER, height=4, highlightthickness=0, bd=0)
        self._pb.pack(fill="both", expand=True)
        self._bar     = self._pb.create_rectangle(0, 0, 0, 4, fill=ACCENT, outline="")
        self._progress = 0.0
        self._target   = 0.0
        self._anim_id  = None
        self._closed   = False   # guard against after() firing post-destroy

        tk.Frame(body, bg=BG, height=16).pack()
        tk.Label(body, text=AUTHOR, font=FXSM, bg=BG, fg=MUTED2).pack(anchor="w")

        self.update()

    # ── public API ────────────────────────────────────────────────────────────

    def advance_to(self, frac: float, msg: str = "") -> None:
        """Animate the progress bar to *frac* (0.0–1.0) and update the status label."""
        self._target = min(1.0, frac)
        self._status_var.set(msg)
        if self._anim_id:
            self.after_cancel(self._anim_id)
        self._step()

    def close(self) -> None:
        self._closed = True          # must set BEFORE cancel so any in-flight _step exits
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None
        self.destroy()

    # ── animation internals ───────────────────────────────────────────────────

    def _step(self) -> None:
        if self._closed:
            return
        if self._progress < self._target:
            self._progress = min(self._progress + 0.018, self._target)
            self._draw_bar()
            # only schedule the next frame if we haven't been closed
            if not self._closed:
                self._anim_id = self.after(16, self._step)
        else:
            self.update_idletasks()

    def _draw_bar(self) -> None:
        # Never call self.update() here — it re-enters the event loop and lets
        # close() fire mid-animation, leaving a dangling after() callback that
        # then tries to draw on a destroyed canvas (the original crash).
        if self._closed:
            return
        try:
            w = self._pb.winfo_width()
            if w > 1:
                self._pb.coords(self._bar, 0, 0, int(w * self._progress), 4)
            self._pb.update_idletasks()
        except tk.TclError:
            pass   # window was destroyed between the guard check and here — safe to ignore
