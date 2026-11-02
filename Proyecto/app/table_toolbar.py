"""Barra contextual de tablas, con medidas legibles y acciones por celda."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu,
    QPushButton, QToolButton, QWidget,
)


class TableToolbar(QFrame):
    actionRequested = Signal(str)
    heightPreviewChanged = Signal(float)
    closed = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("TableToolbar")
        self.setAccessibleName("Edición de tabla")
        self.setAutoFillBackground(True)
        self.setStyleSheet("""
            QFrame#TableToolbar { background: palette(window); border: 1px solid palette(mid); border-radius: 7px; }
            QToolButton, QPushButton { padding: 6px 9px; border-radius: 4px; }
            QToolButton:hover, QPushButton:hover { background: palette(midlight); }
            QToolButton::menu-button { background: transparent; border: none; width: 14px; }
            QDoubleSpinBox { padding: 4px; min-height: 22px; }
        """)
        self.layout_grid = QGridLayout(self)
        self.layout_grid.setContentsMargins(10, 7, 10, 8)
        self.layout_grid.setHorizontalSpacing(8)
        self.layout_grid.setVerticalSpacing(6)
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("Seleccioná una celda")
        self.label.setWordWrap(True)
        header_layout.addWidget(self.label, 1)
        close = QToolButton()
        close.setText("×")
        close.setAccessibleName("Cerrar barra de tabla")
        close.setToolTip("Cerrar barra de tabla (Esc)")
        close.clicked.connect(self.closed)
        header_layout.addWidget(close)
        self.layout_grid.addWidget(header, 0, 0, 1, 5)
        self.row_button = self._insert_button("Insertar fila debajo", "row_below", "Insertar fila arriba", "row_above")
        self.column_button = self._insert_button("Insertar columna", "column_after", "Insertar a la izquierda", "column_before")
        self.delete_button = QToolButton(self)
        self.delete_button.setText("Eliminar")
        self.delete_button.setAccessibleName("Eliminar fila o columna")
        self.delete_button.setToolTip("Eliminar la fila o columna seleccionada y su contenido. Se puede deshacer con Ctrl+Z.")
        self.delete_button.setPopupMode(QToolButton.InstantPopup)
        delete_menu = QMenu(self.delete_button)
        self.delete_row_action = delete_menu.addAction("Eliminar fila", lambda: self.actionRequested.emit("delete_row"))
        self.delete_column_action = delete_menu.addAction("Eliminar columna", lambda: self.actionRequested.emit("delete_column"))
        self.delete_button.setMenu(delete_menu)
        self.measure = QWidget(self)
        measure_layout = QHBoxLayout(self.measure)
        measure_layout.setContentsMargins(0, 0, 0, 0)
        measure_layout.setSpacing(5)
        label = QLabel("Alto:")
        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(2, 200)
        self.height_spin.setDecimals(1)
        self.height_spin.setSuffix(" mm")
        self.height_spin.setSingleStep(1)
        self.height_spin.setKeyboardTracking(False)
        self.height_spin.setAccessibleName("Alto de fila en milímetros")
        label.setBuddy(self.height_spin)
        self.apply_button = QPushButton("Aplicar")
        self.apply_button.setToolTip("Aplicar el alto de fila mostrado en la vista previa")
        self.apply_button.clicked.connect(lambda: self.actionRequested.emit("resize"))
        self.height_spin.valueChanged.connect(lambda value: self.heightPreviewChanged.emit(value * 72 / 25.4))
        measure_layout.addWidget(label)
        measure_layout.addWidget(self.height_spin)
        measure_layout.addWidget(self.apply_button)
        self.undo_button = QPushButton("Deshacer")
        self.undo_button.setToolTip("Deshacer el último cambio del documento (Ctrl+Z)")
        self.undo_button.clicked.connect(lambda: self.actionRequested.emit("undo"))
        self._compact = None
        self.fit_to_width(900)
        self.hide()

    def _insert_button(self, text, action, other_text, other_action):
        button = QToolButton(self)
        primary = QAction(text, button)
        primary.triggered.connect(lambda: self.actionRequested.emit(action))
        button.setDefaultAction(primary)
        button.setPopupMode(QToolButton.MenuButtonPopup)
        menu = QMenu(button)
        menu.addAction(text, lambda: self.actionRequested.emit(action))
        menu.addAction(other_text, lambda: self.actionRequested.emit(other_action))
        button.setMenu(menu)
        return button

    def fit_to_width(self, available):
        compact = available < 790
        if compact != self._compact:
            self._compact = compact
            for widget in (self.row_button, self.column_button, self.delete_button, self.measure, self.undo_button):
                self.layout_grid.removeWidget(widget)
            self.layout_grid.addWidget(self.row_button, 1, 0)
            self.layout_grid.addWidget(self.column_button, 1, 1)
            self.layout_grid.addWidget(self.delete_button, 1, 2)
            self.layout_grid.addWidget(self.measure, 2 if compact else 1, 0 if compact else 3)
            self.layout_grid.addWidget(self.undo_button, 2 if compact else 1, 1 if compact else 4)
        self.adjustSize()

    def set_selection(self, table, row, column_index=0):
        preview = row["preview"].replace("\n", " ").split(" | ")[0]
        if len(preview) > 34:
            preview = preview[:33] + "…"
        self.label.setText(f"Tabla {table['index'] + 1} · Fila {row['row_index'] + 1} · Columna {column_index + 1} · {preview}")
        self.label.setToolTip("Estilo original · Se conserva el tamaño de página")
        self.delete_row_action.setEnabled(table["row_count"] > 1)
        self.delete_column_action.setEnabled(table["col_count"] > 1)
        self.delete_row_action.setText(f"Eliminar fila {row['row_index'] + 1}")
        self.delete_column_action.setText(f"Eliminar columna {column_index + 1}")
        self.height_spin.blockSignals(True)
        self.height_spin.setValue((row["bbox"][3] - row["bbox"][1]) * 25.4 / 72)
        self.height_spin.blockSignals(False)
        self.apply_button.setEnabled(False)
