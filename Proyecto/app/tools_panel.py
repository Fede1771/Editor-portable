"""Herramientas por tarea y controles que se acomodan sin menús de desborde."""
import unicodedata

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLayout, QLineEdit, QListWidget,
    QListWidgetItem, QToolButton,
    QVBoxLayout, QHBoxLayout, QMenu, QWidget,
    QStyle,
)


class FlowLayout(QLayout):
    """Distribuye controles en tantas líneas como haga falta, conservando su tamaño."""
    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _arrange(self, rect, measure):
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line_height = area.x(), area.y(), 0
        for item in self._items:
            if item.widget() and item.widget().isHidden():
                continue
            size = item.sizeHint()
            if x + size.width() > area.right() + 1 and line_height:
                x, y, line_height = area.x(), y + line_height + self.spacing(), 0
            if not measure:
                item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width() + self.spacing()
            line_height = max(line_height, size.height())
        return y + line_height - rect.y() + margins.bottom()


SVG_SIDEBAR = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>
<rect x='3' y='3' width='18' height='18' rx='2'></rect>
<line x1='9' y1='3' x2='9' y2='21'></line>
<line x1='5' y1='7' x2='7' y2='7'></line>
<line x1='5' y1='11' x2='7' y2='11'></line>
<line x1='5' y1='15' x2='7' y2='15'></line>
</svg>"""

SVG_FIT_WIDTH = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>
<line x1='3' y1='4' x2='3' y2='20'></line>
<line x1='21' y1='4' x2='21' y2='20'></line>
<polyline points='8 9 5 12 8 15'></polyline>
<polyline points='16 9 19 12 16 15'></polyline>
<line x1='5' y1='12' x2='19' y2='12'></line>
</svg>"""

SVG_FIT_PAGE = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>
<rect x='5' y='3' width='14' height='18' rx='2'></rect>
<polyline points='9 7 12 4 15 7'></polyline>
<polyline points='9 17 12 20 15 17'></polyline>
<line x1='12' y1='4' x2='12' y2='20'></line>
</svg>"""


def _make_svg_icon(svg_xml: str):
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QByteArray
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor

    app = QApplication.instance()
    normal_color = app.palette().windowText().color().name() if app else "#dcdcdc"
    disabled_color = "#888888" if (app and app.palette().windowText().color().lightness() > 128) else "#aaaaaa"

    icon = QIcon()
    for c, mode in [(normal_color, QIcon.Normal), (disabled_color, QIcon.Disabled)]:
        svg = svg_xml.replace("currentColor", c)
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pix = QPixmap(20, 20)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        renderer.render(p)
        p.end()
        icon.addPixmap(pix, mode)
    return icon


class ToolsPanel(QWidget):
    """Dos franjas compactas: navegación y herramientas, sin cinta de pestañas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ToolsPanel")
        self.setAccessibleName("Herramientas del documento")
        self.setStyleSheet("""
            QWidget#ToolsPanel { background: palette(window); border-bottom: 1px solid palette(mid); }
            QToolButton { padding: 5px 8px; border: 1px solid transparent; border-radius: 5px; min-height: 19px; font-size: 9pt; }
            QToolButton:hover { background: palette(midlight); }
            QToolButton:checked { background: palette(highlight); color: palette(highlighted-text); }
            QToolButton:focus { border-color: palette(highlight); }
            QToolButton::menu-indicator { subcontrol-position: right center; right: 3px; }
            QToolButton::menu-button { background: transparent; border: none; width: 14px; }
            QToolButton[hasMenu="true"] { padding-right: 16px; }
            QToolButton#BtnMain {
                padding: 3px 20px 3px 8px;
                font-weight: 600;
                font-size: 9pt;
                border: 1px solid palette(mid);
                background: palette(button);
            }
            QToolButton#BtnMain:hover {
                background: palette(midlight);
            }
            QToolButton#BtnMain::menu-indicator {
                subcontrol-position: right center;
                right: 6px;
            }
            QCheckBox#ChkFitScreen {
                color: palette(windowText);
                font-size: 9pt;
                padding-left: 3px;
                padding-right: 4px;
            }
            QSpinBox {
                padding: 1px 2px;
                border: 1px solid palette(mid);
                border-radius: 5px;
                background: palette(base);
                color: palette(text);
                font-size: 9pt;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                subcontrol-origin: border;
                width: 0px;
                height: 0px;
                border: none;
            }
            QSpinBox:focus {
                border: 1px solid palette(highlight);
            }
            QSpinBox:disabled {
                color: palette(disabled, text);
                background: palette(window);
                border-color: palette(midlight);
            }
            QComboBox {
                padding: 2px 6px;
                border: 1px solid palette(mid);
                border-radius: 5px;
                background: palette(base);
                color: palette(text);
                font-size: 9pt;
            }
            QComboBox:focus {
                border: 1px solid palette(highlight);
            }
            QLabel#PageTotal {
                color: palette(windowText);
                font-size: 9pt;
                padding: 0 4px;
            }
            QMenu { padding: 5px; }
            QMenu::item { padding: 7px 26px 7px 12px; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 5)
        layout.setSpacing(3)
        self.quick = QWidget(self)
        self.quick_flow = QHBoxLayout(self.quick)
        self.quick_flow.setContentsMargins(0, 0, 0, 0)
        self.quick_flow.setSpacing(3)
        layout.addWidget(self.quick)
        self.tools = QWidget(self)
        self.tools_flow = FlowLayout(self.tools, spacing=3)
        layout.addWidget(self.tools)
        self.groups = {}
        self.current_group = "Editar"

    @staticmethod
    def button(action, parent=None, text=None):
        button = QToolButton(parent)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        label = text or action.text().replace("&", "")
        button.setProperty("fullLabel", label)
        button.setAccessibleName(label)
        tip = action.statusTip() or action.toolTip() or action.text()
        shortcut = action.shortcut().toString(QKeySequenceFormat)
        icons = {"Abrir": QStyle.SP_DialogOpenButton, "Guardar": QStyle.SP_DialogSaveButton,
                 "Deshacer": QStyle.SP_ArrowBack, "Rehacer": QStyle.SP_ArrowForward,
                 "Buscar texto": QStyle.SP_FileDialogContentsView,
                 "Panel lateral": QStyle.SP_FileDialogDetailedView,
                 "◀": QStyle.SP_ArrowLeft,
                 "▶": QStyle.SP_ArrowRight,
                 "Página anterior": QStyle.SP_ArrowLeft,
                 "Página siguiente": QStyle.SP_ArrowRight}
        is_nav_arrow = label in ("◀", "▶", "Página anterior", "Página siguiente")
        is_compact = is_nav_arrow or label in ("－", "＋", "☰")
        if is_compact:
            button.setProperty("iconOnly", True)
            button.setFixedSize(28, 28)
            if is_nav_arrow:
                button.setIconSize(QSize(12, 12))

        def sync_label():
            if is_nav_arrow:
                button.setText("")
            else:
                button.setText(label)
            if label == "Panel lateral":
                try:
                    button.setIcon(_make_svg_icon(SVG_SIDEBAR))
                except Exception:
                    button.setIcon(button.style().standardIcon(QStyle.SP_FileDialogDetailedView))
            elif label in ("Ancho", "Ajustar ancho"):
                try:
                    button.setIcon(_make_svg_icon(SVG_FIT_WIDTH))
                except Exception:
                    button.setIcon(button.style().standardIcon(QStyle.SP_TitleBarMaxButton))
            elif label in ("Página", "Ajustar página"):
                try:
                    button.setIcon(_make_svg_icon(SVG_FIT_PAGE))
                except Exception:
                    button.setIcon(button.style().standardIcon(QStyle.SP_TitleBarNormalButton))
            elif label in icons and icons[label] is not None:
                button.setIcon(button.style().standardIcon(icons[label]))
            button.setToolButtonStyle(Qt.ToolButtonIconOnly if button.property("iconOnly") else Qt.ToolButtonTextBesideIcon)
            button.setToolTip(tip + (f" ({shortcut})" if shortcut and shortcut not in tip else ""))
        action.changed.connect(sync_label)
        sync_label()
        return button

    def add_group(self, name, actions):
        menu = QMenu(self)
        self.groups[name] = menu
        entries = [entry if isinstance(entry, tuple) else (entry, None) for entry in actions]
        if name == "Editar":
            for action, label in entries[:5]:
                self.tools_flow.addWidget(self.button(action, self.tools, label))
            for action, _ in entries:
                menu.addAction(action)
        else:
            button = QToolButton(self.tools)
            button.setProperty("hasMenu", True)
            button.setText(name)
            button.setAccessibleName(f"Herramientas de {name.lower()}")
            button.setToolTip(f"{name}: " + ", ".join(label or action.text() for action, label in entries))
            if name == "Tablas":
                primary, label = entries[0]
                button.setDefaultAction(primary)
                primary.changed.connect(lambda: button.setText("Tablas"))
                button.setText("Tablas")
                button.setPopupMode(QToolButton.MenuButtonPopup)
            else:
                button.setPopupMode(QToolButton.InstantPopup)
            for action, _ in entries:
                menu.addAction(action)
            button.setMenu(menu)
            self.tools_flow.addWidget(button)
        self._resize_current()

    def choose(self, name):
        if name in self.groups:
            self.current_group = name

    def _resize_current(self):
        available = max(1, self.width() - 16)
        compact = available < 1000
        narrow = available < 720
        for button in self.quick.findChildren(QToolButton):
            label = button.property("fullLabel")
            if label:
                only = label in ("Deshacer", "Rehacer") or compact and label in (
                    "Abrir", "Guardar", "Buscar texto", "Panel lateral", "Ancho", "Página", "Ajustar ancho", "Ajustar página")
                button.setProperty("iconOnly", only)
                button.setToolButtonStyle(Qt.ToolButtonIconOnly if only else Qt.ToolButtonTextBesideIcon)
                button.setVisible(not (narrow and label in ("Deshacer", "Rehacer")))
        self.quick.setFixedHeight(34)
        self.tools.setFixedHeight(max(32, self.tools_flow.heightForWidth(available)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_current()


# Usar el mismo formato nativo en botones y en el buscador.
from PySide6.QtGui import QKeySequence
QKeySequenceFormat = QKeySequence.NativeText


class ToolFinder(QDialog):
    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buscar herramienta")
        self.resize(540, 440)
        self.chosen_action = None
        self.actions = list(dict.fromkeys(actions))
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setAccessibleName("Nombre de la herramienta")
        self.search.setPlaceholderText("Ej.: rotar, OCR, texto, comprimir…")
        self.items = QListWidget()
        self.items.setAccessibleName("Herramientas disponibles")
        layout.addWidget(self.search)
        layout.addWidget(self.items)
        layout.addWidget(QLabel("Las opciones atenuadas no están disponibles en el documento actual."))
        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._pick)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._pick)
        self.items.itemActivated.connect(self._pick)
        self._filter("")
        self.search.setFocus()

    @staticmethod
    def _normal(text):
        return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn")

    def _filter(self, query):
        self.items.clear()
        for action in self.actions:
            if self._normal(query) not in self._normal(action.text() + " " + action.toolTip()):
                continue
            shortcut = action.shortcut().toString(QKeySequenceFormat)
            label = action.text().replace("&", "") + (f"    {shortcut}" if shortcut else "")
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, action)
            if not action.isEnabled():
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.items.addItem(item)
        for i in range(self.items.count()):
            if self.items.item(i).flags() & Qt.ItemIsEnabled:
                self.items.setCurrentRow(i)
                break

    def _pick(self, *_):
        item = self.items.currentItem()
        if item and item.flags() & Qt.ItemIsEnabled:
            self.chosen_action = item.data(Qt.UserRole)
            self.accept()
