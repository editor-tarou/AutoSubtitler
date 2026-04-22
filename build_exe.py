import subprocess, sys, os

PYTHON = sys.executable

args = [
    PYTHON, "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--noupx",                       # CRITICAL: UPX triggers AV false positives
    "--onedir",
    "--name", "AutoSubtitle",
    "--icon", "icon.ico",
    "--collect-all", "whisper",
    "--collect-all", "stable_whisper",
    "--collect-all", "torch",
    "--collect-all", "torchaudio",
    "--collect-all", "tiktoken",
    "--collect-all", "numba",
    "--hidden-import", "tkinter",
    "--hidden-import", "tkinter.filedialog",
    "--hidden-import", "tkinter.colorchooser",
    "--hidden-import", "tkinter.messagebox",
    "--hidden-import", "tkinter.font",
    "autosubtitle_gui.py",           # entry point — imports autosubtitle package
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
