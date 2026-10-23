"""Script de compilación para generar el ejecutable portable con PyInstaller."""
import os
import subprocess
import sys

root = os.path.dirname(os.path.abspath(__file__))
dist_dir = os.path.join(root, "dist")
build_dir = os.path.join(root, "build")
data_src = os.path.join(root, "data")
icon_ico = os.path.join(root, "data", "app_icon.ico")
splash_png = os.path.join(root, "data", "splash.png")

# Empaquetar recursos (tessdata e iconos)
add_data_param = f"{data_src};data"

pyinstaller_cmd = [
    os.path.join(root, ".venv", "Scripts", "pyinstaller.exe"),
    "--noconsole",
    "--name=EditorPDFPortable",
    "--clean",
    "-y",
    f"--icon={icon_ico}",
    f"--add-data={add_data_param}",
    f"--splash={splash_png}",
    "--collect-all=fitz",
    "--collect-all=pymupdf",
    "--collect-all=pdf2docx",
    "--collect-all=openpyxl",
    os.path.join(root, "main.py"),
]

print("Iniciando empaquetado portable...")
print("Comando:", " ".join(pyinstaller_cmd))

flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
proc = subprocess.run(pyinstaller_cmd, cwd=root)
if proc.returncode != 0:
    print("Error al compilar.")
    sys.exit(proc.returncode)

exe_path = os.path.join(dist_dir, "EditorPDFPortable", "EditorPDFPortable.exe")
if os.path.isfile(exe_path):
    import shutil
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
