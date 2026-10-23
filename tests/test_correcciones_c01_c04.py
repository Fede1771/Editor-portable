"""Regresiones de C01-C04: apariencias alternativas/compartidas, acciones tipadas y radios."""
from io import BytesIO

import pymupdf as fitz
import pytest
from pypdf import PdfReader
from pypdf.generic import NameObject

from app import content_ops, forms, security
from app.dialogs import FillFormsDialog


def document(pages=1):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=400, height=300).insert_text((30, 50), "PUBLIC DOCUMENT")
    return doc


def field(doc, pno, name, value, kind=fitz.PDF_WIDGET_TYPE_TEXT):
    page = doc[pno]
    w = fitz.Widget()
    w.field_name, w.field_value, w.field_type = name, value, kind
    w.rect = fitz.Rect(30, 120, 300, 155)
    xref = page.add_widget(w).xref
    return xref, int(doc.xref_get_key(xref, "Parent")[1].split()[0])


def persisted(doc):
    return doc.tobytes(garbage=4, deflate=True)


def all_streams(raw):
    reader = PdfReader(BytesIO(raw))
    for entries in reader.xref.values():
        for number in entries:
            if number:
                obj = reader.get_object(number)
                if hasattr(obj, "get_data"):
                    yield obj.get_data()


@pytest.mark.parametrize("branch", ["R", "D"])
@pytest.mark.parametrize("states", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_c01_all_alternate_states_and_nested_encoded_forms_are_redacted(branch, states, nested):
    doc = document()
    doc[0].insert_text((30, 80), "SECRET_AP")
    widget, _ = field(doc, 0, "display", "PUBLIC")
    normal = int(doc.xref_get_key(widget, "AP/N")[1].split()[0])
    alternate = doc.get_new_xref()
    doc.update_object(alternate, doc.xref_object(normal))
    # Hex text: no literal SECRET_AP bytes for an unsafe raw substring scan.
    encoded = b"<" + b"SECRET_AP".hex().encode() + b">"
    data = doc.xref_stream(normal).replace(b"(PUBLIC)", encoded)
    doc.update_stream(alternate, data)
    if nested:
        outer = doc.get_new_xref()
        doc.update_object(outer, f"<< /Type /XObject /Subtype /Form /BBox [0 0 270 35] /Resources << /XObject << /Inner {alternate} 0 R >> >> >>")
        doc.update_stream(outer, b"q /Inner Do Q")
        alternate = outer
    value = f"<< /Idle {normal} 0 R /Reveal {alternate} 0 R >>" if states else f"{alternate} 0 R"
    doc.xref_set_key(widget, "AP/" + branch, value)
    if states:
        doc.xref_set_key(widget, "AS", "/Idle")
    raw = persisted(doc)
    doc.close()
    doc = fitz.open("pdf", raw)
    assert content_ops.redact_search_phrase(doc, "SECRET_AP") >= 2
    raw = persisted(doc)
    doc.close()
    assert "display" not in (PdfReader(BytesIO(raw)).get_fields() or {})
    assert all(b"SECRET_AP" not in s and b"5345435245545f4150" not in s for s in all_streams(raw))


def test_c01_invalid_alternate_form_rejects_before_mutation():
    doc = document()
    widget, owner = field(doc, 0, "display", "PUBLIC")
    stream = doc.get_new_xref()
    doc.update_object(stream, "<< >>")
    doc.update_stream(stream, b"(SECRET_AP) Tj")
    doc.xref_set_key(widget, "AP/R", f"{stream} 0 R")
    before = [doc.xref_object(x) for x in range(1, doc.xref_length())]
    with pytest.raises(ValueError, match="Form/BBox"):
        content_ops.redact_search_phrase(doc, "SECRET_AP")
    assert before == [doc.xref_object(x) for x in range(1, doc.xref_length())]
    assert doc.xref_get_key(owner, "V")[1] == "PUBLIC"
    doc.close()


def test_c01_alternate_annotation_appearance_is_removed():
    doc = document()
    page = doc[0]
    annot = page.add_freetext_annot(fitz.Rect(30, 120, 300, 155), "PUBLIC")
    normal = int(doc.xref_get_key(annot.xref, "AP/N")[1].split()[0])
    alternate = doc.get_new_xref()
    doc.update_object(alternate, doc.xref_object(normal))
    doc.update_stream(alternate, doc.xref_stream(normal).replace(b"PUBLIC", b"SECRET_AP"))
    doc.xref_set_key(annot.xref, "AP/R", f"{alternate} 0 R")
    assert content_ops.redact_search_phrase(doc, "SECRET_AP") == 1
    raw = persisted(doc)
    assert not PdfReader(BytesIO(raw)).pages[0].get("/Annots")
    assert all(b"SECRET_AP" not in stream for stream in all_streams(raw))
    doc.close()


def test_c01_nested_form_can_use_containing_page_resources():
    doc = document()
    widget, _ = field(doc, 0, "display", "PUBLIC")
    normal = int(doc.xref_get_key(widget, "AP/N")[1].split()[0])
    inner, outer = doc.get_new_xref(), doc.get_new_xref()
    doc.update_object(inner, doc.xref_object(normal))
    doc.update_stream(inner, doc.xref_stream(normal).replace(b"PUBLIC", b"SECRET_AP"))
    doc.xref_set_key(doc[0].xref, "Resources", doc.xref_get_key(normal, "Resources")[1])
    doc.xref_set_key(doc[0].xref, "Resources/XObject", f"<< /Inner {inner} 0 R >>")
    doc.xref_set_key(inner, "Resources", "null")
    doc.update_object(outer, "<< /Type /XObject /Subtype /Form /BBox [0 0 270 35] >>")
    doc.update_stream(outer, b"q /Inner Do Q")
    doc.xref_set_key(widget, "AP/R", f"{outer} 0 R")
    assert content_ops.redact_search_phrase(doc, "SECRET_AP") == 1
    assert "display" not in (PdfReader(BytesIO(persisted(doc))).get_fields() or {})
    doc.close()


def test_c02_replace_rejects_field_shared_with_excluded_page_before_mutation():
    doc = radio()
    before = [doc.xref_object(x) for x in range(1, doc.xref_length())]
    with pytest.raises(ValueError, match="fuera del rango"):
        content_ops.replace_text_block(doc, 0, fitz.Rect(30, 120, 300, 155), "UPDATED")
    assert before == [doc.xref_object(x) for x in range(1, doc.xref_length())]
    doc.close()


@pytest.mark.parametrize("operation", ["search", "rectangle", "replace"])
def test_c02_preserve_appearance_shared_with_unrelated_field(operation):
    doc = document(2)
    _, owner = field(doc, 0, "private", "PUBLIC")
    field(doc, 1, "unrelated", "PUBLIC")
    doc.xref_set_key(owner, "RV", fitz.get_pdf_str("<p>SECRET_SHARED_AP</p>"))
    raw = persisted(doc)  # Deduplicar los streams idénticos antes de la operación.
    doc.close()
    doc = fitz.open("pdf", raw)
    pages = [doc[0], doc[1]]
    refs = [doc.xref_get_key(next(p.widgets()).xref, "AP/N")[1] for p in pages]
    assert refs[0] == refs[1]
    before = doc.xref_stream(int(refs[0].split()[0]))
    if operation == "rectangle":
        content_ops.apply_redaction(doc, 0, fitz.Rect(30, 120, 300, 155))
    elif operation == "replace":
        content_ops.replace_text_block(doc, 0, fitz.Rect(30, 120, 300, 155), "UPDATED")
    else:
        assert content_ops.redact_search_phrase(doc, "SECRET_SHARED_AP", pages=[0]) == 1
    raw = persisted(doc)
    doc.close()
    reader = PdfReader(BytesIO(raw))
    normal = reader.pages[1]["/Annots"][0].get_object()["/AP"]["/N"].get_object()
    assert normal.get_data() == before
    assert "/BBox" in normal and normal["/Subtype"] == "/Form"
    assert reader.get_fields()["unrelated"]["/V"] == "PUBLIC"
    with fitz.open("pdf", raw) as reopened:
        assert "PUBLIC" in reopened[1].get_text()


@pytest.mark.parametrize("destination", ["array", "action"])
@pytest.mark.parametrize("indirect", [False, True])
def test_c03_open_destination_does_not_traverse_page_links(tmp_path, destination, indirect):
    doc = document()
    doc[0].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(30, 90, 230, 110), "uri": "https://example.org/kept"})
    raw = persisted(doc)
    doc.close()
    doc = fitz.open("pdf", raw)
    page = doc[0]
    link = page.get_links()[0]
    if indirect:
        action = doc.get_new_xref()
        doc.update_object(action, doc.xref_get_key(link["xref"], "A")[1])
        doc.xref_set_key(link["xref"], "A", f"{action} 0 R")
    dest = f"[{page.xref} 0 R /Fit]"
    if destination == "action":
        dest = f"<< /S /GoTo /D {dest} >>"
    doc.xref_set_key(doc.pdf_catalog(), "OpenAction", dest)
    path = tmp_path / "safe.pdf"
    security.create_sanitized_copy(doc, str(path))
    doc.close()
    with fitz.open(path) as reopened:
        assert reopened[0].get_links()[0]["uri"] == "https://example.org/kept"
        assert reopened.xref_get_key(reopened.pdf_catalog(), "OpenAction")[0] == "null"
        assert not security.scan_document_security(reopened)["has_threats"]


def test_c03_safe_continuation_shared_with_normal_link_is_preserved(tmp_path):
    doc = document()
    doc[0].insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(30, 90, 230, 110), "uri": "https://example.org/shared"})
    raw = persisted(doc)
    doc.close()
    doc = fitz.open("pdf", raw)
    page = doc[0]
    link = page.get_links()[0]
    safe = doc.get_new_xref()
    doc.update_object(safe, doc.xref_get_key(link["xref"], "A")[1])
    doc.xref_set_key(link["xref"], "A", f"{safe} 0 R")
    doc.xref_set_key(doc.pdf_catalog(), "OpenAction", f"<< /S /JavaScript /JS (INERT_TEST) /Next {safe} 0 R >>")
    path = tmp_path / "shared.pdf"
    security.create_sanitized_copy(doc, str(path))
    doc.close()
    with fitz.open(path) as reopened:
        assert reopened[0].get_links()[0]["uri"] == "https://example.org/shared"
        assert not security.scan_document_security(reopened)["has_js"]


def test_c03_javascript_nametree_kids_cleaned_without_attachment_loss(tmp_path):
    doc = document()
    doc.embfile_add("public.txt", b"KEPT_ATTACHMENT")
    action, child, root = [doc.get_new_xref() for _ in range(3)]
    doc.update_object(action, "<< /S /JavaScript /JS (INERT_NAMETREE) >>")
    doc.update_object(child, f"<< /Names [(test) {action} 0 R] >>")
    doc.update_object(root, f"<< /Kids [{child} 0 R] >>")
    doc.xref_set_key(doc.pdf_catalog(), "Names/JavaScript", f"{root} 0 R")
    path = tmp_path / "names.pdf"
    security.create_sanitized_copy(doc, str(path))
    doc.close()
    with fitz.open(path) as reopened:
        assert reopened.embfile_get("public.txt") == b"KEPT_ATTACHMENT"
        assert not security.scan_document_security(reopened)["has_js"]
    assert b"INERT_NAMETREE" not in path.read_bytes()


def radio(states=("Yes", "Other"), flags=0, labels=None):
    doc = document(2)
    first, owner = field(doc, 0, "choice", "Off", fitz.PDF_WIDGET_TYPE_CHECKBOX)
    second, _ = field(doc, 1, "other", "Off", fitz.PDF_WIDGET_TYPE_CHECKBOX)
    for xref, state in zip((first, second), states):
        doc.xref_set_key(xref, "AP/N", doc.xref_get_key(xref, "AP/N")[1].replace("/Yes", "/" + state))
    doc.xref_set_key(owner, "Ff", str(32768 | flags))
    doc.xref_set_key(owner, "Kids", f"[{first} 0 R {second} 0 R]")
    doc.xref_set_key(second, "Parent", f"{owner} 0 R")
    if labels:
        doc.xref_set_key(owner, "Opt", "[" + " ".join(fitz.get_pdf_str(s) for s in labels) + "]")
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm/Fields", f"[{owner} 0 R]")
    raw = persisted(doc)
    doc.close()
    return fitz.open("pdf", raw)


def assert_radio(raw, value, appearances):
    reader = PdfReader(BytesIO(raw))
    actual = reader.get_fields()["choice"]["/V"]
    assert isinstance(actual, NameObject) and actual == "/" + value
    for page, expected in zip(reader.pages, appearances):
        annot = page["/Annots"][0].get_object()
        assert annot["/AS"] == "/" + expected
        assert annot["/AS"] in annot["/AP"]["/N"]


def test_c04_radio_values_are_names_and_exclusive_after_reopening():
    doc = radio()
    for state, appearances in [("Yes", ["Yes", "Off"]), ("Other", ["Off", "Other"]), ("Off", ["Off", "Off"])]:
        assert forms.update_form_fields(doc, {"choice": state}) == 2
        raw = persisted(doc)
        doc.close()
        assert_radio(raw, state, appearances)
        doc = fitz.open("pdf", raw)
        assert forms.get_form_fields(doc)[0]["value"] == state
    doc.close()


def test_c04_duplicate_on_names_select_one_widget_without_unison():
    doc = radio(states=("Yes", "Yes"))
    choices = forms.get_form_fields(doc)[0]["choices"]
    tokens = [c for c in choices if c != "Off"]
    assert len(set(tokens)) == 2
    for token, appearances in zip(tokens, [["Yes", "Off"], ["Off", "Yes"]]):
        forms.update_form_fields(doc, {"choice": token})
        assert_radio(persisted(doc), "Yes", appearances)
        assert forms.get_form_fields(doc)[0]["value"] == token
    with pytest.raises(ValueError, match="ambigua"):
        forms.update_form_fields(doc, {"choice": "Yes"})
    doc.close()


def test_c04_radios_in_unison_select_all_matching_states():
    doc = radio(states=("Yes", "Yes"), flags=1 << 25)
    forms.update_form_fields(doc, {"choice": "Yes"})
    assert_radio(persisted(doc), "Yes", ["Yes", "Yes"])
    doc.close()


def test_c04_no_toggle_to_off_rejected_and_rolled_back():
    doc = radio(flags=1 << 14)
    forms.update_form_fields(doc, {"choice": "Yes"})
    with pytest.raises(ValueError, match="NoToggleToOff"):
        forms.update_form_fields(doc, {"choice": "Off"})
    assert_radio(persisted(doc), "Yes", ["Yes", "Off"])
    doc.close()


def test_c04_opt_exports_have_labels_but_values_remain_names():
    doc = radio(states=("0", "1"), labels=("Export A", "Export B"))
    fields = forms.get_form_fields(doc)
    assert fields[0]["choices"] == ["Off", "0", "1"]
    assert fields[0]["choice_labels"] == ["Sin selección", "Export A", "Export B"]
    forms.update_form_fields(doc, {"choice": "1"})
    assert_radio(persisted(doc), "1", ["Off", "1"])
    doc.close()


def test_c04_dialog_uses_options_and_synchronizes_shared_radio(qapp):
    doc = radio()
    dialog = FillFormsDialog(forms.get_form_fields(doc))
    assert dialog.values() == {"choice": "Off"}
    for kind, combo in dialog.widgets_group["choice"]:
        assert kind == "choice" and not combo.isEditable()
    first = dialog.widgets_group["choice"][0][1]
    first.setCurrentIndex(first.findData("Other"))
    assert dialog.values() == {"choice": "Other"}
    assert all(combo.currentData() == "Other" for _, combo in dialog.widgets_group["choice"])
    dialog.deleteLater()
    doc.close()
