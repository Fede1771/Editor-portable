"""Script de compilación para generar el ejecutable portable con PyInstaller (H38)."""
import os
import shutil
import subprocess
import sys

root = os.path.dirname(os.path.abspath(__file__))
dist_dir = os.path.join(root, "dist")
spec_file = os.path.join(root, "EditorPDFPortable.spec")

# Limpiar cualquier perfil residual antiguo de LibreOffice dentro de data/ si existiera
legacy_lo_profile = os.path.join(root, "data", "lo_profile")
if os.path.isdir(legacy_lo_profile):
    shutil.rmtree(legacy_lo_profile, ignore_errors=True)

venv_pyinstaller = os.path.join(root, ".venv", "Scripts", "pyinstaller.exe")
if os.path.isfile(venv_pyinstaller):
    pyinstaller_cmd = [venv_pyinstaller, "--clean", "-y", spec_file]
else:
    pyinstaller_cmd = [sys.executable, "-m", "PyInstaller", "--clean", "-y", spec_file]

print("Iniciando empaquetado portable...")
print("Comando:", " ".join(pyinstaller_cmd))

proc = subprocess.run(pyinstaller_cmd, cwd=root)
if proc.returncode != 0:
    print("Error al compilar.")
    sys.exit(proc.returncode)

bundle_dir = os.path.join(dist_dir, "EditorPDFPortable")
exe_path = os.path.join(bundle_dir, "EditorPDFPortable.exe")
if os.path.isfile(exe_path):
    bat_src = os.path.join(root, "Abrir_EditorPortable.bat")
    if os.path.isfile(bat_src):
        shutil.copy2(bat_src, os.path.join(bundle_dir, "Abrir_EditorPortable.bat"))
    print("==================================================")
    print("¡COMPILACIÓN EXITOSA!")
    print(f"Ejecutable generado en: {exe_path}")
    zip_dest = os.path.join(dist_dir, "EditorPDFPortable")
    print("Generando paquete comprimido EditorPDFPortable.zip...")
    shutil.make_archive(zip_dest, "zip", dist_dir, "EditorPDFPortable")
    print(f"Paquete listo para distribución en: {zip_dest}.zip")
    print("==================================================")
else:
    print("El archivo ejecutable no fue encontrado en la carpeta dist.")
