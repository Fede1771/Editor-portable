"""Punto de entrada del Editor PDF Portable."""
import os
from pathlib import Path
import sys

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

    icon_path = Path(__file__).resolve().parent / "data" / "app_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    for path in sys.argv[1:]:
        if path.lower().endswith(".pdf"):
            window.open_file(path)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
