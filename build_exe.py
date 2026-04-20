"""
build_exe.py  —  Builds AutoSubtitle using PyInstaller (onedir mode)
====================================================================

WHY onedir and NOT onefile:
- onefile extracts itself to %TEMP% at every launch — that's a classic
  malware pattern and Defender flags it constantly.
- onedir produces a plain folder of real DLL files. Nothing unpacks
  at runtime, nothing touches %TEMP%, no AV issues.

HOW TO RUN (one time only):
    pip install pyinstaller
    python build_exe.py

Output: dist\AutoSubtitle\
Then open AutoSubtitle_Setup.iss in Inno Setup and press Ctrl+F9.
"""

import subprocess, sys, os

PYTHON = sys.executable

args = [
    PYTHON, "-m", "PyInstaller",
    "--noconfirm",                   # overwrite without asking
    "--clean",                       # fresh build every time
    "--windowed",                    # no console window
    "--noupx",                       # CRITICAL: UPX triggers AV false positives
    "--onedir",                      # folder output, not single exe (AV-safe)
    "--name", "AutoSubtitle",
    "--icon", "icon.ico",
    # Collect the heavy ML packages properly so they bundle without errors
    "--collect-all", "whisper",
    "--collect-all", "stable_whisper",
    "--collect-all", "torch",
    "--collect-all", "torchaudio",
    "--collect-all", "tiktoken",
    "--collect-all", "numba",
    # Hidden imports that PyInstaller misses
    "--hidden-import", "tkinter",
    "--hidden-import", "tkinter.filedialog",
    "--hidden-import", "tkinter.colorchooser",
    "--hidden-import", "tkinter.messagebox",
    "--hidden-import", "tkinter.font",
    "autosubtitle_gui.py",
]

print("Building AutoSubtitle...")
print("(This will take several minutes — torch alone is large)\n")
result = subprocess.run(args, cwd=os.path.dirname(os.path.abspath(__file__)))

if result.returncode == 0:
    print("\n✓ Build complete!")
    print("  Output: dist\\AutoSubtitle\\")
    print("  Next:   Open AutoSubtitle_Setup.iss in Inno Setup → Ctrl+F9")
else:
    print("\n✗ Build failed. Check output above.")
    sys.exit(1)
