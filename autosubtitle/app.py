"""
app.py — the main application window.

Wires everything together: splash screen, preset management, transcription
settings, the generate button, and the log output panel.

Started as a single 200-line script, grew into this. Some parts are messier
than I'd like but it works and I'm scared to touch the preset wiring again.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

# drag-and-drop support — falls back gracefully if tkinterdnd2 isn't installed
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

from .theme        import BG, SURFACE, SURFACE2, SURFACE3, BORDER, ACCENT, TEXT, MUTED, MUTED2, ERROR, SUCCESS, FUI, FMONO, FSM, FXSM, FBOLD, _ICON_B64
from .paths        import AUTHOR
from .presets      import load_presets, save_presets
from .transcribe   import SEG_STYLES, MODELS, LANGUAGES, check_dependencies, run_transcription
from .widgets      import get_system_fonts, style_optionmenu
from .splash       import SplashScreen
from .tutorial     import TutorialOverlay
from .preset_editor import PresetEditor


class App(TkinterDnD.Tk if _DND_AVAILABLE else tk.Tk):

    def __init__(self):
        super().__init__()
        self.withdraw()

        splash = SplashScreen(self)
        splash.update()

        try:
            self._icon_img = tk.PhotoImage(data=_ICON_B64)
            self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        self.title("AutoSubtitle")
        self.configure(bg=BG)
        self.resizable(False, True)
        self.geometry("620x940")
        self.minsize(620, 860)

        splash.advance_to(0.20, "Loading interface…")
        self.file_path  = tk.StringVar(value="")
        self.seg_style  = tk.StringVar(value="Balanced - 3-5 words")
        self.model_var  = tk.StringVar(value="medium")
        self.lang_var   = tk.StringVar(value="auto")
        self.format_var = tk.StringVar(value="SRT")
        self.preset_var = tk.StringVar()
        self.running    = False

        splash.advance_to(0.45, "Scanning system fonts…")
        get_system_fonts()   # warm the cache before the UI appears

        splash.advance_to(0.70, "Loading presets…")
        self.presets = load_presets()

        splash.advance_to(0.85, "Building interface…")
        self._build()

        splash.advance_to(0.95, "Checking dependencies…")
        self._refresh_presets()
        self._check_deps()

        splash.advance_to(1.00, "Ready!")
        self.after(380, lambda: (splash.close(), self.deiconify()))

    # ── UI construction ───────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=24, pady=(28, 0))
        tk.Label(hdr, text="AutoSubtitle", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text=" *", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left")
        tk.Button(
            hdr, text="?  Tutorial", font=FSM,
            bg=SURFACE2, fg=ACCENT,
            activebackground=SURFACE3, activeforeground=ACCENT,
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=lambda: TutorialOverlay(self),
        ).pack(side="right")

        tk.Label(self, text="Smart subtitles for Adobe Premiere Pro",
                 font=FSM, bg=BG, fg=MUTED).pack(anchor="w", padx=24, pady=(4, 2))
        tk.Label(self, text=AUTHOR,
                 font=FXSM, bg=BG, fg=MUTED2).pack(anchor="w", padx=24, pady=(0, 20))

        self._div()

        # File picker
        self._section("Audio / Video File")
        self._drop_frame = tk.Frame(self, bg=SURFACE, cursor="hand2",
                        highlightthickness=1, highlightbackground=BORDER)
        self._drop_frame.pack(fill="x", padx=24, pady=(0, 16))
        self._drop_frame.bind("<Button-1>", lambda _e: self._browse())
        self._drop_frame.bind("<Enter>",    lambda _e: self._drop_frame.config(highlightbackground=ACCENT))
        self._drop_frame.bind("<Leave>",    lambda _e: self._drop_frame.config(highlightbackground=BORDER))

        hint = "Click or drag & drop  *  mp3  mp4  wav  m4a  mov" if _DND_AVAILABLE else "Click to choose file  *  mp3  mp4  wav  m4a  mov"
        self._file_label = tk.Label(
            self._drop_frame,
            text=hint,
            font=FUI, bg=SURFACE, fg=MUTED, pady=22, cursor="hand2",
        )
        self._file_label.pack()
        self._file_label.bind("<Button-1>", lambda _e: self._browse())

        # wire up drag-and-drop if tkinterdnd2 is available
        if _DND_AVAILABLE:
            self._drop_frame.drop_target_register(DND_FILES)
            self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            self._file_label.drop_target_register(DND_FILES)
            self._file_label.dnd_bind("<<Drop>>", self._on_drop)

        self._div()

        # Caption preset
        self._section("Caption Preset")
        prow = tk.Frame(self, bg=BG)
        prow.pack(fill="x", padx=24, pady=(0, 8))
        prow.columnconfigure(0, weight=1)

        self._pmenu = tk.OptionMenu(prow, self.preset_var, "")
        style_optionmenu(self._pmenu)
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
        self.preset_var.trace_add("write", lambda *_: self.make_preview())

        self._div()

        # Transcription settings
        # deliberately keeping model + seg on the same row — tried separate sections, looked bloated
        self._section("Transcription Settings")
        opts = tk.Frame(self, bg=BG)
        opts.pack(fill="x", padx=24, pady=(0, 12))
        opts.columnconfigure(0, weight=1)
        opts.columnconfigure(1, weight=1)
        self._seg_om   = self._labeled_optionmenu(opts, "Seg. Style", list(SEG_STYLES.keys()), self.seg_style,  0, 0)
        self._model_om = self._labeled_optionmenu(opts, "Model",      MODELS,                  self.model_var,  0, 1)

        bot_row = tk.Frame(self, bg=BG)
        bot_row.pack(fill="x", padx=24, pady=(0, 24))
        bot_row.columnconfigure(0, weight=1)
        bot_row.columnconfigure(1, weight=0)

        lf = tk.Frame(bot_row, bg=BG)
        lf.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        tk.Label(lf, text="Language", font=FSM, bg=BG, fg=MUTED).pack(anchor="w")
        lm = tk.OptionMenu(lf, self.lang_var, *LANGUAGES)
        style_optionmenu(lm)
        lm.pack(fill="x", pady=(4, 0))
        self._lang_om = lm

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

        # Generate button — slightly oversized on purpose, it's the whole point of the app
        self._btn = tk.Button(
            self, text="Generate Subtitles  →",
            font=("Segoe UI", 11, "bold"), bg=ACCENT, fg="#0f0f0f",
            activebackground="#d4eb2a", activeforeground="#0f0f0f",
            relief="flat", bd=0, pady=16, cursor="hand2",
            command=self._run,
        )
        self._btn.pack(fill="x", padx=24, pady=(0, 28))

        # Log panel — made taller + scrollable so you can actually read transcription output
        self._section("Log")
        lf = tk.Frame(self, bg=SURFACE2, highlightthickness=1, highlightbackground=BORDER)
        lf.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        sb = tk.Scrollbar(lf, orient="vertical", bg=SURFACE2, troughcolor=BG,
                          relief="flat", bd=0, width=6, highlightthickness=0)
        sb.pack(side="right", fill="y")

        self._log = tk.Text(
            lf, height=14, font=FMONO, bg=SURFACE2, fg=TEXT,
            insertbackground=ACCENT, relief="flat", bd=0,
            padx=12, pady=10, state="disabled", wrap="word",
            yscrollcommand=sb.set,
        )
        self._log.pack(side="left", fill="both", expand=True)
        sb.config(command=self._log.yview)
        self._log.tag_config("accent",  foreground=ACCENT)
        self._log.tag_config("success", foreground=SUCCESS)
        self._log.tag_config("error",   foreground=ERROR)
        self._log.tag_config("muted",   foreground=MUTED)

    # ── layout helpers ────────────────────────────────────────────────────────

    def _div(self) -> None:
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=24, pady=(0, 20))

    def _section(self, label: str) -> None:
        tk.Label(self, text=label.upper(), font=FSM, bg=BG, fg=MUTED).pack(
            anchor="w", padx=24, pady=(0, 8))

    def _labeled_optionmenu(self, parent, label, values, var, row, col) -> tk.OptionMenu:
        f = tk.Frame(parent, bg=BG)
        f.grid(row=row, column=col, sticky="ew",
               padx=(0, 12) if col == 0 else 0, pady=(0, 8))
        tk.Label(f, text=label, font=FSM, bg=BG, fg=MUTED).pack(anchor="w")
        m = tk.OptionMenu(f, var, *values)
        style_optionmenu(m)
        m.pack(fill="x", pady=(4, 0))
        return m

    # ── presets ───────────────────────────────────────────────────────────────

    def _refresh_presets(self) -> None:
        menu = self._pmenu["menu"]
        menu.delete(0, "end")
        for p in self.presets:
            menu.add_command(label=p["name"],
                             command=lambda n=p["name"]: self.preset_var.set(n))
        if self.presets:
            cur   = self.preset_var.get()
            names = [p["name"] for p in self.presets]
            self.preset_var.set(cur if cur in names else names[0])

    def _current_preset(self) -> dict | None:
        name = self.preset_var.get()
        return next((p for p in self.presets if p["name"] == name), None)

    def make_preview(self) -> None:
        # used to be called _update_preview, renamed when I added the builtin lock logic
        p = self._current_preset()
        if not p:
            return
        parts = [
            f"Font: {p['font']} {p['size']}pt",
            ("Bold " if p.get("bold") else "") + ("Italic" if p.get("italic") else ""),
            f"Color: {p['color']}",
            f"Outline: {'yes' if p.get('outline') else 'no'}",
            f"Shadow: {'yes' if p.get('shadow') else 'no'}",
            f"Position: {p.get('x_offset', 50)},{p.get('y_offset', 85)}",
        ]
        self._preview.config(text="  *  ".join(s for s in parts if s.strip()))
        builtin = p.get("builtin", False)
        self._edit_btn.config(state="disabled" if builtin else "normal",
                              fg=MUTED if builtin else TEXT)
        self._del_btn.config(state="disabled" if builtin else "normal",
                             fg=MUTED if builtin else ERROR)

    def _new_preset(self) -> None:
        PresetEditor(self, on_save=self._save_new)

    def _save_new(self, preset: dict) -> None:
        if any(p["name"] == preset["name"] for p in self.presets):
            messagebox.showerror("Name taken", f'"{preset["name"]}" already exists.')
            return
        self.presets.append(preset)
        save_presets(self.presets)
        self._refresh_presets()
        self.preset_var.set(preset["name"])

    def _edit_preset(self) -> None:
        p = self._current_preset()
        if not p or p.get("builtin"):
            return
        PresetEditor(self, preset=p,
                     on_save=lambda u: self._save_edited(p["name"], u))

    def _save_edited(self, old_name: str, updated: dict) -> None:
        # replace in-place so list order stays the same
        for i, p in enumerate(self.presets):
            if p["name"] == old_name:
                self.presets[i] = updated
                break
        save_presets(self.presets)
        self._refresh_presets()
        self.preset_var.set(updated["name"])

    def _delete_preset(self) -> None:
        p = self._current_preset()
        if not p or p.get("builtin"):
            return
        # skip confirmation for custom presets? considered it, but too easy to fat-finger
        if messagebox.askyesno("Delete", f'Delete "{p["name"]}"?'):
            self.presets = [x for x in self.presets if x["name"] != p["name"]]
            save_presets(self.presets)
            self._refresh_presets()

    # ── file picker & log ─────────────────────────────────────────────────────

    def _on_drop(self, event) -> None:
        # tkinterdnd2 wraps paths in braces if they have spaces — strip them
        raw = event.data.strip()
        if raw.startswith("{") and raw.endswith("}"):
            raw = raw[1:-1]
        path = raw.split("} {")[0]   # take first file if multiple dropped
        path = path.strip("{}")

        valid_ext = {".mp3", ".mp4", ".wav", ".m4a", ".mov", ".aac", ".flac", ".ogg", ".mkv", ".webm"}
        if os.path.isfile(path) and os.path.splitext(path)[1].lower() in valid_ext:
            self.file_path.set(path)
            self._file_label.config(text=f"  {os.path.basename(path)}", fg=TEXT)
            self._drop_frame.config(highlightbackground=ACCENT)
            self._log_clear()
            self._log_write(f"File: {os.path.basename(path)}\n", "muted")
        else:
            self._drop_frame.config(highlightbackground=ERROR)
            self.after(1000, lambda: self._drop_frame.config(highlightbackground=BORDER))
            self._log_write("Unsupported file type. Drop an mp3, mp4, wav, m4a, mov etc.\n", "error")

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose audio or video file",
            filetypes=[
                ("Media files", "*.mp3 *.mp4 *.wav *.m4a *.mov *.aac *.flac *.ogg"),
                ("All files",   "*.*"),
            ],
        )
        if path:
            self.file_path.set(path)
            self._file_label.config(text=f"  {os.path.basename(path)}", fg=TEXT)
            self._log_clear()
            self._log_write(f"File: {os.path.basename(path)}\n", "muted")

    def _check_deps(self) -> None:
        missing = check_dependencies()
        if missing:
            self._log_write("Missing packages:\n", "error")
            self._log_write(f"  pip install {' '.join(missing)}\n", "accent")
            self._btn.config(state="disabled", bg=BORDER, fg=MUTED)

    def _log_clear(self) -> None:
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    def _log_write(self, text: str, tag: str | None = None) -> None:
        self._log.config(state="normal")
        self._log.insert("end", text, tag or "")
        self._log.see("end")
        self._log.config(state="disabled")

    # ── run ───────────────────────────────────────────────────────────────────

    def _run(self) -> None:
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

        seg_cfg  = SEG_STYLES[self.seg_style.get()]
        mdl      = self.model_var.get()
        lang     = self.lang_var.get()
        fmt      = self.format_var.get()

        def _safe_run():
            try:
                run_transcription(path, mdl, lang, seg_cfg,
                                  self._log_write, self._finish, preset, fmt)
            except Exception as exc:
                import traceback
                self._log_write(f"\nCrash: {exc}\n", "error")
                self._log_write(traceback.format_exc(), "muted")
                self._finish()

        threading.Thread(target=_safe_run, daemon=True).start()

    def _finish(self) -> None:
        self.running = False
        # restore full button weight — wants to feel rewarding to click again
        self._btn.config(state="normal", text="Generate Subtitles  →",
                         bg=ACCENT, fg="#0f0f0f")
