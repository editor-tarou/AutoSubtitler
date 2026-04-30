"""
subtitle_export.py — converts segmented caption cards to SRT, VTT, or ASS.

No GUI or ML imports here on purpose — this can be used or tested standalone.

SRT is simpler and Premiere handles it more reliably. VTT is theoretically
better because it embeds position, but Premiere's VTT parser is quirky.
ASS (Advanced SubStation Alpha) is what DaVinci Resolve uses — it carries
full styling: font, size, colour, bold, italic, outline, shadow, position.
Finally a format that actually respects the preset.
"""


# ── timestamp formatters ──────────────────────────────────────────────────────

def _fmt_srt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hh, ms = divmod(ms, 3_600_000)
    mm, ms = divmod(ms,    60_000)
    ss, ms = divmod(ms,     1_000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _fmt_vtt_ts(seconds: float) -> str:
    # VTT uses dots, SRT uses commas — annoying but that's the spec
    return _fmt_srt_ts(seconds).replace(",", ".")


def _fmt_ass_ts(seconds: float) -> str:
    # ASS uses H:MM:SS.cc (centiseconds, not milliseconds)
    cs = int(round(seconds * 100))
    hh, cs = divmod(cs, 360_000)
    mm, cs = divmod(cs,   6_000)
    ss, cs = divmod(cs,     100)
    return f"{hh}:{mm:02d}:{ss:02d}.{cs:02d}"


# ── card timing helper ────────────────────────────────────────────────────────

def _card_times(cards: list, i: int) -> tuple[float, float]:
    """
    Return (start, end) for card i.

    End time is the *start* of the next card so there's no overlap.
    A minimum duration of 100 ms is enforced.

    Tried using the actual word end times for card end — caused flicker when
    there's a gap before the next card. This approach feels cleaner on screen.
    """
    start = cards[i][0]["start"]
    end   = cards[i + 1][0]["start"] if i + 1 < len(cards) else cards[i][-1]["end"]
    if end - start < 0.1:
        end = start + 0.1
    return start, end


# ── colour helpers ────────────────────────────────────────────────────────────

def _hex_to_ass(hex_color: str, alpha: int = 0) -> str:
    """
    Convert #RRGGBB to ASS &HAABBGGRR format.
    ASS stores colours as BGR not RGB — caught me out the first time.
    alpha=0 is fully opaque, 255 is fully transparent.
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c*2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


# ── exporters ─────────────────────────────────────────────────────────────────

def cards_to_srt(cards: list, preset: dict) -> str:
    caps  = preset.get("caps", False)
    lines = []

    for i, card in enumerate(cards):
        txt = " ".join(w["word"] for w in card).strip()
        if caps:
            txt = txt.upper()
        start, end = _card_times(cards, i)

        lines.append(str(i + 1))
        lines.append(f"{_fmt_srt_ts(start)} --> {_fmt_srt_ts(end)}")
        lines.append(txt)
        lines.append("")   # blank line between cues

    return "\n".join(lines)


def cards_to_vtt(cards: list, preset: dict) -> str:
    caps  = preset.get("caps", False)
    x_off = preset.get("x_offset", 50)
    y_off = preset.get("y_offset", 85)
    align = preset.get("text_align", "Center").lower()

    lines = ["WEBVTT", ""]

    for i, card in enumerate(cards):
        txt = " ".join(w["word"] for w in card).strip()
        if caps:
            txt = txt.upper()
        start, end = _card_times(cards, i)

        # Premiere doesn't always respect these position cues, but it doesn't hurt to include them
        pos_line = f"line:{y_off}% position:{x_off}% align:{align}"
        lines.append(str(i + 1))
        lines.append(f"{_fmt_vtt_ts(start)} --> {_fmt_vtt_ts(end)} {pos_line}")
        lines.append(txt)
        lines.append("")

    return "\n".join(lines)


def cards_to_ass(cards: list, preset: dict) -> str:
    """
    Export to ASS (Advanced SubStation Alpha) for DaVinci Resolve.

    This is the first format that actually carries the full preset —
    font, size, colour, bold, italic, outline, shadow, position, everything.
    Resolve imports .ass and respects all of it without any extra steps.

    ASS alignment uses numpad positions:
      7 8 9  (top-left, top-center, top-right)
      4 5 6  (mid-left, mid-center, mid-right)
      1 2 3  (bot-left, bot-center, bot-right)
    We map y_offset < 30 = top, > 70 = bottom, else middle.
    """
    font        = preset.get("font", "Arial")
    size        = preset.get("size", 72)
    bold        = -1 if preset.get("bold") else 0      # ASS uses -1 for true
    italic      = -1 if preset.get("italic") else 0
    color       = _hex_to_ass(preset.get("color", "#FFFFFF"))
    outline_c   = _hex_to_ass(preset.get("outline_color", "#000000"))
    shadow_c    = _hex_to_ass(preset.get("shadow_color", "#000000"))
    outline_w   = preset.get("outline_w", 4) if preset.get("outline") else 0
    shadow_w    = 2 if preset.get("shadow") else 0
    caps        = preset.get("caps", False)
    x_off       = preset.get("x_offset", 50)
    y_off       = preset.get("y_offset", 85)

    # map y_offset percentage to ASS alignment
    text_align  = preset.get("text_align", "Center").lower()
    if y_off < 30:
        align = 8 if text_align == "center" else (7 if text_align == "left" else 9)
    elif y_off > 70:
        align = 2 if text_align == "center" else (1 if text_align == "left" else 3)
    else:
        align = 5 if text_align == "center" else (4 if text_align == "left" else 6)

    # margin from edge — convert percentage offset to rough pixel margin
    # 1920px wide assumption, good enough for most exports
    margin_v = int((y_off / 100) * 1080) if y_off > 50 else int(((100 - y_off) / 100) * 1080)
    margin_v = max(10, min(margin_v, 200))   # clamp to sane range

    header = f"""[Script Info]
; Generated by AutoSubtitle — Kormány EditorTarou Róbert Károly
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{color},&H000000FF,{outline_c},{shadow_c},{bold},{italic},0,0,100,100,0,0,1,{outline_w},{shadow_w},{align},10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    lines = [header]
    for card in cards:
        txt = " ".join(w["word"] for w in card).strip()
        if caps:
            txt = txt.upper()
        i   = cards.index(card)
        start, end = _card_times(cards, i)
        lines.append(f"Dialogue: 0,{_fmt_ass_ts(start)},{_fmt_ass_ts(end)},Default,,0,0,0,,{txt}")

    return "\n".join(lines)

