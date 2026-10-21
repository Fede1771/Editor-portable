# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

ROOT_DIR = SPECPATH
DATA_DIR = os.path.join(ROOT_DIR, "data")
MAIN_PY = os.path.join(ROOT_DIR, "main.py")
SPLASH_PNG = os.path.join(DATA_DIR, "splash.png")
ICON_ICO = os.path.join(DATA_DIR, "app_icon.ico")

datas = [(DATA_DIR, "data")]
binaries = []
hiddenimports = []

for pkg in ("fitz", "pymupdf", "pdf2docx", "openpyxl"):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    [MAIN_PY],
    pathex=[ROOT_DIR],
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
splash = Splash(
    SPLASH_PNG,
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    minify_script=True,
    always_on_top=True,
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    [],
    exclude_binaries=True,
    name="EditorPDFPortable",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON_ICO],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    splash.binaries,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="EditorPDFPortable",
)
