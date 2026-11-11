import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import pymupdf as fitz

from app.main_window import MainWindow
from app.viewer import FIT_NONE, FIT_PAGE, FIT_WIDTH


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_ui_refinements_and_zoom_check(qapp, tmp_path):
    # Crear un PDF de prueba de 2 páginas
    pdf_path = str(tmp_path / "test_doc.pdf")
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.new_page(width=595, height=842)
    doc.save(pdf_path)
    doc.close()

    win = MainWindow()
    win.open_file(pdf_path)

    # 1. Verificar btn_main ("Archivo")
    assert win.btn_main.text() == "Archivo"
    assert win.btn_main.objectName() == "BtnMain"
    assert not win.btn_main.icon().isNull()
    assert win.btn_main.property("hasMenu") is True
    assert win.btn_main.height() == 28

    # 2. Verificar btn_side ("Panel lateral")
    assert win.btn_side.property("fullLabel") == "Panel lateral"
    assert win.btn_side.isCheckable() is True
    assert not win.btn_side.icon().isNull()

    tab = win.current_tab()
    assert tab is not None
    assert win.btn_side.isChecked() == tab.side.isVisible()

    # Probar toggle de panel
    win.btn_side.click()
    assert tab.side.isVisible() == win.btn_side.isChecked()
    win.btn_side.click()
    assert tab.side.isVisible() == win.btn_side.isChecked()

    # 3. Verificar btn_fit_w ("Ancho") y btn_fit_p ("Página")
    assert hasattr(win, "btn_fit_w")
    assert hasattr(win, "btn_fit_p")
    assert win.btn_fit_w.isCheckable() is True
    assert win.btn_fit_p.isCheckable() is True
    assert not win.btn_fit_w.icon().isNull()
    assert not win.btn_fit_p.icon().isNull()

    # Arranca en FIT_PAGE: Página está activo, Ancho está inactivo
    assert tab.view.fit == FIT_PAGE
    assert win.btn_fit_p.isChecked() is True
    assert win.btn_fit_w.isChecked() is False

    # Al hacer clic en Ancho, pasa a FIT_WIDTH
    win.btn_fit_w.click()
    assert tab.view.fit == FIT_WIDTH
    assert win.btn_fit_w.isChecked() is True
    assert win.btn_fit_p.isChecked() is False

    # Al hacer clic en Página, vuelve a FIT_PAGE
    win.btn_fit_p.click()
    assert tab.view.fit == FIT_PAGE
    assert win.btn_fit_p.isChecked() is True
    assert win.btn_fit_w.isChecked() is False

    # Si se hace zoom manual (ej. zoom in o cambio en combo), ambos quedan desmarcados
    tab.view.zoom_in()
    assert tab.view.fit == FIT_NONE
    assert win.btn_fit_w.isChecked() is False
    assert win.btn_fit_p.isChecked() is False

    # 4. Verificar que el botón ruidoso 'Herramientas' NO está en la barra rápida,
    # pero el atajo Ctrl+K sigue registrado en la ventana
    labels_in_quick = [
        btn.property("fullLabel")
        for btn in win.tools_panel.quick.findChildren(type(win.btn_main))
        if btn.property("fullLabel")
    ]
    assert "Herramientas" not in labels_in_quick
    assert win.a_commands in win.actions()
    assert win.a_commands.shortcut().toString() == "Ctrl+K"

    # 5. El ancho mínimo sugerido del panel lateral no excede 190px
    assert tab.side.minimumSizeHint().width() <= 190

    win.close()
