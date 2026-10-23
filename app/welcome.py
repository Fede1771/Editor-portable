"""Pantalla de bienvenida y documentos recientes (Empty State minimalista)."""
import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from .settings_store import app_settings
from PySide6.QtGui import QCursor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

SETTINGS_ORG = "EditorPDFPortable"
SETTINGS_APP = "Settings"
KEY_RECENT_FILES = "recent_files"
MAX_RECENT_FILES = 8


def get_recent_files() -> list[str]:
    from .privacy import is_private_mode
    if is_private_mode():
        return []
    settings = app_settings()
    val = settings.value(KEY_RECENT_FILES, [])
    if isinstance(val, str):
        return [val] if val else []
    if isinstance(val, list):
        return [str(p) for p in val if p and os.path.exists(str(p))]
    return []


def add_recent_file(file_path: str) -> None:
    from .privacy import is_private_mode
    if is_private_mode():
        return
    if not file_path or not os.path.exists(file_path):
        return
    file_path = os.path.abspath(file_path)
    current = get_recent_files()
    if file_path in current:
        current.remove(file_path)
    current.insert(0, file_path)
    current = current[:MAX_RECENT_FILES]
    settings = app_settings()
    settings.setValue(KEY_RECENT_FILES, current)


def clear_recent_files() -> None:
    settings = app_settings()
    settings.setValue(KEY_RECENT_FILES, [])


class RecentFileItem(QWidget):
    """Fila para un documento reciente con nombre y ruta."""

    openRequested = Signal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.setCursor(QCursor(Qt.PointingHandCursor))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        icon_lbl = QLabel("📄")
        icon_font = QFont()
        icon_font.setPointSize(16)
        icon_lbl.setFont(icon_font)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        name_lbl = QLabel(os.path.basename(file_path))
        name_font = QFont()
        name_font.setPointSize(10)
        name_font.setBold(True)
        name_lbl.setFont(name_font)

        path_lbl = QLabel(os.path.dirname(file_path))
        path_font = QFont()
        path_font.setPointSize(8)
        path_lbl.setFont(path_font)
        path_lbl.setStyleSheet("color: gray;")

        text_layout.addWidget(name_lbl)
        text_layout.addWidget(path_lbl)

        layout.addWidget(icon_lbl)
        layout.addLayout(text_layout, 1)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.openRequested.emit(self.file_path)


class WelcomeWidget(QWidget):
    """Pantalla inicial visible cuando no hay documentos abiertos."""

    openFileRequested = Signal()
    openRecentRequested = Signal(str)
    blankDocRequested = Signal()
    combineRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setContentsMargins(20, 20, 20, 20)

        card = QFrame()
        card.setMaximumWidth(580)
        card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(30, 30, 30, 30)

        # Encabezado
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignCenter)
        header_layout.setSpacing(6)

        title_lbl = QLabel("Editor PDF Portable")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setAlignment(Qt.AlignCenter)

        sub_lbl = QLabel("Visualizador y editor ligero de documentos PDF")
        sub_font = QFont()
        sub_font.setPointSize(10)
        sub_lbl.setFont(sub_font)
        sub_lbl.setStyleSheet("color: gray;")
        sub_lbl.setAlignment(Qt.AlignCenter)

        header_layout.addWidget(title_lbl)
        header_layout.addWidget(sub_lbl)
        card_layout.addLayout(header_layout)

        # Zona central de acción
        drop_box = QFrame()
        drop_box.setFrameShape(QFrame.StyledPanel)
        drop_box.setStyleSheet("""
            QFrame {
                border: 2px dashed #8ab4f8;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        drop_layout = QVBoxLayout(drop_box)
        drop_layout.setAlignment(Qt.AlignCenter)
        drop_layout.setSpacing(10)

        drop_msg = QLabel("Arrastra tus archivos PDF aquí\no selecciona una opción:")
        drop_msg.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(drop_msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setAlignment(Qt.AlignCenter)

        self.btn_open = QPushButton("📂  Abrir archivo PDF…")
        self.btn_open.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_open.setFixedHeight(34)
        self.btn_open.clicked.connect(self.openFileRequested.emit)
        btn_row.addWidget(self.btn_open)

        self.btn_blank = QPushButton("📄  Documento en blanco")
        self.btn_blank.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_blank.setFixedHeight(34)
        self.btn_blank.clicked.connect(self.blankDocRequested.emit)
        btn_row.addWidget(self.btn_blank)

        drop_layout.addLayout(btn_row)
        card_layout.addWidget(drop_box)

        # Sección de archivos recientes
        self.recents_box = QWidget()
        self.recents_layout = QVBoxLayout(self.recents_box)
        self.recents_layout.setContentsMargins(0, 8, 0, 0)
        self.recents_layout.setSpacing(6)

        recents_header = QHBoxLayout()
        rec_title = QLabel("Documentos recientes")
        rec_font = QFont()
        rec_font.setBold(True)
        rec_title.setFont(rec_font)
        recents_header.addWidget(rec_title)

        recents_header.addStretch()
        btn_clear = QPushButton("Limpiar historial")
        btn_clear.setStyleSheet("border: none; color: gray; font-size: 8pt;")
        btn_clear.setCursor(QCursor(Qt.PointingHandCursor))
        btn_clear.clicked.connect(self._on_clear_recents)
        recents_header.addWidget(btn_clear)

        self.recents_layout.addLayout(recents_header)

        self.recents_list = QListWidget()
        self.recents_list.setSelectionMode(QListWidget.NoSelection)
        self.recents_list.setMaximumHeight(200)
        self.recents_layout.addWidget(self.recents_list)

        card_layout.addWidget(self.recents_box)

        main_layout.addWidget(card)
        self.refresh_recents()

    def refresh_recents(self):
        self.recents_list.clear()
        recents = get_recent_files()
        if not recents:
            self.recents_box.hide()
            return

        self.recents_box.show()
        for path in recents:
            item = QListWidgetItem()
            widget = RecentFileItem(path)
            widget.openRequested.connect(self.openRecentRequested.emit)
            item.setSizeHint(QSize(0, 48))
            self.recents_list.addItem(item)
            self.recents_list.setItemWidget(item, widget)

    def _on_clear_recents(self):
        clear_recent_files()
        self.refresh_recents()
