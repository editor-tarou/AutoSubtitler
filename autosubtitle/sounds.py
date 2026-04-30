"""
sounds.py — Synthesized UI sounds for AutoSubtitle.

All sounds are generated at runtime with numpy — no audio files to bundle.
Playback is non-blocking (daemon thread) so it never stalls the UI.

Usage:
    from .sounds import play_complete, play_error, play_activate, play_startup, play_click, prewarm
"""

from __future__ import annotations

import io
import threading
import wave

import numpy as np

SAMPLE_RATE = 44100


def _sine(freq, duration, amp=1.0):
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    return amp * np.sin(2 * np.pi * freq * t)


def _envelope(signal, attack, decay, sustain, release, sustain_level=0.7):
    n  = len(signal)
    sr = SAMPLE_RATE
    a  = int(attack  * sr)
    d  = int(decay   * sr)
    r  = int(release * sr)
    s  = max(0, n - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1,             a),
        np.linspace(1, sustain_level, d),
        np.full(s, sustain_level),
        np.linspace(sustain_level, 0, r),
    ])
    env = env[:n]
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)))
    return signal * env


def _normalize(signal, peak=0.85):
    m = np.max(np.abs(signal))
    if m > 0:
        signal = signal / m * peak
    return signal


def _to_wav_bytes(signal):
    pcm     = np.clip(signal, -1.0, 1.0)
    pcm_int = (pcm * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_int.tobytes())
    return buf.getvalue()


def _play_async(wav_bytes):
    def _run():
        try:
            import winsound, tempfile, os, time
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_bytes)
                tmp = f.name
            winsound.PlaySound(tmp, winsound.SND_FILENAME | winsound.SND_ASYNC)
            time.sleep(3)
            try:
                os.unlink(tmp)
            except OSError:
                pass
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


# ── Sound builders ───────────────────────────────────────────────────────────

def _build_complete():
    note1  = _sine(523.25, 0.18, 0.6) + _sine(1046.5, 0.18, 0.15)
    note1  = _envelope(note1, 0.008, 0.04, 0.5, 0.12)
    note2  = _sine(659.25, 0.45, 0.55) + _sine(783.99, 0.45, 0.35) + _sine(1318.5, 0.45, 0.10)
    note2  = _envelope(note2, 0.006, 0.05, 0.55, 0.3)
    gap    = int(0.14 * SAMPLE_RATE)
    out    = np.zeros(gap + len(note2))
    out[:len(note1)]          += note1
    out[gap:gap + len(note2)] += note2
    return _to_wav_bytes(_normalize(out))


def _build_error():
    note1  = _sine(392.0, 0.22, 0.7) + _sine(784.0, 0.22, 0.12)
    note1  = _envelope(note1, 0.01, 0.06, 0.45, 0.14)
    note2  = _sine(311.13, 0.30, 0.6) + _sine(622.25, 0.30, 0.10)
    note2  = _envelope(note2, 0.008, 0.05, 0.35, 0.2)
    gap    = int(0.16 * SAMPLE_RATE)
    out    = np.zeros(gap + len(note2))
    out[:len(note1)]          += note1
    out[gap:gap + len(note2)] += note2
    return _to_wav_bytes(_normalize(out))


def _build_activate():
    freqs   = [523.25, 659.25, 783.99, 1046.5]
    offsets = [0.0,    0.11,   0.22,   0.34]
    total   = int((offsets[-1] + 0.70) * SAMPLE_RATE)
    out     = np.zeros(total)
    for i, (freq, offset) in enumerate(zip(freqs, offsets)):
        note = _sine(freq, 0.20 + 0.50 - offset * 0.5, 0.6 - i * 0.05)
        note = _envelope(note, 0.006, 0.04, 0.6 - i * 0.08, 0.3)
        s    = int(offset * SAMPLE_RATE)
        out[s:s + len(note)] += note
    shimmer = _envelope(_sine(2093.0, 0.18, 0.08), 0.005, 0.03, 0.4, 0.12)
    s = int(offsets[-1] * SAMPLE_RATE)
    out[s:s + len(shimmer)] += shimmer
    return _to_wav_bytes(_normalize(out))


def _build_click():
    tone = _sine(880.0, 0.04, 0.4) + _sine(1320.0, 0.04, 0.15)
    tone = _envelope(tone, 0.002, 0.015, 0.2, 0.02)
    return _to_wav_bytes(_normalize(tone, peak=0.5))


def _build_startup():
    sr    = SAMPLE_RATE
    total = int(1.25 * sr)
    out   = np.zeros(total)

    # 1. Bwoop: F3→A3 pitch bend
    n   = int(0.22 * sr)
    t   = np.linspace(0, 0.22, n, endpoint=False)
    fsw = 174.6 * np.exp(t / 0.22 * np.log(220.0 / 174.6))
    ph  = np.cumsum(2 * np.pi * fsw / sr)
    bw  = 0.55 * np.sin(ph) + 0.12 * np.sin(2 * ph)
    env = np.concatenate([
        np.linspace(0, 1,   int(0.012 * sr)),
        np.linspace(1, 0.6, int(0.080 * sr)),
        np.linspace(0.6, 0, n - int(0.012 * sr) - int(0.080 * sr)),
    ])
    bw *= env[:n]
    out[:n] += bw

    # 2. Two blips: C5, Eb5
    for offset, freq in [(0.26, 523.25), (0.38, 622.25)]:
        nb  = int(0.09 * sr)
        tb  = np.linspace(0, 0.09, nb)
        blp = 0.45 * np.sin(2 * np.pi * freq * tb) + 0.10 * np.sin(4 * np.pi * freq * tb)
        eb  = np.concatenate([np.linspace(0, 1, int(0.006 * sr)),
                               np.linspace(1, 0, nb - int(0.006 * sr))])
        blp *= eb[:nb]
        s = int(offset * sr)
        out[s:s + nb] += blp

    # 3. Fmaj chord bloom
    cs = int(0.50 * sr)
    for freq, amp in [(349.23, 0.40), (440.00, 0.30), (523.25, 0.22)]:
        nc  = int(0.72 * sr)
        tc  = np.linspace(0, 0.72, nc)
        tn  = amp * np.sin(2 * np.pi * freq * tc) + amp * 0.18 * np.sin(4 * np.pi * freq * tc)
        ec  = np.concatenate([
            np.linspace(0, 1,   int(0.06 * sr)),
            np.linspace(1, 0.8, int(0.10 * sr)),
            np.linspace(0.8, 0, nc - int(0.06 * sr) - int(0.10 * sr)),
        ])
        tn *= ec[:nc]
        end = min(cs + nc, total)
        out[cs:end] += tn[:end - cs]

    return _to_wav_bytes(_normalize(out, peak=0.82))


# ── Cache ────────────────────────────────────────────────────────────────────

_cache: dict = {}

_BUILDERS = {
    "complete": _build_complete,
    "error":    _build_error,
    "activate": _build_activate,
    "click":    _build_click,
    "startup":  _build_startup,
}


def _get(name):
    if name not in _cache:
        _cache[name] = _BUILDERS[name]()
    return _cache[name]


# ── Public API ───────────────────────────────────────────────────────────────

def play_startup():  _play_async(_get("startup"))
def play_complete(): _play_async(_get("complete"))
def play_error():    _play_async(_get("error"))
def play_activate(): _play_async(_get("activate"))
def play_click():    _play_async(_get("click"))


def prewarm():
    def _build_all():
        for name in _BUILDERS:
            _get(name)
    threading.Thread(target=_build_all, daemon=True).start()
