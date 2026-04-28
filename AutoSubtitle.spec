# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = [('C:\\Users\\chaot\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\torch\\lib\\c10.dll', 'torch/lib'), ('C:\\Users\\chaot\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\torch\\lib\\libiomp5md.dll', 'torch/lib'), ('C:\\Users\\chaot\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\torch\\lib\\libiompstubs5md.dll', 'torch/lib'), ('C:\\Users\\chaot\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\torch\\lib\\shm.dll', 'torch/lib'), ('C:\\Users\\chaot\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\torch\\lib\\torch.dll', 'torch/lib'), ('C:\\Users\\chaot\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\torch\\lib\\torch_cpu.dll', 'torch/lib'), ('C:\\Users\\chaot\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\torch\\lib\\torch_global_deps.dll', 'torch/lib'), ('C:\\Users\\chaot\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\torch\\lib\\torch_python.dll', 'torch/lib'), ('C:\\Users\\chaot\\AppData\\Local\\Programs\\Python\\Python313\\Lib\\site-packages\\torch\\lib\\uv.dll', 'torch/lib')]
hiddenimports = ['tkinter', 'tkinter.filedialog', 'tkinter.colorchooser', 'tkinter.messagebox', 'tkinter.font', 'ffmpeg', 'torch.cuda', 'torch.backends.cuda', 'torch.backends.cudnn', 'torch._C._cuda']
tmp_ret = collect_all('whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('stable_whisper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('torch')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('torchaudio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tiktoken')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('numba')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['autosubtitle_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AutoSubtitle',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
    hide_console='hide-early',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AutoSubtitle',
)
