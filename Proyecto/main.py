"""Punto de entrada del Editor PDF Portable."""
import os
from pathlib import Path
import sys
import warnings
import multiprocessing

# Antes de cargar Qt/splash: PyInstaller despacha aquí los procesos PDF de spawn.
if __name__ == "__main__":
    multiprocessing.freeze_support()

# Suprimir advertencia transitoria de la API clásica de PyMuPDF
warnings.filterwarnings("ignore", category=FutureWarning, module=r"fitz(\..*)?")
warnings.filterwarnings("ignore", message=r".*The `fitz` API is deprecated.*", category=FutureWarning)

# Soporte de Splash nativo de PyInstaller (se muestra en <50ms por el bootloader en C)
try:
    import pyi_splash
    pyi_splash.update_text("Iniciando aplicación...")
except ImportError:
    pass

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def main() -> int:
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("editorpdf.portable.personal")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("Editor PDF Portable")
    from app.privacy import TempManager
    TempManager.sweep_orphaned_temps()

    icon_candidates = [
        Path(sys.executable).parent / "_internal" / "data" / "app_icon.png" if getattr(sys, "frozen", False) else None,
        Path(sys.executable).parent / "data" / "app_icon.png" if getattr(sys, "frozen", False) else None,
        Path(__file__).resolve().parent / "data" / "app_icon.png",
        Path(__file__).resolve().parent.parent / "data" / "app_icon.png",
    ]
    for p in icon_candidates:
        if p and p.exists():
            app.setWindowIcon(QIcon(str(p)))
            break

    window = MainWindow()
    window.show()

    # Cerrar splash nativo tan pronto la ventana principal está lista y visible
    try:
        import pyi_splash
        pyi_splash.close()
    except ImportError:
        pass

    os.environ["PYINSTALLER_SUPPRESS_SPLASH_SCREEN"] = "1"
    for path in sys.argv[1:]:
        if path.lower().endswith(".pdf"):
            window.open_file(path)
    return app.exec()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ["PYINSTALLER_SUPPRESS_SPLASH_SCREEN"] = "1"
        try:
            pyi_splash.close()
        except (NameError, RuntimeError):
            pass
        from app.diagnostics import self_test
        sys.exit(self_test(sys.argv[2]))
    sys.exit(main())
