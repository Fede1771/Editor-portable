"""Regresiones de inserción, estilo, objetos PDF y barra contextual."""
import math

import pymupdf as fitz
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from app import operations as ops
from app import table_edit


@pytest.fixture
def table_doc():
    doc = fitz.open()
    p = doc.new_page(width=500, height=600)
    purple = (.50, .39, .64)
    grid = (.82, .80, .87)
    p.draw_rect((50, 50, 450, 100), color=purple, fill=purple, width=.5)
    p.draw_rect((50, 100, 450, 200), color=grid, width=.5)
    p.draw_line((50, 150), (450, 150), color=grid, width=.5)
    p.draw_line((200, 100), (200, 200), color=grid, width=.5)
    p.insert_text((190, 80), "Curso", color=(1, 1, 1))
    p.insert_text((60, 125), "Inicio")
    p.insert_text((210, 125), "15/07/2026")
    p.insert_text((60, 175), "Fin")
    p.insert_text((210, 175), "18/12/2026")
    p.insert_text((60, 350), "Notas al pie")
    yield doc
    doc.close()


def _table(doc):
    tables = ops.detect_tables_on_page(doc[0])
    assert len(tables) == 1
    return tables[0]


def _pixel(page, x, y):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fitz.Rect(x, y, x + 1, y + 1), alpha=False)
    return pix.pixel(0, 0)


def test_insert_row_keeps_page_text_style_and_detects_repeated_edits(table_doc):
    original = table_doc[0].rect
    table_edit.edit_row(table_doc, 0, _table(table_doc), 1, insert="below", height=25)
    assert table_doc[0].rect == original
    assert _table(table_doc)["row_count"] == 4
    assert table_doc[0].get_text().count("Inicio") == 1
    assert table_doc[0].search_for("Fin")[0].y0 == pytest.approx(188.175, abs=.1)
    border = _pixel(table_doc[0], 200, 162)
    assert min(border) > 170  # conservar el gris claro, sin líneas negras
    table_edit.edit_row(table_doc, 0, _table(table_doc), 2, insert="below", height=20)
    assert _table(table_doc)["row_count"] == 5
    assert table_doc[0].get_text().count("Curso") == 1


def test_resize_merged_header_extends_purple_without_column_divider(table_doc):
    table_edit.edit_row(table_doc, 0, _table(table_doc), 0, height=75)
    pixel = _pixel(table_doc[0], 200, 110)
    assert pixel[0] == pytest.approx(128, abs=3)
    assert pixel[1] == pytest.approx(99, abs=3)
    assert _table(table_doc)["row_count"] == 3
    assert _table(table_doc)["rows"][0]["bbox"][3] == pytest.approx(125, abs=.2)


@pytest.mark.parametrize("column,before", [(0, False), (0, True), (1, False)])
def test_insert_column_keeps_merged_header_and_content(table_doc, column, before):
    page_xref = table_doc[0].xref
    table_edit.insert_column(table_doc, 0, _table(table_doc), column, before=before)
    result = _table(table_doc)
    assert result["col_count"] == 3
    assert result["bbox"][2] - result["bbox"][0] == pytest.approx(400, abs=1)
    assert sum(c is not None for c in result["rows"][0]["cells"]) == 1
    assert table_doc[0].xref == page_xref
    for word in ("Curso", "Inicio", "Fin", "15/07/2026", "Notas al pie"):
        assert table_doc[0].get_text().count(word) == 1


def test_resize_can_shrink_blank_space_but_never_crop_text(table_doc):
    table_edit.edit_row(table_doc, 0, _table(table_doc), 1, height=35)
    assert _table(table_doc)["rows"][1]["bbox"][3] == pytest.approx(135, abs=.2)
    assert table_doc[0].search_for("Inicio")
    with pytest.raises(ValueError, match="cortaría el texto"):
        table_edit.edit_row(table_doc, 0, _table(table_doc), 1, height=8)


def test_row_edit_preserves_page_identity_bookmark_annotations_and_widget(table_doc):
    p = table_doc[0]
    xref = p.xref
    note = p.add_text_annot((300, 400), "Conservar comentario")
    old_note_y = note.rect.y0
    highlight = p.add_highlight_annot(p.search_for("Notas al pie"))
    old_vertex = highlight.vertices[0][1]
    widget = fitz.Widget()
    widget.field_name = "firma"
    widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect = fitz.Rect(60, 430, 180, 455)
    widget.field_value = "Nombre"
    p.add_widget(widget)
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(60, 330, 120, 350), "uri": "https://example.com"})
    table_doc.set_toc([[1, "Curso", 1]])
    table_edit.edit_row(table_doc, 0, _table(table_doc), 1, insert="below", height=25)
    p = table_doc[0]
    assert p.xref == xref
    assert table_doc.get_toc()[0][2] == 1
    annots = list(p.annots())
    assert annots[0].info["content"] == "Conservar comentario"
    assert annots[0].rect.y0 == pytest.approx(old_note_y + 25)
    assert annots[1].vertices[0][1] == pytest.approx(old_vertex + 25)
    assert p.get_links()[0]["from"].y0 == pytest.approx(355)
    field = next(p.widgets())
    assert field.field_value == "Nombre"
    assert field.rect.y0 == pytest.approx(455)


def test_no_room_does_not_change_document(table_doc):
    table_doc[0].insert_text((60, 590), "Pie final")
    before = table_doc.tobytes(no_new_id=True)
    with pytest.raises(ValueError, match="No hay espacio"):
        table_edit.edit_row(table_doc, 0, _table(table_doc), 1, insert="below", height=25)
    assert table_doc.tobytes(no_new_id=True) == before


def test_row_cannot_cut_text_beside_table(table_doc):
    table_doc[0].insert_text((455, 150), "Nota", fontsize=9)
    with pytest.raises(ValueError, match="cortaría texto"):
        table_edit.edit_row(table_doc, 0, _table(table_doc), 1, insert="below", height=20)


def test_saved_document_keeps_repeated_edits(table_doc):
    table_edit.edit_row(table_doc, 0, _table(table_doc), 1, insert="below", height=20)
    table_edit.insert_column(table_doc, 0, _table(table_doc), 0)
    with fitz.open(stream=table_doc.tobytes(garbage=3, deflate=True), filetype="pdf") as reopened:
        result = _table(reopened)
        assert result["col_count"] == 3
        assert result["row_count"] == 4
        assert reopened[0].get_text().count("Inicio") == 1


@pytest.mark.parametrize("height", [math.nan, math.inf, -1, 0])
def test_invalid_measure_is_rejected(table_doc, height):
    with pytest.raises(ValueError):
        table_edit.edit_row(table_doc, 0, _table(table_doc), 1, height=height)


def test_contextual_actions_apply_to_selected_cell_and_undo(qapp, table_doc):
    from app.main_window import MainWindow
    from app.viewer import TOOL_TABLE
    window = MainWindow()
    owned_doc = fitz.open(stream=table_doc.tobytes(), filetype="pdf")
    window._add_tab("", owned_doc)
    window.resize(1100, 900)
    window.show()
    window._set_active_tool(TOOL_TABLE)
    qapp.processEvents()
    tab = window.current_tab()
    view = tab.view
    pt = view._map_point(0, fitz.Point(110, 125)) + view._page_rects[0].topLeft()
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=QPoint(round(pt.x()), round(pt.y())))
    qapp.processEvents()
    assert view.table_toolbar.isVisible()
    assert view._table_selection[2]["row_index"] == 1
    view._table_action("row_below")
    assert _table(tab.doc)["row_count"] == 4
    rows = _table(tab.doc)["rows"]
    assert rows[2]["preview"] == "Fila 3"  # insertar exactamente debajo de Inicio
    assert "Fin" in rows[3]["preview"]
    view._table_action("undo")
    assert _table(tab.doc)["row_count"] == 3
    view._table_action("column_after")
    assert _table(tab.doc)["col_count"] == 3
    assert _table(tab.doc)["rows"][1]["cells"][1] is not None
    view.set_tool("select")
    assert not view.table_toolbar.isVisible()
    tab.close_document()
    window.deleteLater()


@pytest.mark.parametrize("row_index", [0, 1, 2])
def test_delete_row_closes_gap_and_removes_only_selected_content(table_doc, row_index):
    original_xref = table_doc[0].xref
    original_size = table_doc[0].rect
    words = ["Curso", "Inicio", "Fin"]
    table_edit.delete_row(table_doc, 0, _table(table_doc), row_index)
    assert table_doc[0].rect == original_size
    assert table_doc[0].xref == original_xref
    text = table_doc[0].get_text()
    assert words[row_index] not in text
    assert all(word in text for i, word in enumerate(words) if i != row_index)
    assert _table(table_doc)["row_count"] == 2
    assert table_doc[0].search_for("Notas al pie")[0].y0 == pytest.approx(288.175, abs=.2)


@pytest.mark.parametrize("column_index", [0, 1])
def test_delete_column_keeps_merged_heading_and_page_width(table_doc, column_index):
    size = table_doc[0].rect
    table_edit.delete_column(table_doc, 0, _table(table_doc), column_index)
    result = _table(table_doc)
    assert result["col_count"] == 1
    assert result["bbox"][2] - result["bbox"][0] == pytest.approx(400, abs=.2)
    text = table_doc[0].get_text()
    assert text.count("Curso") == 1
    assert ("Inicio" in text) is (column_index == 1)
    assert ("15/07/2026" in text) is (column_index == 0)
    assert table_doc[0].rect == size
    with pytest.raises(ValueError, match="al menos una columna"):
        table_edit.delete_column(table_doc, 0, result, 0)


def test_delete_inserted_row_and_column_restores_grid(table_doc):
    table_edit.edit_row(table_doc, 0, _table(table_doc), 1, insert="below", height=20)
    table_edit.insert_column(table_doc, 0, _table(table_doc), 0)
    table_edit.delete_column(table_doc, 0, _table(table_doc), 1)
    table_edit.delete_row(table_doc, 0, _table(table_doc), 2)
    result = _table(table_doc)
    assert (result["row_count"], result["col_count"]) == (3, 2)
    assert table_doc[0].get_text().count("Inicio") == 1


def test_last_remaining_cell_is_still_editable(table_doc):
    table_edit.delete_column(table_doc, 0, _table(table_doc), 0)
    table_edit.delete_row(table_doc, 0, _table(table_doc), 2)
    table_edit.delete_row(table_doc, 0, _table(table_doc), 1)
    result = _table(table_doc)
    assert (result["row_count"], result["col_count"]) == (1, 1)
    with pytest.raises(ValueError, match="al menos una fila"):
        table_edit.delete_row(table_doc, 0, result, 0)
    table_edit.edit_row(table_doc, 0, result, 0, insert="below", height=20)
    assert _table(table_doc)["row_count"] == 2


def test_delete_row_moves_notes_and_never_removes_neighbor_text(table_doc):
    page = table_doc[0]
    note = page.add_text_annot((300, 400), "Nota conservada")
    old_y = note.rect.y0
    table_edit.delete_row(table_doc, 0, _table(table_doc), 1)
    page = table_doc[0]
    assert next(page.annots()).rect.y0 == pytest.approx(old_y - 50)
    page.insert_text((455, 125), "Fuera", fontsize=8)
    before = page.get_text()
    with pytest.raises(ValueError, match="contenido junto"):
        table_edit.delete_row(table_doc, 0, _table(table_doc), 1)
    assert page.get_text() == before


def test_selection_shows_table_actions_without_switching_tools(qapp, table_doc):
    from app.doc_tab import DocTab
    from app.viewer import TOOL_SELECT
    doc = fitz.open(stream=table_doc.tobytes(), filetype="pdf")
    tab = DocTab("", doc)
    tab.resize(1000, 800)
    tab.show()
    qapp.processEvents()
    view = tab.view
    pt = view._map_point(0, fitz.Point(110, 125)) + view._page_rects[0].topLeft()
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=QPoint(round(pt.x()), round(pt.y())))
    assert view._tool == TOOL_SELECT
    assert view.table_toolbar.isVisible()
    assert view.table_toolbar.delete_row_action.isEnabled()
    tab.close_document()
    tab.deleteLater()


def test_delete_actions_support_undo_and_redo(qapp, table_doc):
    from app.main_window import MainWindow
    from app.viewer import TOOL_TABLE
    window = MainWindow()
    window._add_tab("", fitz.open(stream=table_doc.tobytes(), filetype="pdf"))
    tab = window.current_tab()
    window._set_active_tool(TOOL_TABLE)
    tab.view.select_table_cell(0, 0, 1, 0)
    tab.view._table_action("delete_row")
    assert "Inicio" not in tab.doc[0].get_text()
    tab.undo()
    assert "Inicio" in tab.doc[0].get_text()
    tab.redo()
    assert "Inicio" not in tab.doc[0].get_text()
    tab.undo()
    tab.view.select_table_cell(0, 0, 1, 0)
    tab.view._table_action("delete_column")
    assert "Inicio" not in tab.doc[0].get_text()
    tab.undo()
    assert "Inicio" in tab.doc[0].get_text()
    tab.close_document()
    window.deleteLater()


def test_compact_tools_keep_menus_visible_and_finder_reaches_commands(qapp, table_doc):
    from app.main_window import MainWindow
    from app.tools_panel import ToolFinder
    window = MainWindow()
    window._add_tab("", fitz.open(stream=table_doc.tobytes(), filetype="pdf"))
    window.resize(1250, 850)
    window.show()
    qapp.processEvents()
    panel = window.tools_panel
    button_height = max(panel.tools_flow.itemAt(i).sizeHint().height() for i in range(panel.tools_flow.count()))
    assert not hasattr(panel, "tabs")
    assert panel.height() <= 34 + 2 * button_height + 16
    assert all(panel.groups[name].actions() for name in ("Editar", "Tablas", "Anotar", "Páginas", "Documento"))
    panel.choose("Páginas")
    assert panel.current_group == "Páginas"
    window.resize(620, 850)
    qapp.processEvents()
    assert panel.height() <= 34 + 3 * button_height + 20
    for i in range(panel.tools_flow.count()):
        button = panel.tools_flow.itemAt(i).widget()
        assert button.geometry().right() <= panel.tools.width()
        assert button.geometry().bottom() <= panel.tools.height()
        assert button.isVisible()
    for i in range(panel.quick_flow.count()):
        item = panel.quick_flow.itemAt(i)
        if item.widget() and item.widget().isVisible():
            assert item.geometry().right() <= panel.quick.width()
            assert item.geometry().bottom() <= panel.quick.height()
    finder = ToolFinder([window.a_ocr, window.a_compress, window.a_tool_text], window)
    finder.search.setText("comprimir")
    assert finder.items.count() == 1
    finder._pick()
    assert finder.chosen_action is window.a_compress
    finder.deleteLater()
    window.hide()
    window.current_tab().close_document()
    window.deleteLater()
