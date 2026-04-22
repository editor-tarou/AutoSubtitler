"""
subtitle_export.py — converts segmented caption cards to SRT or WebVTT text.

No GUI or ML imports here on purpose — this can be used or tested standalone.

SRT is simpler and Premiere handles it more reliably. VTT is theoretically
better because it embeds position, but Premiere's VTT parser is quirky — test
before using position cues in production.
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
