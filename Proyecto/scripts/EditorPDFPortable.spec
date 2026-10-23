# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

# No resolver DLLs contra herramientas ajenas presentes en el PATH del shell.
# Por ejemplo, ICU de Poppler no implementa la ABI de ICU de Windows usada por Qt.
if sys.platform == "win32":
    windows_dir = os.environ.get("SystemRoot", r"C:\Windows")
    os.environ["PATH"] = os.pathsep.join([
        sys.base_prefix, os.path.join(sys.base_prefix, "DLLs"),
        os.path.join(sys.prefix, "Scripts"),
        os.path.join(windows_dir, "System32"), windows_dir,
    ])

project_root = os.path.dirname(os.path.abspath(SPECPATH))
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
for pkg in ("fitz", "pymupdf", "pypdf"):
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
    console=os.environ.get("EDITORPDF_BUILD_CONSOLE") == "1",
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
