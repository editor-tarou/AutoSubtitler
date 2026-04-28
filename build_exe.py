import subprocess, sys, os
from pathlib import Path

PYTHON = sys.executable

# Before building, make sure these are installed:
#   pip install tkinterdnd2
#   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
#
# The CUDA torch MUST be installed before building or the exe will bundle
# the cpu-only version and GPU transcription won't work.


def find_torch_lib_dir() -> str | None:
    """Find the torch/lib directory that contains CUDA .dll files."""
    try:
        import torch
        lib = Path(torch.__file__).parent / "lib"
        if lib.exists():
            return str(lib)
    except Exception:
        pass
    return None


def check_torch_cuda() -> None:
    """Warn loudly if the installed torch doesn't have CUDA support."""
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
            print(f"torch {torch.__version__} — CUDA OK ({torch.cuda.get_device_name(0)})")
            print()
    except ImportError:
        print("WARNING: torch not installed!")


check_torch_cuda()

# Collect torch DLLs explicitly — PyInstaller misses them with --collect-all alone
torch_lib = find_torch_lib_dir()
cuda_binaries = []
if torch_lib:
    for dll in Path(torch_lib).glob("*.dll"):
        cuda_binaries += ["--add-binary", f"{dll};torch/lib"]
    print(f"Found {len(cuda_binaries)//2} torch DLLs to bundle from:\n  {torch_lib}\n")
else:
    print("WARNING: could not find torch/lib — CUDA may not work in the built exe.\n")

args = [
    PYTHON, "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--hide-console", "hide-early",   # kills the flash-console problem on Windows
    "--noupx",                        # CRITICAL: UPX triggers AV false positives
    "--onedir",
    "--name", "AutoSubtitle",
    "--icon", "icon.ico",
    "--collect-all", "whisper",
    "--collect-all", "stable_whisper",
    "--collect-all", "torch",
    "--collect-all", "torchaudio",
    "--collect-all", "tiktoken",
    "--collect-all", "numba",
    "--collect-all", "tkinterdnd2",    # drag-and-drop support
    "--hidden-import", "tkinter",
    "--hidden-import", "tkinter.filedialog",
    "--hidden-import", "tkinter.colorchooser",
    "--hidden-import", "tkinter.messagebox",
    "--hidden-import", "tkinter.font",
    "--hidden-import", "ffmpeg",
    # CUDA extension modules — PyInstaller won't find these automatically
    "--hidden-import", "torch.cuda",
    "--hidden-import", "torch.backends.cuda",
    "--hidden-import", "torch.backends.cudnn",
    "--hidden-import", "torch._C._cuda",
    "autosubtitle_gui.py",
] + cuda_binaries   # append the --add-binary pairs at the end

print("Building AutoSubtitle...")
print("(This will take several minutes — torch+CUDA alone is massive)\n")
result = subprocess.run(args, cwd=os.path.dirname(os.path.abspath(__file__)))

if result.returncode == 0:
    print("\n✓ Build complete!")
    print("  Output: dist\\AutoSubtitle\\")
    print("  Next:   Open AutoSubtitle_Setup.iss in Inno Setup → Ctrl+F9")
else:
    print("\n✗ Build failed. Check output above.")
    sys.exit(1)
