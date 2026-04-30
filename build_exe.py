"""
build_exe.py — builds AutoSubtitle via PyInstaller.

Edition is now determined at runtime by the user's license key,
so there is only one build. Both the Lite and Pro installers package
the same executable.

Usage:
    python build_exe.py

Before building:
    pip install tkinterdnd2
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

The CUDA torch must be installed before building or the exe will bundle
the CPU-only version and GPU transcription will not work.
"""

import subprocess, sys, os
from pathlib import Path

PYTHON   = sys.executable
APP_NAME = "AutoSubtitle"


# ── helpers ───────────────────────────────────────────────────────────────────

def find_torch_lib_dir():
    try:
        import torch
        lib = Path(torch.__file__).parent / "lib"
        if lib.exists():
            return str(lib)
    except Exception:
        pass
    return None


def check_torch_cuda():
    try:
        import torch
        if not torch.cuda.is_available():
            print("=" * 60)
            print("WARNING: installed torch has NO CUDA support!")
            print(f"  torch version: {torch.__version__}")
            print("  The built exe will run on CPU only.")
            print("  To fix, run BEFORE building:")
            print("    pip uninstall torch torchaudio -y")
            print("    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121")
            print("=" * 60)
            print()
        else:
            print(f"torch {torch.__version__} - CUDA OK ({torch.cuda.get_device_name(0)})")
            print()
    except ImportError:
        print("WARNING: torch not installed!")


# ── build ─────────────────────────────────────────────────────────────────────

check_torch_cuda()

torch_lib     = find_torch_lib_dir()
cuda_binaries = []
if torch_lib:
    for dll in Path(torch_lib).glob("*.dll"):
        cuda_binaries += ["--add-binary", f"{dll};torch/lib"]
    print(f"Found {len(cuda_binaries)//2} torch DLLs from:\n  {torch_lib}\n")
else:
    print("WARNING: could not find torch/lib - CUDA may not work in the built exe.\n")

args = [
    PYTHON, "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--hide-console", "hide-early",
    "--noupx",
    "--onedir",
    "--name", APP_NAME,
    "--icon", "icon.ico",
    "--collect-all", "whisper",
    "--collect-all", "stable_whisper",
    "--collect-all", "torch",
    "--collect-all", "torchaudio",
    "--collect-all", "tiktoken",
    "--collect-all", "numba",
    "--collect-all", "tkinterdnd2",
    "--hidden-import", "tkinter",
    "--hidden-import", "tkinter.filedialog",
    "--hidden-import", "tkinter.colorchooser",
    "--hidden-import", "tkinter.messagebox",
    "--hidden-import", "tkinter.font",
    "--hidden-import", "ffmpeg",
    "--hidden-import", "torch.cuda",
    "--hidden-import", "torch.backends.cuda",
    "--hidden-import", "torch.backends.cudnn",
    "--hidden-import", "torch._C._cuda",
    "autosubtitle_gui.py",
] + cuda_binaries

print(f"Building {APP_NAME}...")
print("(This takes several minutes — torch+CUDA is large)\n")

result = subprocess.run(args, cwd=os.path.dirname(os.path.abspath(__file__)))

if result.returncode == 0:
    print(f"\n Build complete!")
    print(f"  Output: dist\\{APP_NAME}\\")
    print(f"  Next:   Open AutoSubtitle_Setup.iss in Inno Setup -> Ctrl+F9")
    print(f"  Note:   One exe ships for both Lite and Pro.")
    print(f"          Pro features unlock when a valid license key is entered.")
else:
    print("\n Build failed. Check output above.")
    sys.exit(1)
