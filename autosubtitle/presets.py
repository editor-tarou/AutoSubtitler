"""
presets.py — preset data model, defaults, and load/save helpers.

A preset is just a plain dict. PRESET_DEFAULTS defines every key a preset
must have (and their fallback values), so older saved presets that are missing
a newer field will still work after an upgrade.

Added letter_spacing and line_height late — not all Premiere versions respect
them via SRT anyway, but useful for the preview at minimum.
"""

import json

from .paths import PRESETS_FILE


# ── every field a preset can have, with its default value ────────────────────
# x_offset/y_offset are percentages — 0,0 is top-left, 100,100 is bottom-right
# y_offset=85 is where Premiere puts subs by default, so that's the fallback

PRESET_DEFAULTS = {
    "caps":           False,
    "letter_spacing": 0,
    "line_height":    100,
    "x_offset":       50,
    "y_offset":       85,
    "text_align":     "Center",
    "max_width":      80,
    "safe_zone":      True,
    "show_safe_zone": False,
}

# ── built-in (non-editable) presets ──────────────────────────────────────────

DEFAULT_PRESETS = [
    {
        **PRESET_DEFAULTS,
        "name": "Clean White", "font": "Arial", "size": 72,
        "bold": False, "italic": False,
        "color": "#FFFFFF", "outline": True, "outline_color": "#000000", "outline_w": 4,
        "shadow": False, "shadow_color": "#000000", "position": "bottom", "builtin": True,
    },
    {
        **PRESET_DEFAULTS,
        "name": "Bold Impact", "font": "Impact", "size": 88,
        "bold": True, "italic": False,
        "color": "#FFFF00", "outline": True, "outline_color": "#000000", "outline_w": 6,
        "shadow": False, "shadow_color": "#000000", "position": "bottom", "builtin": True,
    },
    {
        **PRESET_DEFAULTS,
        "name": "Cinematic", "font": "Georgia", "size": 64,
        "bold": False, "italic": True,
        "color": "#FFFFFF", "outline": False, "outline_color": "#000000", "outline_w": 3,
        "shadow": True, "shadow_color": "#000000", "position": "bottom", "builtin": True,
    },
    {
        **PRESET_DEFAULTS,
        "name": "Minimal Top", "font": "Helvetica Neue", "size": 60,
        "bold": False, "italic": False,
        "color": "#FFFFFF", "outline": True, "outline_color": "#333333", "outline_w": 2,
        "shadow": False, "shadow_color": "#000000", "position": "top", "builtin": True,
        "y_offset": 10,
    },
]


# ── persistence ───────────────────────────────────────────────────────────────

def load_presets() -> list[dict]:
    """Load presets from disk, falling back to built-in defaults."""
    if PRESETS_FILE.exists():
        try:
            presets = json.loads(PRESETS_FILE.read_text())
            # Backfill any keys added after the user's file was saved.
            # This is why PRESET_DEFAULTS exists — cheaper than a migration system.
            for p in presets:
                for k, v in PRESET_DEFAULTS.items():
                    p.setdefault(k, v)
            return presets
        except Exception:
            pass   # corrupted file — fall through to defaults

    return [dict(p) for p in DEFAULT_PRESETS]


def save_presets(presets: list[dict]) -> None:
    PRESETS_FILE.write_text(json.dumps(presets, indent=2))
