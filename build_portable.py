"""Compilar y empaquetar el portable desde cualquier carpeta, sin publicar."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, default=root / "dist")
    parser.add_argument("--work-dir", type=Path, default=root / "build")
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()
    dist = args.dist_dir.resolve()
    work = args.work_dir.resolve()
    venv = root / ".venv/Scripts/python.exe"
    python = str(venv) if venv.is_file() else sys.executable
    cmd = [python, "-m", "PyInstaller", "--clean", "-y", "--distpath", str(dist),
           "--workpath", str(work), str(root / "EditorPDFPortable.spec")]
    print("Compilando el ejecutable portable...", flush=True)
    proc = subprocess.run(cmd, cwd=root)
    if proc.returncode:
        return proc.returncode
    bundle = dist / "EditorPDFPortable"
    exe = bundle / "EditorPDFPortable.exe"
    if not exe.is_file():
        print("No se encontró el ejecutable de salida.", file=sys.stderr)
        return 1
    shutil.copy2(root / "Abrir_EditorPortable.bat", bundle / "Abrir_EditorPortable.bat")
    print(f"Ejecutable generado: {exe}")
    if not args.no_zip:
        archive = shutil.make_archive(str(dist / "EditorPDFPortable"), "zip", str(dist), "EditorPDFPortable")
        print(f"Paquete generado: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
