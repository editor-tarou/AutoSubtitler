"""
transcribe.py — everything that touches audio/ML.

Kept in its own file so the GUI imports are completely separate from torch.
Heavy imports (stable_whisper, torch) happen inside run_transcription() so
the app starts fast even on machines that haven't installed them yet.

NOTE: stable-ts does way better word-level alignment than vanilla whisper.
Worth the extra install headache.
"""

import re
import os
import sys

# Suppress the console window that torch/ffmpeg spawns on Windows.
# Without this, a black cmd window flashes every time transcription runs.
if sys.platform == "win32":
    import subprocess
    _orig_popen = subprocess.Popen.__init__
    def _silent_popen(self, *args, **kwargs):
        if sys.platform == "win32" and "creationflags" not in kwargs:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        _orig_popen(self, *args, **kwargs)
    subprocess.Popen.__init__ = _silent_popen


# ── segmentation styles ───────────────────────────────────────────────────────
# Balanced is basically the only mode that looks right on most content.
# Punchy works for hype reels. Full is kinda useless unless it's a slow podcast.
# Shorts is the TikTok/Reels style — one impactful word at a time, fillers glued on.

SEG_STYLES: dict[str, dict] = {
    "Shorts  - 1 word":       {"max_words": 1,  "pause_gap": 0.10, "shorts": True},
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


# ── filler words (glued to the next card in Shorts mode) ─────────────────────
# These are words that look weird alone on screen — attach them to whatever
# comes next so you don't get a card that just says "and" or "the".
# List is intentionally short — only the most common offenders.

_FILLERS = {
    "a", "an", "the", "and", "or", "but", "so", "yet", "for", "nor",
    "to", "of", "in", "on", "at", "by", "is", "it", "i", "he", "she",
    "we", "my", "his", "her", "our", "you", "your", "its",
}


# ── word segmentation ─────────────────────────────────────────────────────────

def segment_shorts(words: list[dict]) -> list[list[dict]]:
    """
    Shorts-style segmentation: one word per card, but filler words get
    glued onto the next card so you never show just "and" or "the" alone.

    This is the TikTok/Reels look — fast, punchy, one word flashing at a time.
    Works best with medium or large model for clean word boundaries.
    """
    if not words:
        return []

    cards: list[list[dict]] = []
    i = 0
    while i < len(words):
        word = words[i]["word"].strip().lower().rstrip(".,!?;:")

        # If this word is a filler AND there's a next word, group them together
        if word in _FILLERS and i + 1 < len(words):
            cards.append([words[i], words[i + 1]])
            i += 2
        else:
            cards.append([words[i]])
            i += 1

    return cards


def segment_words(words: list[dict], cfg: dict) -> list[list[dict]]:
    """
    Group word-level timestamps into subtitle cards.

    Each element of `words` must have keys: word, start, end.
    `cfg` must have: max_words (int), pause_gap (float, seconds).
    If cfg has shorts=True, delegates to segment_shorts instead.
    """
    if cfg.get("shorts"):
        return segment_shorts(words)

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
    on_log,        # callable(str, tag: str | None)
    on_done,       # callable()
    preset: dict,
    nle: str,      # "Premiere" or "Resolve"
    fmt: str = "SRT",   # Premiere: "SRT" or "VTT" | Resolve: "SRT" (Lite) or "ASS" (Pro)
    on_progress=None,         # callable(float 0–1, str label) | None
    on_transcribe_start=None, # callable() | None  — fired just before model.transcribe()
) -> None:
    """
    Transcribe *path* using stable-whisper and write the chosen subtitle format.

    Designed to be called from a daemon thread — all log output goes through
    `on_log(text, tag)` so the GUI can display it without blocking.
    `on_done()` is called when finished (even on error).
    """
    def _prog(frac: float, label: str) -> None:
        if on_progress:
            on_progress(frac, label)

    _prog(0.0, "Starting…")

    # When running as a PyInstaller bundle, torch/lib is unpacked next to the
    # exe. We add it to PATH so CUDA DLLs (cublas, cudnn etc.) are found.
    if getattr(sys, "frozen", False):
        bundle_dir = os.path.dirname(sys.executable)
        torch_lib  = os.path.join(bundle_dir, "torch", "lib")
        if os.path.isdir(torch_lib):
            os.environ["PATH"] = torch_lib + os.pathsep + os.environ.get("PATH", "")
            on_log(f"Bundle torch/lib found: {torch_lib}\n", "muted")
        else:
            on_log(f"Bundle torch/lib NOT found at: {torch_lib}\n", "error")

    import torch

    on_log(f"Torch version: {torch.__version__}\n", "muted")
    on_log(f"CUDA available: {torch.cuda.is_available()}\n", "muted")
    if not torch.cuda.is_available():
        on_log(f"CUDA reason: {torch.cuda.is_available.__doc__}\n", "muted")
        try:
            torch.cuda.init()
        except Exception as cuda_err:
            on_log(f"CUDA init error: {cuda_err}\n", "error")

    import stable_whisper

    from .subtitle_export import cards_to_srt, cards_to_vtt, cards_to_ass

    # Premiere → SRT or VTT depending on user choice
    # Resolve  → SRT (basic, no styling) or ASS (full preset: font, colour, outline, position)
    if nle == "Resolve" and fmt == "ASS":
        ext = ".ass"
    elif fmt == "VTT":
        ext = ".vtt"
    else:
        ext = ".srt"

    # Save next to the source file. If that directory isn't writable (e.g. a
    # network drive or a protected folder) fall back to the user's Desktop.
    base_name = os.path.splitext(os.path.basename(path))[0] + "_captions" + ext
    out_dir   = os.path.dirname(path)
    out_path  = os.path.join(out_dir, base_name)
    if not os.access(out_dir, os.W_OK):
        desktop  = os.path.join(os.path.expanduser("~"), "Desktop")
        out_path = os.path.join(desktop, base_name)
        on_log(f"Note: can't write to source folder, saving to Desktop instead.\n", "accent")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    on_log(f"Device: {device}", "muted")
    if device == "cuda":
        on_log(f" ({torch.cuda.get_device_name(0)})\n", "muted")
    else:
        on_log("\n", "muted")
        if model_id in ("medium", "large"):
            on_log(f"Warning: '{model_id}' on CPU is slow and may need more RAM.\n", "accent")

    try:
        on_log(f"Loading Whisper '{model_id}'...\n", "muted")
        _prog(0.10, f"Loading {model_id} model…")
        # NOTE: large model on CPU takes like 3x realtime, warn user?
        # had a crash once with large+cuda on my 3050 with a 20min clip — not reproducible
        model = stable_whisper.load_model(model_id, device=device)

        on_log("Transcribing with precise timing...\n", "muted")
        _prog(0.25, "Transcribing audio…")
        if on_transcribe_start:
            on_transcribe_start()
        opts: dict = {"word_timestamps": True, "regroup": False}
        if language != "auto":
            opts["language"] = language
        if device == "cuda":
            opts["fp16"] = True

        # In a --windowed PyInstaller build stdout is None.
        # tqdm (used internally by stable_whisper) tries to write to it and
        # crashes with 'NoneType has no attribute write'. Redirect to devnull.
        import io
        _null = open(os.devnull, "w")
        _old_stdout, _old_stderr = sys.stdout, sys.stderr
        if sys.stdout is None:
            sys.stdout = _null
        if sys.stderr is None:
            sys.stderr = _null

        try:
            result = model.transcribe(path, **opts)
        except Exception as transcribe_err:
            import traceback
            on_log(f"\nTranscribe failed internally:\n{transcribe_err}\n", "error")
            on_log(traceback.format_exc(), "muted")
            on_done()
            return
        finally:
            sys.stdout = _old_stdout
            sys.stderr = _old_stderr
            _null.close()

        if result is None:
            on_log("\nError: transcribe() returned nothing.\n", "error")
            on_log("This usually means the model ran out of RAM.\n", "accent")
            on_log("Try switching to 'base' or 'small' model.\n", "accent")
            on_done()
            return

        detected = result.language if hasattr(result, "language") else "unknown"
        on_log(f"Language: {detected}\n", "muted")
        _prog(0.80, "Segmenting words…")

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
        _prog(0.92, "Writing subtitle file…")

        if nle == "Resolve" and fmt == "ASS":
            content = cards_to_ass(cards, preset)
        elif fmt == "VTT":
            content = cards_to_vtt(cards, preset)
        else:
            content = cards_to_srt(cards, preset)

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(content)
        except PermissionError:
            on_log(f"\nError: no permission to write to:\n  {out_path}\n", "error")
            on_log("Try moving your file to your Desktop or Documents folder.\n", "accent")
            on_done()
            return

        on_log(f"\n✓ Done!  {len(cards)} caption cards\n", "success")
        on_log(f"  Saved: {out_path}\n", "accent")
        _prog(1.0, "Done!")

        if nle == "Resolve" and fmt == "ASS":
            on_log(
                "\nIn Resolve: File > Import > Subtitles, select the .ass file.\n"
                "Font, colour, outline and position from your preset\n"
                "are all embedded — should look right immediately.\n",
                "muted",
            )
        elif nle == "Resolve":
            on_log(
                "\nIn Resolve: File > Import > Subtitles, select the .srt file.\n"
                "Note: SRT carries no styling — use the Inspector panel in Resolve\n"
                "to adjust font and colour after import.\n"
                "Upgrade to Pro for .ass export with full preset styling.\n",
                "muted",
            )
        elif fmt == "VTT":
            on_log(
                "\nIn Premiere: File > Import, then drag the .vtt\n"
                "onto a caption track. Position cues are embedded.\n",
                "muted",
            )
        else:
            on_log(
                "\nIn Premiere: File > Import, then drag the .srt\n"
                "onto a caption track. Right-click the track >\n"
                "Convert to Graphics to apply a .mogrt style.\n",
                "muted",
            )

    except Exception as exc:
        on_log(f"\nError: {exc}\n", "error")

    on_done()
