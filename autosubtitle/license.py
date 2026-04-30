import hmac
import hashlib
import base64
import re
from pathlib import Path

from .paths import APP_DIR


# ── secret ────────────────────────────────────────────────────────────────────
# Split across two halves so a naive strings search won't grab it in one shot.
# Change both halves before distributing — the keygen must use the same values.

_S1 = bytes([0x41, 0x53, 0x75, 0x62, 0x2D, 0x4B, 0x65, 0x79, 0x2D, 0x53])
_S2 = bytes([0x61, 0x6C, 0x74, 0x2D, 0x76, 0x31, 0x2E, 0x31, 0x2E, 0x31])
_SECRET: bytes = _S1 + _S2


# ── paths ─────────────────────────────────────────────────────────────────────

LICENSE_FILE: Path = APP_DIR / "license.key"


# ── key format ────────────────────────────────────────────────────────────────
# 10 bytes total: 5-byte random payload + 5-byte HMAC prefix
# → 16 base32 chars (80 bits, no padding needed) → XXXX-XXXX-XXXX-XXXX

_KEY_RE = re.compile(r"^[A-Z2-7]{4}-[A-Z2-7]{4}-[A-Z2-7]{4}-[A-Z2-7]{4}$")


def _normalise(key: str) -> str:
    """Upper-case, strip dashes/spaces, re-insert dashes in the right places."""
    raw = key.upper().replace("-", "").replace(" ", "")
    if len(raw) != 16:
        return ""
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def validate_key(key: str) -> bool:
    """
    Return True if *key* is a genuine AutoSubtitle Pro license key.

    Validation steps:
      1. Normalise formatting.
      2. Base32-decode to 10 raw bytes.
      3. Split into payload (first 5) + check (last 5).
      4. Recompute HMAC-SHA256(SECRET, payload)[:5] and compare in
         constant time to prevent timing attacks.
    """
    normed = _normalise(key)
    if not _KEY_RE.match(normed):
        return False

    raw_b32 = normed.replace("-", "")
    # base32 alphabet is A-Z + 2-7.  16 chars → 10 bytes exactly (80 bits).
    try:
        raw = base64.b32decode(raw_b32)
    except Exception:
        return False

    if len(raw) != 10:
        return False

    payload, check = raw[:5], raw[5:]
    expected = hmac.new(_SECRET, payload, hashlib.sha256).digest()[:5]
    return hmac.compare_digest(expected, check)


# ── persistence ───────────────────────────────────────────────────────────────

def load_saved_key() -> str | None:
    """Return the saved license key, or None if no key is saved."""
    try:
        key = LICENSE_FILE.read_text(encoding="utf-8").strip()
        return key if key else None
    except FileNotFoundError:
        return None
    except Exception:
        return None


def save_key(key: str) -> bool:
    """Write the key to disk.  Returns True on success."""
    try:
        LICENSE_FILE.write_text(_normalise(key), encoding="utf-8")
        return True
    except Exception:
        return False


def remove_key() -> None:
    """Delete the saved license key (deactivate)."""
    try:
        LICENSE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ── runtime edition ───────────────────────────────────────────────────────────

def is_pro() -> bool:
    """
    True if a valid Pro license key is saved on this machine.
    Cached after first call so repeated checks are free.
    """
    if _cache[0] is None:
        key = load_saved_key()
        _cache[0] = bool(key and validate_key(key))
    return _cache[0]


_cache: list[bool | None] = [None]   # [result] — simple mutable singleton


def refresh() -> bool:
    """Re-check the license (call after saving or removing a key)."""
    _cache[0] = None
    return is_pro()
