"""Pruebas de regresión para el panel lateral de miniaturas:
Garantiza que documentos de 1 página (que inician con panel plegado) y de múltiples páginas
muestren las miniaturas centradas sin desplazamientos laterales ni barras de desplazamiento horizontal.
"""

import fitz
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def test_thumbnail_alignment_single_and_multi_page(qapp):
    win = MainWindow()
    win.resize(1200, 800)
    win.show()
    qapp.processEvents()

    # 1. Documento de 1 página (como Armario.pdf)
    doc1 = fitz.open()
    doc1.new_page()
    win._add_tab("Armario.pdf", doc1)
    qapp.processEvents()

    tab0 = win.tabs.widget(0)
    # Por diseño inteligente, arranca con barra lateral plegada para <= 2 páginas
    assert not tab0.side.isVisible()

    # Usuario activa el panel lateral
    win.a_side.trigger()
    qapp.processEvents()
    assert tab0.side.isVisible()

    r0 = tab0.thumbs.visualRect(tab0.thumbs.model().index(0, 0))
    vw0 = tab0.thumbs.viewport().width()
    # No debe existir barra de scroll horizontal
    assert tab0.thumbs.horizontalScrollBar().maximum() == 0
    assert abs(r0.width() - vw0) <= 6

    # 2. Documento multipágina (como Guia.pdf)
    doc2 = fitz.open()
    for _ in range(13):
        doc2.new_page()
    win._add_tab("Guia.pdf", doc2)
    qapp.processEvents()

    tab1 = win.tabs.widget(1)
    assert tab1.side.isVisible()
    assert tab1.thumbs.horizontalScrollBar().maximum() == 0

    # 3. Alternancia de pestañas
    win.tabs.setCurrentIndex(0)
    qapp.processEvents()
    assert tab0.thumbs.horizontalScrollBar().maximum() == 0

    # 4. Redimensionado elástico del panel
    tab0.splitter.setSizes([260, 940])
    qapp.processEvents()
    r0_wide = tab0.thumbs.visualRect(tab0.thumbs.model().index(0, 0))
    vw0_wide = tab0.thumbs.viewport().width()
    assert tab0.thumbs.horizontalScrollBar().maximum() == 0
    assert abs(r0_wide.width() - vw0_wide) <= 6
