"""
transcribe.py — everything that touches audio/ML.

Kept in its own file so the GUI imports are completely separate from torch.
Heavy imports (stable_whisper, torch) happen inside run_transcription() so
the app starts fast even on machines that haven't installed them yet.

NOTE: stable-ts does way better word-level alignment than vanilla whisper.
Worth the extra install headache.
"""

import re


# ── segmentation styles ───────────────────────────────────────────────────────
# Balanced is basically the only mode that looks right on most content.
# Punchy works for hype reels. Full is kinda useless unless it's a slow podcast.

SEG_STYLES: dict[str, dict] = {
    "Punchy  - 1-3 words":    {"max_words": 3,  "pause_gap": 0.15},
    "Balanced - 3-5 words":   {"max_words": 5,  "pause_gap": 0.30},   # default, use this
    "Full - natural phrases": {"max_words": 10, "pause_gap": 0.50},
}

# large model will OOM on my RTX 3050 with longer clips — user beware
# tiny is only useful for testing, results are embarrassing for real use
MODELS = ["tiny", "base", "small", "medium", "large"]

LANGUAGES = ["auto", "en", "hu", "de", "fr", "es", "it", "pt", "pl", "ru", "zh", "ja", "ko"]


# ── dependency check ──────────────────────────────────────────────────────────

def check_dependencies() -> list[str]:
    """Return the names of any pip packages that are not yet installed."""
    missing = []
    for pkg, imp in [
        ("openai-whisper", "whisper"),
        ("torch",          "torch"),
        ("stable-ts",      "stable_whisper"),
    ]:
        try:
            __import__(imp)
        except ImportError:
            missing.append(pkg)
    return missing


# ── word segmentation ─────────────────────────────────────────────────────────

def segment_words(words: list[dict], cfg: dict) -> list[list[dict]]:
    """
    Group word-level timestamps into subtitle cards.

    Each element of `words` must have keys: word, start, end.
    `cfg` must have: max_words (int), pause_gap (float, seconds).
    """
    max_words = cfg["max_words"]
    pause_gap = cfg["pause_gap"]

    phrases: list[list[dict]] = []
    current: list[dict] = []

    for w in words:
        word = w["word"].strip()
        if not word:
            continue

        # Split on a long pause
        if current and w["start"] - current[-1]["end"] >= pause_gap:
            phrases.append(current)
            current = []

        current.append({"word": word, "start": w["start"], "end": w["end"]})

        # Split on sentence-ending punctuation
        # TODO: em-dashes? stable-ts sometimes emits those mid-word
        if re.search(r"[.,!?;:]$", word):
            phrases.append(current)
            current = []

    if current:
        phrases.append(current)

    # Enforce max_words per card
    # old approach was splitting on syllable weight — too slow, dropped it
    # if pause_gap > 0.4 and len(phrase) <= 2: skip_split = True
    cards: list[list[dict]] = []
    for phrase in phrases:
        while len(phrase) > max_words:
            cards.append(phrase[:max_words])
            phrase = phrase[max_words:]
        if phrase:
            cards.append(phrase)

    return cards


# ── main transcription entry point ────────────────────────────────────────────

def run_transcription(
    path: str,
    model_id: str,
    language: str,
    seg_cfg: dict,
    on_log,       # callable(str, tag: str | None)
    on_done,      # callable()
    preset: dict,
    fmt: str,
) -> None:
    """
    Transcribe *path* using stable-whisper and write an SRT or VTT file.

    Designed to be called from a daemon thread — all log output goes through
    `on_log(text, tag)` so the GUI can display it without blocking.
    `on_done()` is called when finished (even on error).
    """
    # These imports are intentionally late — they are slow and we don't want
    # them running at startup before the splash screen is shown.
    import torch
    import stable_whisper

    from .subtitle_export import cards_to_srt, cards_to_vtt
    import os

    ext      = ".srt" if fmt == "SRT" else ".vtt"
    out_path = os.path.splitext(path)[0] + "_captions" + ext
    device   = "cuda" if torch.cuda.is_available() else "cpu"

    try:
        on_log(f"Loading Whisper '{model_id}' on {device}...\n", "muted")
        # NOTE: large model on CPU takes like 3x realtime, warn user?
        # had a crash once with large+cuda on my 3050 with a 20min clip — not reproducible
        model = stable_whisper.load_model(model_id, device=device)

        on_log("Transcribing with precise timing...\n", "muted")
        opts: dict = {"word_timestamps": True, "regroup": False}
        if language != "auto":
            opts["language"] = language
        result = model.transcribe(path, **opts)

        detected = result.language if hasattr(result, "language") else "unknown"
        on_log(f"Language: {detected}\n", "muted")

        all_words = []
        for seg in result.segments:
            for w in seg.words:
                word = w.word.strip()
                if word:
                    all_words.append({"word": word, "start": w.start, "end": w.end})

        if not all_words:
            on_log("No speech detected.\n", "error")
            on_done()
            return

        on_log(f"Words found: {len(all_words)}\n", "muted")
        cards = segment_words(all_words, seg_cfg)
        on_log(f"Cards: {len(cards)}\n", "muted")

        if fmt == "SRT":
            content = cards_to_srt(cards, preset)
        else:
            content = cards_to_vtt(cards, preset)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

        on_log(f"\n✓ Done!  {len(cards)} caption cards\n", "success")
        on_log(f"  Saved: {out_path}\n", "accent")

        # SRT is more reliable for Premiere — VTT position cues are supposed to work
        # but Premiere interprets them inconsistently depending on version
        if fmt == "SRT":
            on_log(
                "\nIn Premiere: File > Import, then drag the .srt\n"
                "onto a caption track. Right-click the track >\n"
                "Convert to Graphics to apply a .mogrt style.\n",
                "muted",
            )
        else:
            on_log(
                "\nIn Premiere: File > Import, then drag the .vtt\n"
                "onto a caption track. Position cues are embedded.\n"
                "Right-click the track > Convert to Graphics\n"
                "to apply a .mogrt style.\n",
                "muted",
            )

    except Exception as exc:
        on_log(f"\nError: {exc}\n", "error")

    on_done()
