"""Punto de entrada del Editor PDF Portable."""
import os
from pathlib import Path
import sys
import warnings

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

    for path in sys.argv[1:]:
        if path.lower().endswith(".pdf"):
            window.open_file(path)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
