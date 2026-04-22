"""
preset_editor.py — the modal dialog for creating and editing caption presets.

Split into two tabs: Style (typography + colour + live 16:9 preview) and
Position (screen grid, fine-tune offsets, alignment, safe zone).

This got pretty big. Considered splitting into separate files but it all
depends on shared state so not worth it right now. TODO: maybe someday.
"""

import tkinter as tk
from tkinter import font as tkfont

from .theme import (
    BG, SURFACE, SURFACE2, SURFACE3, BORDER, ACCENT, TEXT, MUTED, MUTED2,
    FUI, FSM, FXSM, FBIG, FBOLD,
)
from .presets  import PRESET_DEFAULTS
from .widgets  import (
    ScrollFrame, get_system_fonts,
    color_widget, pill_toggle, option_pills, spinbox, section_label,
)

# 3×3 quick-position grid: (label, x%, y%)
GRID_POSITIONS = [
    ("top-left",     0,  10), ("top-center",    50,  10), ("top-right",   100,  10),
    ("mid-left",     0,  50), ("mid-center",    50,  50), ("mid-right",   100,  50),
    ("bottom-left",  0,  85), ("bottom-center", 50,  85), ("bottom-right",100,  85),
]

PREVIEW_TEXT = "This is a subtitle preview"


class PresetEditor(tk.Toplevel):

    def __init__(self, parent: tk.Widget, preset: dict | None = None, on_save=None):
        super().__init__(parent)
        self.title("Edit Preset")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.geometry("870x660")
        self.on_save = on_save
        self.grab_set()

        # Fill missing keys from defaults
        # doing this here AND in load_presets because older saved presets might
        # come through the edit flow directly without going through loader
        p = preset or {
            **PRESET_DEFAULTS,
            "name": "My Preset", "font": "Arial", "size": 72,
            "bold": False, "italic": False,
            "color": "#FFFFFF", "outline": True,
            "outline_color": "#000000", "outline_w": 4,
            "shadow": False, "shadow_color": "#000000",
            "position": "bottom", "builtin": False,
        }
        for k, v in PRESET_DEFAULTS.items():
            p.setdefault(k, v)

        self.vars = {
            "name":           tk.StringVar(value=p["name"]),
            "font":           tk.StringVar(value=p["font"]),
            "size":           tk.IntVar(value=p["size"]),
            "bold":           tk.BooleanVar(value=p.get("bold",   False)),
            "italic":         tk.BooleanVar(value=p.get("italic", False)),
            "caps":           tk.BooleanVar(value=p.get("caps",   False)),
            "letter_spacing": tk.IntVar(value=p.get("letter_spacing", 0)),
            "line_height":    tk.IntVar(value=p.get("line_height",  100)),
            "color":          tk.StringVar(value=p.get("color",         "#FFFFFF")),
            "outline":        tk.BooleanVar(value=p.get("outline",      True)),
            "outline_color":  tk.StringVar(value=p.get("outline_color", "#000000")),
            "outline_w":      tk.IntVar(value=p.get("outline_w",  4)),
            "shadow":         tk.BooleanVar(value=p.get("shadow",       False)),
            "shadow_color":   tk.StringVar(value=p.get("shadow_color",  "#000000")),
            "position":       tk.StringVar(value=p.get("position",      "bottom")),
            "x_offset":       tk.IntVar(value=p.get("x_offset",  50)),
            "y_offset":       tk.IntVar(value=p.get("y_offset",  85)),
            "text_align":     tk.StringVar(value=p.get("text_align",    "Center")),
            "max_width":      tk.IntVar(value=p.get("max_width",  80)),
            "safe_zone":      tk.BooleanVar(value=p.get("safe_zone",      True)),
            "show_safe_zone": tk.BooleanVar(value=p.get("show_safe_zone", False)),
        }

        for v in self.vars.values():
            v.trace_add("write", lambda *_: self.after_idle(self.refreshUI))

        self._tab_frames: dict[str, tk.Frame] = {}
        self._tab_btns:   dict[str, tk.Button] = {}
        self._grid_btns:  dict[str, tk.Button] = {}
        self._active_tab  = "Style"
        self._font_popup  = None

        self._build_shell()
        self._show_tab("Style")
        self.after(100, self.refreshUI)

    # ── shell: header + tab bar + footer ──────────────────────────────────────

    def _build_shell(self) -> None:
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=22, pady=(18, 0))
        tk.Label(hdr, text="Edit Preset",        font=FBIG, bg=BG, fg=TEXT  ).pack(side="left")
        tk.Label(hdr, text=" — ",                font=FBIG, bg=BG, fg=MUTED ).pack(side="left")
        tk.Label(hdr, textvariable=self.vars["name"], font=FBIG, bg=BG, fg=ACCENT).pack(side="left")

        nr = tk.Frame(self, bg=BG)
        nr.pack(fill="x", padx=22, pady=(6, 14))
        tk.Label(nr, text="Name", font=FSM, bg=BG, fg=MUTED, width=6, anchor="w").pack(side="left")
        tk.Entry(
            nr, textvariable=self.vars["name"], font=FUI,
            bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
            relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER, width=30,
        ).pack(side="left", ipady=5, ipadx=6)

        tab_bar = tk.Frame(self, bg=BG)
        tab_bar.pack(fill="x", padx=22)
        for name in ("Style", "Position"):
            frame = tk.Frame(tab_bar, bg=BG)
            frame.pack(side="left")
            btn = tk.Button(
                frame, text=name, font=("Segoe UI", 10),
                relief="flat", bd=0, padx=14, pady=8, cursor="hand2", bg=BG,
                command=lambda n=name: self._show_tab(n),
            )
            btn.pack(side="left")
            self._tab_btns[name] = btn

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        self._content_area = tk.Frame(self, bg=BG)
        self._content_area.pack(fill="both", expand=True)

        self._tab_frames["Style"]    = self.build_left_panel(self._content_area)
        self._tab_frames["Position"] = self.build_pos_panel(self._content_area)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=22, pady=12)
        tk.Button(
            foot, text="Save Preset", font=FBOLD,
            bg=ACCENT, fg="#0f0f0f",
            activebackground="#d4eb2a", activeforeground="#0f0f0f",
            relief="flat", bd=0, padx=22, pady=10, cursor="hand2",
            command=self._save,
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            foot, text="Cancel", font=FBOLD,
            bg=SURFACE2, fg=TEXT,
            activebackground=SURFACE3, activeforeground=TEXT,
            relief="flat", bd=0, padx=22, pady=10, cursor="hand2",
            command=self.destroy,
        ).pack(side="left")
        tk.Label(foot, text="* Premiere XML will include all style properties",
                 font=FXSM, bg=BG, fg=MUTED).pack(side="right")

    def _show_tab(self, name: str) -> None:
        for n, f in self._tab_frames.items():
            f.place_forget()
        self._tab_frames[name].place(relx=0, rely=0, relwidth=1, relheight=1)
        self._active_tab = name
        for n, btn in self._tab_btns.items():
            active = n == name
            btn.config(
                fg=ACCENT if active else MUTED,
                activeforeground=ACCENT if active else TEXT,
            )

    # ── Style tab ─────────────────────────────────────────────────────────────
    # "Style" is a misnomer, it's really typography+colour. Position is separate.

    def build_left_panel(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)

        left = tk.Frame(frame, bg=BG, width=310)
        left.pack(side="left", fill="y", padx=(18, 8), pady=12)
        left.pack_propagate(False)

        tk.Frame(frame, bg=BORDER, width=1).pack(side="left", fill="y", pady=12)

        right = tk.Frame(frame, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(12, 18), pady=12)

        # Scrollable controls on the left
        sf  = ScrollFrame(left, bg=BG)
        sf.pack(fill="both", expand=True)
        inn = sf.inner

        section_label(inn, "TYPOGRAPHY")

        fr = tk.Frame(inn, bg=BG)
        fr.pack(fill="x", pady=(0, 8))
        tk.Label(fr, text="Font", font=FSM, bg=BG, fg=MUTED, width=14, anchor="w").pack(side="left")
        self._font_entry_widget(fr)

        sr = tk.Frame(inn, bg=BG)
        sr.pack(fill="x", pady=(0, 8))
        tk.Label(sr, text="Size (pt)", font=FSM, bg=BG, fg=MUTED, width=14, anchor="w").pack(side="left")
        spinbox(sr, self.vars["size"], 20, 200, 4)
        tg = tk.Frame(sr, bg=BG)
        tg.pack(side="left")
        pill_toggle(tg, "Bold",   self.vars["bold"]).pack(side="left", padx=(0, 3))
        pill_toggle(tg, "Italic", self.vars["italic"]).pack(side="left", padx=(0, 3))
        pill_toggle(tg, "Caps",   self.vars["caps"]).pack(side="left")

        lsr = tk.Frame(inn, bg=BG)
        lsr.pack(fill="x", pady=(0, 8))
        tk.Label(lsr, text="Letter spacing", font=FSM, bg=BG, fg=MUTED,
                 width=14, anchor="w").pack(side="left")
        spinbox(lsr, self.vars["letter_spacing"], -20, 100, 4)
        spinbox(lsr, self.vars["line_height"],     50, 200, 4)
        tk.Label(lsr, text="%", font=FSM, bg=BG, fg=MUTED).pack(side="left")

        section_label(inn, "COLOUR")

        cr = tk.Frame(inn, bg=BG)
        cr.pack(fill="x", pady=(0, 8))
        tk.Label(cr, text="Text", font=FSM, bg=BG, fg=MUTED, width=14, anchor="w").pack(side="left")
        color_widget(cr, self.vars["color"]).pack(side="left")

        tk.Checkbutton(inn, text="Outline", variable=self.vars["outline"],
                       font=FSM, bg=BG, fg=TEXT, selectcolor=SURFACE2,
                       activebackground=BG, activeforeground=TEXT,
                       command=self.refreshUI).pack(anchor="w", pady=(0, 4))

        od = tk.Frame(inn, bg=BG)
        od.pack(fill="x", pady=(0, 4), padx=(16, 0))
        tk.Label(od, text="Color", font=FSM, bg=BG, fg=MUTED, width=12, anchor="w").pack(side="left")
        color_widget(od, self.vars["outline_color"]).pack(side="left")

        ow = tk.Frame(inn, bg=BG)
        ow.pack(fill="x", pady=(0, 8), padx=(16, 0))
        tk.Label(ow, text="Width", font=FSM, bg=BG, fg=MUTED, width=12, anchor="w").pack(side="left")
        spinbox(ow, self.vars["outline_w"], 1, 20, 4)

        tk.Checkbutton(inn, text="Shadow", variable=self.vars["shadow"],
                       font=FSM, bg=BG, fg=TEXT, selectcolor=SURFACE2,
                       activebackground=BG, activeforeground=TEXT,
                       command=self.refreshUI).pack(anchor="w", pady=(0, 4))

        sd = tk.Frame(inn, bg=BG)
        sd.pack(fill="x", pady=(0, 8), padx=(16, 0))
        tk.Label(sd, text="Color", font=FSM, bg=BG, fg=MUTED, width=12, anchor="w").pack(side="left")
        color_widget(sd, self.vars["shadow_color"]).pack(side="left")

        # 16:9 live preview canvas on the right
        tk.Label(right, text="16:9 preview", font=FXSM, bg=BG, fg=MUTED).pack(anchor="w")

        canvas_outer = tk.Frame(right, bg=SURFACE, highlightthickness=1, highlightbackground=BORDER)
        canvas_outer.pack(fill="both", expand=True)

        self._preview_canvas = tk.Canvas(canvas_outer, bg="#161616",
                                          highlightthickness=0, relief="flat")
        self._preview_canvas.pack(fill="both", expand=True)
        self._preview_canvas.bind("<Configure>", lambda _e: self.after_idle(self.refreshUI))

        return frame

    # ── font entry widget (entry + searchable popup) ──────────────────────────

    def _font_entry_widget(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)
        frame.pack(side="left")

        fonts = get_system_fonts()
        current = self.vars["font"].get()
        if current not in fonts:
            fonts = [current] + fonts
        self._all_fonts = fonts

        row = tk.Frame(frame, bg=SURFACE2, highlightthickness=1, highlightbackground=BORDER)
        row.pack(fill="x")

        self._font_display = tk.Entry(
            row, textvariable=self.vars["font"], font=FUI,
            bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
            relief="flat", bd=0, highlightthickness=0, width=18,
        )
        self._font_display.pack(side="left", ipady=5, ipadx=6)

        arrow = tk.Label(row, text="▾", font=("Segoe UI", 9),
                         bg=SURFACE2, fg=MUTED, cursor="hand2", padx=4)
        arrow.pack(side="right")

        self._font_popup = None

        def toggle_popup(_e=None):
            if self._font_popup and self._font_popup.winfo_exists():
                self._close_font_popup()
            else:
                self._open_font_popup(row, fonts)

        arrow.bind("<Button-1>", toggle_popup)
        self._font_display.bind("<Button-1>", toggle_popup)
        self._font_display.bind("<KeyRelease>", lambda _e: self._filter_font_popup())

        return frame

    def _open_font_popup(self, anchor_widget: tk.Widget, fonts: list[str]) -> None:
        anchor_widget.update_idletasks()
        x = anchor_widget.winfo_rootx()
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 2
        w = anchor_widget.winfo_width() + 40

        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.geometry(f"{w}x220+{x}+{y}")
        popup.configure(bg=BORDER)
        popup.attributes("-topmost", True)
        self._font_popup = popup

        search_var   = tk.StringVar()
        search_entry = tk.Entry(
            popup, textvariable=search_var, font=FUI,
            bg=SURFACE3, fg=TEXT, insertbackground=ACCENT,
            relief="flat", bd=0, highlightthickness=1, highlightbackground=ACCENT,
        )
        search_entry.pack(fill="x", padx=1, pady=(1, 0), ipady=5)
        search_entry.focus_set()

        lb_frame = tk.Frame(popup, bg=SURFACE)
        lb_frame.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        sb = tk.Scrollbar(lb_frame, orient="vertical", bg=SURFACE2,
                          troughcolor=SURFACE, relief="flat", bd=0, width=6)
        lb = tk.Listbox(
            lb_frame, font=FUI, bg=SURFACE, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#0f0f0f",
            relief="flat", bd=0, highlightthickness=0, activestyle="none",
            yscrollcommand=sb.set,
        )
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        self._font_listbox = lb

        def populate(filter_text: str = "") -> None:
            lb.delete(0, "end")
            ft = filter_text.lower()
            matches = [f for f in self._all_fonts if ft in f.lower()]
            for f in matches:
                lb.insert("end", f)
            cur = self.vars["font"].get()
            for i, f in enumerate(matches):
                if f == cur:
                    lb.selection_set(i)
                    lb.see(i)
                    break

        populate()
        self._font_popup_populate = populate

        search_var.trace_add("write", lambda *_: populate(search_var.get()))

        lb.bind("<MouseWheel>", lambda e: lb.yview_scroll(int(-1*(e.delta/120)), "units"))

        def on_select(_e=None):
            sel = lb.curselection()
            if sel:
                self.vars["font"].set(lb.get(sel[0]))
            self._close_font_popup()

        lb.bind("<ButtonRelease-1>", on_select)
        lb.bind("<Return>", on_select)
        search_entry.bind("<Return>",  on_select)
        search_entry.bind("<Escape>",  lambda _e: self._close_font_popup())
        search_entry.bind("<Down>",    lambda _e: lb.focus_set())

        popup.bind("<FocusOut>", lambda _e: self.after(100, self._maybe_close_popup))

    def _maybe_close_popup(self) -> None:
        try:
            if self._font_popup and self._font_popup.winfo_exists():
                if self._font_popup.focus_get() is None:
                    self._close_font_popup()
        except Exception:
            pass

    def _close_font_popup(self) -> None:
        try:
            if self._font_popup and self._font_popup.winfo_exists():
                self._font_popup.destroy()
        except Exception:
            pass
        self._font_popup = None

    def _filter_font_popup(self) -> None:
        if self._font_popup and self._font_popup.winfo_exists():
            self._font_popup_populate(self.vars["font"].get())

    # ── Position tab ─────────────────────────────────────────────────────────
    # this tab is a bit overbuilt for what it does, but the grid felt important

    def build_pos_panel(self, parent: tk.Widget) -> tk.Frame:
        frame = tk.Frame(parent, bg=BG)

        left  = tk.Frame(frame, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(24, 16), pady=12)
        right = tk.Frame(frame, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(16, 24), pady=12)

        # 3×3 position grid + fine-tune
        section_label(left, "SCREEN POSITION")
        pos_row = tk.Frame(left, bg=BG)
        pos_row.pack(anchor="w", pady=(0, 16))

        gf = tk.Frame(pos_row, bg=BG)
        gf.pack(side="left", padx=(0, 24))
        tk.Label(gf, text="Grid", font=FXSM, bg=BG, fg=MUTED).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

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
            b = tk.Button(
                gf, width=3, height=1,
                bg=ACCENT if is_sel else SURFACE2,
                activebackground=ACCENT, relief="flat", bd=0,
                highlightthickness=1, highlightbackground=BORDER,
                cursor="hand2",
                command=make_grid_cmd(gname, gx, gy),
            )
            b.grid(row=ri, column=ci, padx=2, pady=2)
            self._grid_btns[gname] = b

        # Fine-tune spinboxes
        ft = tk.Frame(pos_row, bg=BG)
        ft.pack(side="left")
        tk.Label(ft, text="Fine-tune (%)", font=FXSM, bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 6))

        for axis, var_key in (("X offset", "x_offset"), ("Y offset", "y_offset")):
            row = tk.Frame(ft, bg=BG)
            row.pack(anchor="w", pady=(0, 6))
            tk.Label(row, text=axis, font=FSM, bg=BG, fg=MUTED, width=8, anchor="w").pack(side="left")
            tk.Entry(
                row, textvariable=self.vars[var_key], font=FUI,
                bg=SURFACE2, fg=TEXT, insertbackground=ACCENT,
                relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER, width=6,
            ).pack(side="left", ipady=5, ipadx=4)

        tk.Label(ft, text="0,0 = top-left   100,100 = bottom-right",
                 font=FXSM, bg=BG, fg=MUTED2).pack(anchor="w", pady=(4, 0))

        # Right: alignment, max width, safe zone
        section_label(right, "TEXT ALIGNMENT")
        option_pills(right, ["Left", "Center", "Right"], self.vars["text_align"]).pack(anchor="w", pady=(0, 14))

        section_label(right, "MAX WIDTH")
        mwr = tk.Frame(right, bg=BG)
        mwr.pack(anchor="w", pady=(0, 4))
        tk.Label(mwr, text="% of screen", font=FSM, bg=BG, fg=MUTED).pack(side="left", padx=(0, 8))
        tk.Scale(
            mwr, variable=self.vars["max_width"], from_=20, to=100,
            orient="horizontal", bg=BG, fg=MUTED, troughcolor=SURFACE2,
            highlightthickness=0, bd=0, length=160,
            sliderrelief="flat", sliderlength=10, showvalue=False,
        ).pack(side="left")
        mw_lbl = tk.Label(mwr, font=FSM, bg=BG, fg=TEXT, width=3)
        mw_lbl.pack(side="left", padx=(4, 0))
        tk.Label(mwr, text="%", font=FSM, bg=BG, fg=MUTED).pack(side="left")

        def upd_mw(*_):
            mw_lbl.config(text=str(self.vars["max_width"].get()))
        self.vars["max_width"].trace_add("write", upd_mw)
        upd_mw()

        section_label(right, "SAFE ZONE")
        for text, var_key in (
            ("Snap to broadcast safe area", "safe_zone"),
            ("Show safe zone in preview",   "show_safe_zone"),
        ):
            tk.Checkbutton(
                right, text=text, variable=self.vars[var_key],
                font=FSM, bg=BG, fg=TEXT, selectcolor=SURFACE2,
                activebackground=BG,
            ).pack(anchor="w", pady=(0, 6))

        return frame

    # ── preview renderer ──────────────────────────────────────────────────────

    def _alpha_color(self, hex_color: str, alpha: float) -> str:
        try:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except Exception:
            return hex_color
        bg_r, bg_g, bg_b = 0x16, 0x16, 0x16
        a  = max(0.0, min(1.0, alpha))
        nr = int(r * a + bg_r * (1 - a))
        ng = int(g * a + bg_g * (1 - a))
        nb = int(b * a + bg_b * (1 - a))
        return f"#{nr:02x}{ng:02x}{nb:02x}"

    # was _refresh_preview — renamed to match app.py style
    # the outline pixel loop is O(n²) but canvas is tiny so whatever
    def refreshUI(self, *_) -> None:
        if not hasattr(self, "_preview_canvas"):
            return
        c = self._preview_canvas
        c.delete("all")

        cw = c.winfo_width()
        ch = c.winfo_height()
        if cw < 10 or ch < 10:
            return

        # Background grid
        for gx in range(0, cw, 40):
            c.create_line(gx, 0, gx, ch, fill="#1e1e1e", width=1)
        for gy in range(0, ch, 40):
            c.create_line(0, gy, cw, gy, fill="#1e1e1e", width=1)

        # Safe zone outline
        if self.vars.get("show_safe_zone") and self.vars["show_safe_zone"].get():
            m = 0.1
            c.create_rectangle(
                int(cw*m), int(ch*m), int(cw*(1-m)), int(ch*(1-m)),
                outline="#334433", width=1, dash=(4, 4),
            )

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
        weight = "bold"   if bold   else "normal"
        slant  = "italic" if italic else "roman"

        try:
            fnt = tkfont.Font(family=font_name, size=preview_size, weight=weight, slant=slant)
        except Exception:
            fnt = tkfont.Font(size=preview_size)

        text = PREVIEW_TEXT
        if self.vars["caps"].get():
            text = text.upper()

        x = int(cw * x_off / 100)
        y = int(ch * y_off / 100)

        if outline:
            ow_px = max(1, outline_w // 2)
            for dx in range(-ow_px, ow_px + 1):
                for dy in range(-ow_px, ow_px + 1):
                    if dx == 0 and dy == 0:
                        continue
                    c.create_text(x+dx, y+dy, text=text, font=fnt, fill=outline_c, anchor="center")

        if shadow:
            c.create_text(x+2, y+2, text=text, font=fnt, fill=shadow_c, anchor="center")

        c.create_text(x, y, text=text, font=fnt, fill=color, anchor="center")

        # Position badge
        pos_name = "custom"
        for gname, gx, gy in GRID_POSITIONS:
            if gx == x_off and gy == y_off:
                pos_name = gname
                break
        badge_txt = f"position: {pos_name}"
        bx, by    = cw - 8, ch - 8
        text_id   = c.create_text(bx, by, text=badge_txt, font=("Segoe UI", 8),
                                   fill="#0f0f0f", anchor="se")
        bb = c.bbox(text_id)
        if bb:
            c.create_rectangle(bb[0]-4, bb[1]-3, bb[2]+4, bb[3]+3,
                               fill="#e8ff47", outline="", tags="badge_bg")
            c.tag_raise(text_id)
            c.itemconfig(text_id, fill="#0f0f0f")
        c.tag_lower("badge_bg")

    # ── save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        result = {k: v.get() for k, v in self.vars.items()}
        result["builtin"] = False
        y = result.get("y_offset", 85)
        result["position"] = "top" if y <= 20 else ("center" if y <= 60 else "bottom")
        if self.on_save:
            self.on_save(result)
        self.destroy()
