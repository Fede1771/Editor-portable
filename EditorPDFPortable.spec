# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

project_root = os.path.abspath(SPECPATH)
data_dir = os.path.join(project_root, "data")

datas = []
for rel_file, dest_dir in (
    ("app_icon.ico", "data"),
    ("app_icon.png", "data"),
    ("splash.png", "data"),
):
    src_p = os.path.join(data_dir, rel_file)
    if os.path.isfile(src_p):
        datas.append((src_p, dest_dir))

tessdata_dir = os.path.join(data_dir, "tessdata")
if os.path.isdir(tessdata_dir):
    for fname in os.listdir(tessdata_dir):
        if fname.endswith(".traineddata"):
            datas.append((os.path.join(tessdata_dir, fname), os.path.join("data", "tessdata")))

binaries = []
hiddenimports = []
for pkg in ("fitz", "pymupdf", "pdf2docx", "openpyxl"):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    [os.path.join(project_root, "main.py")],
    pathex=[project_root],
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
    os.path.join(data_dir, "splash.png"),
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
    icon=[os.path.join(data_dir, "app_icon.ico")],
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
