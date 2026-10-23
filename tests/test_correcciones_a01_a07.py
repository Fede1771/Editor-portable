"""Regresiones A01-A07: oráculos independientes sobre los documentos guardados."""
from io import BytesIO

import pymupdf as fitz
import pytest
from pypdf import PdfReader

from app import content_ops as content, forms, ocr, viewer


def document(pages=1):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=400, height=300).insert_text((30, 50), "AUDIT RECOGNITION TEST", fontsize=18)
    return doc


def field(doc, pno, name, value, kind=fitz.PDF_WIDGET_TYPE_TEXT):
    page = doc[pno]
    w = fitz.Widget()
    w.field_name, w.field_type, w.field_value = name, kind, value
    w.rect = fitz.Rect(30, 100, 240, 130)
    widget = page.add_widget(w)
    owner = int(doc.xref_get_key(widget.xref, "Parent")[1].split()[0])
    return widget.xref, owner


def written(doc):
    return doc.tobytes(garbage=4, deflate=True)


def raw_texts(raw):
    reader = PdfReader(BytesIO(raw))
    # Otro motor: recorrer todos los objetos indirectos, incluidos streams.
    result = []
    for entries in reader.xref.values():
        for xref in entries:
            if not xref:
                continue
            obj = reader.get_object(xref)
            result.append(str(obj))
            if hasattr(obj, "get_data"):
                result.append(obj.get_data().decode("utf-8", errors="replace"))
    return "\n".join(result)


@pytest.mark.parametrize("key,stream", [("RV", False), ("RV", True), ("RC", False), ("RC", True)])
def test_a01_rich_inline_words_and_paragraphs_leave_no_secret(key, stream):
    doc = document()
    page = doc[0]
    page.insert_text((30, 80), "SECRETO PRIVADO")
    if key == "RV":
        _, owner = field(doc, 0, "rich", "PUBLIC")
    else:
        owner = page.add_freetext_annot(fitz.Rect(30, 170, 240, 200), "PUBLIC").xref
    rich = '<body><p>SEC<span style="font-weight:bold">RETO</span></p><p>PRI<span>VADO</span></p></body>'
    if stream:
        ref = doc.get_new_xref()
        doc.update_object(ref, "<< >>")
        doc.update_stream(ref, rich.encode())
        doc.xref_set_key(owner, key, f"{ref} 0 R")
    else:
        doc.xref_set_key(owner, key, fitz.get_pdf_str(rich))
    assert content.redact_search_phrase(doc, "SECRETO PRIVADO") > 0
    raw = written(doc)
    doc.close()
    with fitz.open("pdf", raw) as reopened:
        assert not reopened[0].search_for("SECRETO PRIVADO")
    text = raw_texts(raw)
    assert "font-weight:bold" not in text
    assert "PRI<span>VADO" not in text


def hierarchy(depth=1):
    doc = document(2)
    _, name = field(doc, 0, "name", "SECRET_NAME")
    _, email = field(doc, 1, "email", "public@example.org")
    group = doc.get_new_xref()
    doc.update_object(group, f"<< /T (person) /Kids [{name} 0 R {email} 0 R] >>")
    for xref in (name, email):
        doc.xref_set_key(xref, "Parent", f"{group} 0 R")
    root = group
    for _ in range(depth - 1):
        root = doc.get_new_xref()
        doc.update_object(root, f"<< /T (outer) /Kids [{group} 0 R] >>")
        doc.xref_set_key(group, "Parent", f"{root} 0 R")
        group = root
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm/Fields", f"[{root} 0 R]")
    raw = written(doc)
    doc.close()
    return fitz.open("pdf", raw)


@pytest.mark.parametrize("depth", [1, 2])
@pytest.mark.parametrize("together", [False, True])
def test_a02_nested_terminal_fields_keep_distinct_canonical_values(depth, together):
    doc = hierarchy(depth)
    prefix = "outer." * (depth - 1) + "person."
    values = {prefix + "name": "NEW_NAME", prefix + "email": "NEW_EMAIL"}
    if together:
        forms.update_form_fields(doc, values)
    else:
        for name, value in values.items():
            forms.update_form_fields(doc, {name: value})
    raw = written(doc)
    doc.close()
    fields = PdfReader(BytesIO(raw)).get_fields()
    for name, value in values.items():
        assert fields[name]["/V"] == value
    assert "/V" not in fields[prefix[:-1]]
    with fitz.open("pdf", raw) as reopened:
        assert {w.field_name: w.field_value for p in reopened for w in p.widgets()} == values


def test_a02_redaction_preserves_unrelated_terminal_and_appearance():
    doc = hierarchy(2)
    page = doc[1]
    widget = next(page.widgets())
    before_ap = doc.xref_stream(int(doc.xref_get_key(widget.xref, "AP/N")[1].split()[0]))
    assert content.redact_search_phrase(doc, "SECRET_NAME", pages=[0]) == 1
    raw = written(doc)
    doc.close()
    fields = PdfReader(BytesIO(raw)).get_fields()
    assert fields["outer.person.email"]["/V"] == "public@example.org"
    with fitz.open("pdf", raw) as reopened:
        page = reopened[1]
        widget = next(page.widgets())
        assert widget.field_name == "outer.person.email"
        assert reopened.xref_stream(int(reopened.xref_get_key(widget.xref, "AP/N")[1].split()[0])) == before_ap
    assert "SECRET_NAME" not in raw_texts(raw)


def test_a03_no_match_in_selected_pages_is_noop():
    doc = document(2)
    widget, owner = field(doc, 1, "outside", "SECRET_OUTSIDE")
    before = {x: doc.xref_object(x) for x in (widget, owner)}
    assert content.redact_search_phrase(doc, "SECRET_OUTSIDE", pages=[0]) == 0
    assert {x: doc.xref_object(x) for x in before} == before
    raw = written(doc)
    doc.close()
    assert PdfReader(BytesIO(raw)).get_fields()["outside"]["/V"] == "SECRET_OUTSIDE"


def shared_field():
    doc = document(2)
    first, owner = field(doc, 0, "shared", "SHARED_SECRET")
    second = doc.get_new_xref()
    doc.update_object(second, f"<< /Type /Annot /Subtype /Widget /Parent {owner} 0 R /P {doc[1].xref} 0 R /Rect [30 170 240 200] >>")
    doc.xref_set_key(owner, "Kids", f"[{first} 0 R {second} 0 R]")
    doc.xref_set_key(doc[1].xref, "Annots", f"[{second} 0 R]")
    return doc


@pytest.mark.parametrize("manual", [False, True])
def test_a03_shared_terminal_outside_scope_rejected_before_mutation(manual):
    doc = shared_field()
    before = [doc.xref_object(x) for x in range(1, doc.xref_length())]
    with pytest.raises(ValueError, match="fuera del rango"):
        if manual:
            content.apply_redaction(doc, 0, fitz.Rect(30, 100, 240, 130))
        else:
            content.redact_search_phrase(doc, "SHARED_SECRET", pages=[0])
    assert [doc.xref_object(x) for x in range(1, doc.xref_length())] == before
    doc.close()


def test_a03_shared_terminal_all_pages_can_be_redacted():
    doc = shared_field()
    assert content.redact_search_phrase(doc, "SHARED_SECRET", pages=[0, 1]) >= 2
    raw = written(doc)
    doc.close()
    assert "SHARED_SECRET" not in raw_texts(raw)


@pytest.mark.parametrize("state", ["Accepted", "No", "1"])
def test_a04_custom_checkbox_states_survive_toggle_and_reopen(state):
    doc = document()
    xref, _ = field(doc, 0, "agree", "Off", fitz.PDF_WIDGET_TYPE_CHECKBOX)
    ap = doc.xref_get_key(xref, "AP/N")[1]
    doc.xref_set_key(xref, "AP/N", ap.replace("/Yes", "/" + state))
    for checked in (True, False, True):
        forms.update_form_fields(doc, {"agree": checked})
        raw = written(doc)
        doc.close()
        reader = PdfReader(BytesIO(raw))
        widget = reader.pages[0]["/Annots"][0].get_object()
        value = "/" + state if checked else "/Off"
        assert reader.get_fields()["agree"]["/V"] == value
        assert widget["/AS"] == value
        assert value in widget["/AP"]["/N"]
        doc = fitz.open("pdf", raw)
        assert forms.get_form_fields(doc)[0]["value"] == checked
    doc.close()


@pytest.mark.parametrize("dpi", [72, 150, 300])
def test_a05_real_ocr_preserves_physical_page_size(dpi):
    doc = document()
    result = ocr.ocr_document(doc, language="eng", dpi=dpi)
    try:
        assert result._editorpdf_ocr_report["recognized"] == [1]
        raw = written(result)
        with fitz.open("pdf", raw) as reopened:
            assert list(reopened[0].rect) == pytest.approx(list(doc[0].rect), abs=.01)
            assert "AUDIT" in reopened[0].get_text()
    finally:
        result.close()
        doc.close()


def raster_ocr(self, **kwargs):
    doc = fitz.open()
    page = doc.new_page(width=self.width * 72 / self.xres, height=self.height * 72 / self.yres)
    page.insert_image(page.rect, stream=self.tobytes("png"))
    page.insert_text((10, 20), "RECOGNIZED", render_mode=3)
    raw = doc.tobytes()
    doc.close()
    return raw


@pytest.mark.parametrize("rotation,userunit", [(0, 1), (90, 1), (180, 2), (270, 2)])
def test_a05_crop_rotation_userunit_preserved_with_bounded_raster(monkeypatch, rotation, userunit):
    doc = document()
    page = doc[0]
    page.draw_rect(fitz.Rect(45, 60, 100, 100), color=None, fill=(1, 0, 0))
    page.set_cropbox(fitz.Rect(20, 20, 380, 280))
    page.set_rotation(rotation)
    doc.xref_set_key(page.xref, "UserUnit", str(userunit))
    before = page.get_pixmap().samples
    real_render = viewer.render_bounded_pixmap
    monkeypatch.setattr(viewer, "render_bounded_pixmap", lambda p, **kw: real_render(p, max_pixels=180000, **kw))
    monkeypatch.setattr(fitz.Pixmap, "pdfocr_tobytes", raster_ocr)
    result = ocr.ocr_document(doc, language="eng", dpi=300)
    try:
        assert result._editorpdf_ocr_report["recognized"] == [1]
        with fitz.open("pdf", written(result)) as reopened:
            out = reopened[0]
            assert list(out.rect) == list(page.rect)
            assert list(out.mediabox) == list(page.mediabox)
            assert list(out.cropbox) == list(page.cropbox)
            assert out.rotation == rotation
            assert reopened.xref_get_key(out.xref, "UserUnit")[1] == str(userunit)
            after = out.get_pixmap().samples
            # Centro de masa del marcador rojo: detecta inversión, giro o desplazamiento.
            def center(data, width):
                red = [i // 3 for i in range(0, len(data), 3) if data[i] > 220 and data[i+1] < 30 and data[i+2] < 30]
                assert red
                return (sum(p % width for p in red)/len(red), sum(p // width for p in red)/len(red))
            assert center(after, out.get_pixmap().width) == pytest.approx(center(before, page.get_pixmap().width), abs=3)
    finally:
        result.close()
        doc.close()


def test_a06_ocr_preserves_incoming_links_external_bookmarks_and_destinations(monkeypatch):
    doc = document(2)
    doc[0].insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(20, 180, 160, 205), "page": 1, "to": fitz.Point(30, 50)})
    doc[1].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(20, 180, 160, 205), "uri": "https://example.org/link"})
    doc.set_toc([[1, "Internal", 2], [1, "Web", -1]])
    doc.set_toc_item(1, dest_dict={"kind": fitz.LINK_URI, "uri": "https://example.org/bookmark", "bold": True})
    monkeypatch.setattr(fitz.Pixmap, "pdfocr_tobytes", raster_ocr)
    result = ocr.ocr_document(doc, pages=[1], language="eng")
    try:
        with fitz.open("pdf", written(result)) as reopened:
            link = reopened[0].get_links()[0]
            assert link["page"] == 1 and list(link["to"]) == [30, 50]
            assert reopened[1].get_links()[0]["uri"] == "https://example.org/link"
            toc = reopened.get_toc(False)
            assert toc[0][3]["page"] == 1
            assert toc[1][3]["uri"] == "https://example.org/bookmark"
            assert toc[1][3]["bold"] is True
    finally:
        result.close()
        doc.close()


def test_a07_both_text_edit_rasters_are_bounded_before_allocation(monkeypatch):
    doc = fitz.open()
    page = doc.new_page(width=20000, height=20000)
    page.insert_text((100, 12000), "A", fontsize=10000)
    real = fitz.Page.get_pixmap
    calls = []
    def bounded_only(p, *args, **kwargs):
        clip = kwargs.get("clip", p.rect) & p.rect
        matrix = fitz.Matrix(kwargs["dpi"] / 72, kwargs["dpi"] / 72) if "dpi" in kwargs else kwargs.get("matrix", fitz.Matrix(1, 1))
        rect = (clip * matrix).irect
        assert rect.width * rect.height <= content.MAX_SAMPLE_PIXELS
        calls.append((rect.width, rect.height))
        return real(p, *args, **kwargs)
    monkeypatch.setattr(fitz.Page, "get_pixmap", bounded_only)
    result = content.find_text_block_at(page, fitz.Point(3000, 7000))
    assert result and len(calls) == 2
    doc.close()


def test_a01_utf16_stream_and_inspection_failure_are_not_ignored(monkeypatch):
    doc = document()
    _, owner = field(doc, 0, "rich", "PUBLIC")
    ref = doc.get_new_xref()
    doc.update_object(ref, "<< >>")
    doc.update_stream(ref, '<body><p>SECRET_UTF16</p></body>'.encode("utf-16-be"))
    doc.xref_set_key(owner, "RV", f"{ref} 0 R")
    real_stream = doc.xref_stream
    monkeypatch.setattr(doc, "xref_stream", lambda x: (_ for _ in ()).throw(RuntimeError("inspection failed")) if x == ref else real_stream(x))
    with pytest.raises(RuntimeError, match="inspection failed"):
        content.redact_search_phrase(doc, "SECRET_UTF16")
    assert doc.xref_get_key(owner, "V")[1] == "PUBLIC"
    monkeypatch.undo()
    assert content.redact_search_phrase(doc, "SECRET_UTF16") > 0
    assert "SECRET_UTF16" not in raw_texts(written(doc))
    doc.close()


def test_a05_exported_png_carries_requested_resolution(tmp_path):
    from app.conversion import convert_to_images
    doc = document()
    path = convert_to_images(doc, str(tmp_path), dpi=150)[0]
    pix = fitz.Pixmap(path)
    assert (pix.xres, pix.yres) == (150, 150)
    with fitz.open(path) as image:
        assert image[0].rect.width == pytest.approx(doc[0].rect.width, abs=.5)
        assert image[0].rect.height == pytest.approx(doc[0].rect.height, abs=.5)
    doc.close()


def test_a05_render_budget_declares_effective_resolution():
    doc = document()
    pix = viewer.render_bounded_pixmap(doc[0], dpi=300, max_pixels=100000)
    assert pix.width * pix.height <= 100000
    assert pix.xres < 300
    assert pix.xres == pytest.approx(pix.width * 72 / doc[0].rect.width, abs=1)
    assert pix.yres == pytest.approx(pix.height * 72 / doc[0].rect.height, abs=1)
    doc.close()


@pytest.mark.parametrize("clip", [
    fitz.Rect(12093.6476, 847.5863, 12113.2056, 31253.1084),
    fitz.Rect(68605.4451, 3.1039, 68607.6137, 67726.3065),
])
def test_a07_thin_offset_clips_include_pixel_rounding_in_budget(clip, monkeypatch):
    doc = fitz.open()
    page = doc.new_page(width=100000, height=100000)
    real = fitz.Page.get_pixmap
    def guarded(p, *args, **kwargs):
        bounds = (clip * kwargs["matrix"]).irect
        assert bounds.width * bounds.height <= content.MAX_SAMPLE_PIXELS
        return real(p, *args, **kwargs)
    monkeypatch.setattr(fitz.Page, "get_pixmap", guarded)
    pix = viewer.render_bounded_pixmap(page, clip=clip, dpi=150, max_pixels=content.MAX_SAMPLE_PIXELS)
    assert pix.width * pix.height <= content.MAX_SAMPLE_PIXELS
    doc.close()
