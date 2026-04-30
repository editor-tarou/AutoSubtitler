"""
app.py — the main application window.

Wires everything together: splash screen, preset management, transcription
settings, the generate button, and the log output panel.

Started as a single 200-line script, grew into this. Some parts are messier
than I'd like but it works and I'm scared to touch the preset wiring again.
"""

import os
import json
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
from .edition      import IS_PRO, EDITION, reload_edition
from .license      import validate_key, save_key, load_saved_key, remove_key
from .transcribe   import SEG_STYLES, MODELS, LANGUAGES, check_dependencies, run_transcription
from .widgets      import get_system_fonts, style_optionmenu
from .splash       import SplashScreen
from .tutorial     import TutorialOverlay
from .preset_editor import PresetEditor
from .sounds        import play_complete, play_error, play_activate, play_startup, prewarm

# First-run flag — stored next to presets/license data
from .paths import AUTHOR as _AUTHOR
import pathlib
_DATA_DIR   = pathlib.Path(os.environ.get("APPDATA", "~")).expanduser() / "AutoSubtitle"
_FIRST_RUN  = _DATA_DIR / ".first_run_done"


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

        self.title("AutoSubtitle" + (" Pro" if IS_PRO else " Lite"))
        self.configure(bg=BG)
        self.resizable(False, True)
        self.geometry("620x940")
        self.minsize(620, 860)

        splash.advance_to(0.20, "Loading interface…")
        self.file_path  = tk.StringVar(value="")
        self.seg_style  = tk.StringVar(value="Balanced - 3-5 words")
        self.model_var  = tk.StringVar(value="medium")
        self.lang_var   = tk.StringVar(value="auto")
        self.nle_var    = tk.StringVar(value="Premiere")
        self.fmt_premiere = tk.StringVar(value="SRT")
        self.fmt_resolve  = tk.StringVar(value="ASS" if IS_PRO else "SRT")
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
        self.after(380, lambda: (splash.close(), self.deiconify(), play_startup()))
        prewarm()  # build all sounds in background so first play is instant

        # Auto-launch tutorial on first run, then never again
        if not _FIRST_RUN.exists():
            try:
                _DATA_DIR.mkdir(parents=True, exist_ok=True)
                _FIRST_RUN.touch()
            except OSError:
                pass
            self.after(900, lambda: TutorialOverlay(self))

    # ── UI construction ───────────────────────────────────────────────────────

    def _build(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=24, pady=(28, 0))
        tk.Label(hdr, text="AutoSubtitle", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text=" *", font=("Segoe UI", 18, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left")
        # edition badge
        badge_text  = "  PRO" if IS_PRO else "  LITE"
        badge_color = ACCENT if IS_PRO else MUTED
        tk.Label(hdr, text=badge_text, font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=badge_color).pack(side="left", padx=(2, 0))
        tk.Button(
            hdr, text="?  Tutorial", font=FSM,
            bg=SURFACE2, fg=ACCENT,
            activebackground=SURFACE3, activeforeground=ACCENT,
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=lambda: TutorialOverlay(self),
        ).pack(side="right")

        # License button — shows "Unlock Pro" on Lite, "License" on Pro
        _lic_text  = "🔑  License" if IS_PRO else "🔑  Unlock Pro"
        _lic_fg    = MUTED if IS_PRO else ACCENT
        tk.Button(
            hdr, text=_lic_text, font=FSM,
            bg=SURFACE2, fg=_lic_fg,
            activebackground=SURFACE3, activeforeground=_lic_fg,
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2",
            command=lambda: LicenseDialog(self),
        ).pack(side="right", padx=(0, 6))

        tk.Label(self, text="Smart subtitles for your editing flow",
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
            self._drop_frame.dnd_bind("<<Drop>>",         self._on_drop)
            self._drop_frame.dnd_bind("<<DragEnter>>",    self._on_drag_enter)
            self._drop_frame.dnd_bind("<<DragLeave>>",    self._on_drag_leave)
            self._file_label.drop_target_register(DND_FILES)
            self._file_label.dnd_bind("<<Drop>>",         self._on_drop)
            self._file_label.dnd_bind("<<DragEnter>>",    self._on_drag_enter)
            self._file_label.dnd_bind("<<DragLeave>>",    self._on_drag_leave)

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

        _btn_state = "normal" if IS_PRO else "disabled"
        _btn_fg    = TEXT if IS_PRO else MUTED

        tk.Button(btns, text="New", font=FSM, bg=SURFACE2, fg=_btn_fg,
                  activebackground=BORDER, relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2" if IS_PRO else "arrow",
                  state=_btn_state,
                  command=self._new_preset).pack(side="left", padx=(0, 4))
        self._edit_btn = tk.Button(btns, text="Edit", font=FSM, bg=SURFACE2, fg=_btn_fg,
                  activebackground=BORDER, relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2" if IS_PRO else "arrow",
                  state=_btn_state,
                  command=self._edit_preset)
        self._edit_btn.pack(side="left", padx=(0, 4))
        self._del_btn = tk.Button(btns, text="Delete", font=FSM, bg=SURFACE2, fg=MUTED if not IS_PRO else ERROR,
                  activebackground=BORDER, relief="flat", bd=0, padx=12, pady=6,
                  cursor="hand2" if IS_PRO else "arrow",
                  state=_btn_state,
                  command=self._delete_preset)
        self._del_btn.pack(side="left")

        if not IS_PRO:
            tk.Label(prow, text="  ★ Pro", font=FXSM, bg=BG, fg=MUTED2).grid(row=0, column=2, padx=(6, 0))

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
        tk.Label(ff, text="Export for", font=FSM, bg=BG, fg=MUTED).pack(anchor="w")
        nle_row = tk.Frame(ff, bg=BG)
        nle_row.pack(anchor="w", pady=(4, 0))
        for nle in ("Premiere", "Resolve"):
            tk.Radiobutton(
                nle_row, text=nle, variable=self.nle_var, value=nle,
                font=FUI, bg=BG, fg=TEXT, selectcolor=SURFACE2,
                activebackground=BG, activeforeground=TEXT,
                command=self._update_nle_panel,
            ).pack(side="left", padx=(0, 10))

        # sub-panel that swaps depending on which NLE is selected
        self._nle_panel = tk.Frame(ff, bg=BG)
        self._nle_panel.pack(anchor="w", pady=(6, 0))
        self._update_nle_panel()

        self._div()

        # Generate button — slightly oversized on purpose, it's the whole point of the app
        self._btn = tk.Button(
            self, text="Generate Subtitles  →",
            font=("Segoe UI", 11, "bold"), bg=ACCENT, fg="#0f0f0f",
            activebackground="#d4eb2a", activeforeground="#0f0f0f",
            relief="flat", bd=0, pady=16, cursor="hand2",
            command=self._run,
        )
        self._btn.pack(fill="x", padx=24, pady=(0, 8))

        # Progress bar — hidden until a run starts
        self._prog_frame = tk.Frame(self, bg=BG, height=24)
        self._prog_frame.pack(fill="x", padx=24, pady=(0, 12))
        self._prog_frame.pack_propagate(False)

        self._prog_track = tk.Frame(self._prog_frame, bg=SURFACE2,
                                    highlightthickness=1, highlightbackground=BORDER,
                                    height=6)
        self._prog_track.place(x=0, y=0, relwidth=1)
        self._prog_track.pack_propagate(False)

        self._prog_fill = tk.Frame(self._prog_track, bg=ACCENT, height=6)
        self._prog_fill.place(x=0, y=0, relheight=1, relwidth=0)

        self._prog_label = tk.Label(self._prog_frame, text="", font=FXSM,
                                     bg=BG, fg=MUTED, anchor="w")
        self._prog_label.place(x=0, y=10, relwidth=1)

        # start invisible
        self._prog_frame.config(height=1)
        for w in (self._prog_track, self._prog_label):
            w.place_forget()

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

    def _update_nle_panel(self) -> None:
        # Lite:  Premiere→SRT only  |  Resolve→SRT only
        # Pro:   Premiere→SRT/VTT   |  Resolve→SRT/ASS
        for w in self._nle_panel.winfo_children():
            w.destroy()

        nle = self.nle_var.get()

        if nle == "Premiere":
            if IS_PRO:
                tk.Label(self._nle_panel, text="Format", font=FXSM, bg=BG, fg=MUTED2).pack(anchor="w")
                row = tk.Frame(self._nle_panel, bg=BG)
                row.pack(anchor="w")
                for fmt in ("SRT", "VTT"):
                    tk.Radiobutton(row, text=fmt, variable=self.fmt_premiere, value=fmt,
                                   font=FXSM, bg=BG, fg=MUTED, selectcolor=SURFACE2,
                                   activebackground=BG, activeforeground=TEXT,
                    ).pack(side="left", padx=(0, 8))
            else:
                # Lite — SRT only, no VTT
                self.fmt_premiere.set("SRT")
                tk.Label(self._nle_panel, text="Format: SRT", font=FXSM,
                         bg=BG, fg=MUTED2).pack(anchor="w")
        else:
            # DaVinci Resolve
            if IS_PRO:
                tk.Label(self._nle_panel, text="Format", font=FXSM, bg=BG, fg=MUTED2).pack(anchor="w")
                row = tk.Frame(self._nle_panel, bg=BG)
                row.pack(anchor="w")
                for fmt in ("SRT", "ASS"):
                    lbl = fmt if fmt == "SRT" else "ASS  (full styling)"
                    tk.Radiobutton(row, text=lbl, variable=self.fmt_resolve, value=fmt,
                                   font=FXSM, bg=BG, fg=MUTED, selectcolor=SURFACE2,
                                   activebackground=BG, activeforeground=TEXT,
                    ).pack(side="left", padx=(0, 8))
            else:
                # Lite — SRT only, ASS is Pro
                self.fmt_resolve.set("SRT")
                tk.Label(self._nle_panel, text="Format: SRT   ★ ASS requires Pro",
                         font=FXSM, bg=BG, fg=MUTED2).pack(anchor="w")

    def _on_drag_enter(self, event) -> None:
        self._drop_frame.config(bg=SURFACE2, highlightbackground=ACCENT)
        self._file_label.config(bg=SURFACE2, fg=ACCENT,
                                 text="  Drop it!")

    def _on_drag_leave(self, event) -> None:
        self._drop_frame.config(bg=SURFACE, highlightbackground=BORDER)
        # restore label: if a file is loaded show its name, else show the hint
        if self.file_path.get():
            self._file_label.config(bg=SURFACE, fg=TEXT,
                                     text=f"  {os.path.basename(self.file_path.get())}")
        else:
            hint = "Click or drag & drop  *  mp3  mp4  wav  m4a  mov" if _DND_AVAILABLE else "Click to choose file  *  mp3  mp4  wav  m4a  mov"
            self._file_label.config(bg=SURFACE, fg=MUTED, text=hint)

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
            self._drop_frame.config(bg=SURFACE, highlightbackground=ACCENT)
            self._file_label.config(bg=SURFACE, text=f"  {os.path.basename(path)}", fg=TEXT)
            self._log_clear()
            self._log_write(f"File: {os.path.basename(path)}\n", "muted")
        else:
            self._drop_frame.config(bg=SURFACE, highlightbackground=ERROR)
            self.after(1000, lambda: self._drop_frame.config(highlightbackground=BORDER))
            self._file_label.config(bg=SURFACE)
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
        self._indet_job = None
        self._btn.config(state="disabled", text="Working...", bg=BORDER, fg=MUTED)
        self._log_clear()
        self._show_progress(True)
        self._update_progress(0.0, "Starting…")

        seg_cfg  = SEG_STYLES[self.seg_style.get()]
        mdl      = self.model_var.get()
        lang     = self.lang_var.get()
        nle      = self.nle_var.get()
        fmt      = self.fmt_premiere.get() if nle == "Premiere" else self.fmt_resolve.get()

        def _safe_run():
            try:
                run_transcription(path, mdl, lang, seg_cfg,
                                  self._log_write, self._finish, preset, nle, fmt,
                                  on_progress=lambda f, lbl: self.after(0, self._update_progress, f, lbl),
                                  on_transcribe_start=lambda: self.after(0, self._start_indeterminate, "Transcribing…"))
            except Exception as exc:
                import traceback
                self._log_write(f"\nCrash: {exc}\n", "error")
                self._log_write(traceback.format_exc(), "muted")
                play_error()
                self._finish()

        threading.Thread(target=_safe_run, daemon=True).start()

    def _show_progress(self, visible: bool) -> None:
        if visible:
            self._prog_frame.config(height=24)
            self._prog_track.place(x=0, y=0, relwidth=1)
            self._prog_label.place(x=0, y=10, relwidth=1)
        else:
            self._stop_indeterminate()
            self._prog_frame.config(height=1)
            self._prog_track.place_forget()
            self._prog_label.place_forget()

    def _update_progress(self, frac: float, label: str) -> None:
        """Show a real deterministic fill. Stops any indeterminate animation."""
        self._stop_indeterminate()
        self._prog_fill.place(x=0, relheight=1, relwidth=max(0.0, min(1.0, frac)))
        self._prog_label.config(text=label)

    def _start_indeterminate(self, label: str) -> None:
        """
        Scanning pulse: a fixed-width block slides back and forth.
        Honest — makes no claim about how much work is done.
        """
        self._stop_indeterminate()
        self._prog_label.config(text=label)
        BLOCK = 0.28   # width of the travelling block as a fraction of the track
        STEP  = 0.012
        pos   = [0.0]
        dir_  = [1]

        def _tick():
            pos[0] += STEP * dir_[0]
            if pos[0] + BLOCK >= 1.0:
                pos[0] = 1.0 - BLOCK
                dir_[0] = -1
            elif pos[0] <= 0.0:
                pos[0] = 0.0
                dir_[0] = 1
            self._prog_track.update_idletasks()
            w = self._prog_track.winfo_width()
            if w > 1:
                self._prog_fill.place(x=int(pos[0] * w), relheight=1,
                                      width=int(BLOCK * w))
            self._indet_job = self.after(30, _tick)

        self._indet_job = self.after(0, _tick)

    def _stop_indeterminate(self) -> None:
        if self._indet_job:
            self.after_cancel(self._indet_job)
            self._indet_job = None

    def _finish(self) -> None:
        self.running = False
        play_complete()
        self._update_progress(1.0, "Done!")
        self.after(1800, lambda: self._show_progress(False))
        self._btn.config(state="normal", text="Generate Subtitles  →",
                         bg=ACCENT, fg="#0f0f0f")

# ── License / activation dialog ───────────────────────────────────────────────

class LicenseDialog(tk.Toplevel):
    """
    Modal dialog for entering a Pro license key.

    On a valid key: saves it, reloads the edition flags, and prompts
    the user to restart so the full UI re-initialises in Pro mode.
    On an invalid key: shakes the entry field and shows an inline error.
    """

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.parent   = parent
        self.title("Unlock AutoSubtitle Pro")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()          # modal

        # ── layout ──────────────────────────────────────────────────────
        pad = {"padx": 28, "pady": 0}

        tk.Label(self, text="Enter your license key", font=("Segoe UI", 13, "bold"),
                 bg=BG, fg=TEXT).pack(anchor="w", padx=28, pady=(24, 4))
        tk.Label(self, text="Format: XXXX-XXXX-XXXX-XXXX",
                 font=FXSM, bg=BG, fg=MUTED).pack(anchor="w", **pad)

        self._entry_var = tk.StringVar()
        self._entry = tk.Entry(
            self, textvariable=self._entry_var,
            font=("Segoe UI Mono", 13), bg=SURFACE2, fg=TEXT,
            insertbackground=ACCENT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            width=22,
        )
        self._entry.pack(padx=28, pady=(10, 0), ipady=8, fill="x")
        self._entry.bind("<Return>", lambda _: self._activate())

        # auto-insert dashes as the user types (XXXX-XXXX-XXXX-XXXX)
        self._entry_var.trace_add("write", self._auto_dash)
        self._typing = False

        self._status = tk.Label(self, text="", font=FSM, bg=BG, fg=ERROR)
        self._status.pack(anchor="w", padx=28, pady=(6, 0))

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=28, pady=(16, 24))
        tk.Button(btn_row, text="Cancel", font=FSM, bg=SURFACE2, fg=MUTED,
                  activebackground=BORDER, relief="flat", bd=0,
                  padx=14, pady=8, cursor="hand2",
                  command=self.destroy).pack(side="right", padx=(8, 0))
        tk.Button(btn_row, text="Activate  →", font=FSM, bg=ACCENT, fg="#0f0f0f",
                  activebackground="#d4eb2a", activeforeground="#0f0f0f",
                  relief="flat", bd=0,
                  padx=14, pady=8, cursor="hand2",
                  command=self._activate).pack(side="right")

        # If a key is already saved (but invalid?), prefill it
        saved = load_saved_key()
        if saved:
            self._entry_var.set(saved)
            self._entry.icursor("end")

        # deactivate button at the bottom if already activated
        if IS_PRO:
            tk.Button(btn_row, text="Deactivate", font=FSM, bg=SURFACE2, fg=ERROR,
                      activebackground=BORDER, relief="flat", bd=0,
                      padx=14, pady=8, cursor="hand2",
                      command=self._deactivate).pack(side="left")

        self.update_idletasks()
        # centre over parent
        pw = parent.winfo_x(); ph = parent.winfo_y()
        pw2 = parent.winfo_width(); ph2 = parent.winfo_height()
        w = self.winfo_reqwidth(); h = self.winfo_reqheight()
        self.geometry(f"+{pw + pw2//2 - w//2}+{ph + ph2//2 - h//2}")
        self._entry.focus_set()

    # ── auto-dash ──────────────────────────────────────────────────────
    def _auto_dash(self, *_):
        if self._typing:
            return
        self._typing = True
        raw = self._entry_var.get().upper().replace("-", "").replace(" ", "")
        raw = "".join(c for c in raw if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
        raw = raw[:16]
        parts = [raw[i:i+4] for i in range(0, len(raw), 4)]
        formatted = "-".join(parts)
        self._entry_var.set(formatted)
        self._entry.icursor("end")
        self._typing = False

    # ── activate ───────────────────────────────────────────────────────
    def _activate(self):
        key = self._entry_var.get().strip()
        if not validate_key(key):
            self._status.config(text="Invalid key — please check and try again.", fg=ERROR)
            # shake the entry to give tactile feedback
            x0 = self._entry.winfo_x()
            for dx in (6, -6, 4, -4, 2, -2, 0):
                self._entry.place(x=x0 + dx)
                self.update()
                self.after(30)
            self._entry.pack(padx=28, pady=(10, 0), ipady=8, fill="x")
            return

        if not save_key(key):
            self._status.config(text="Could not save key — check folder permissions.", fg=ERROR)
            return

        reload_edition()
        play_activate()
        self.destroy()
        messagebox.showinfo(
            "Pro Activated!",
            "Your license key is valid.\n\n"
            "Please restart AutoSubtitle to enable all Pro features.",
            parent=self.parent,
        )

    # ── deactivate ─────────────────────────────────────────────────────
    def _deactivate(self):
        if messagebox.askyesno("Deactivate", "Remove your Pro license from this machine?",
                                parent=self):
            remove_key()
            reload_edition()
            self.destroy()
            messagebox.showinfo("Deactivated",
                                "License removed. Restart AutoSubtitle to revert to Lite.",
                                parent=self.parent)
