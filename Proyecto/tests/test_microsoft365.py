"""Integración Office: rutas, atomicidad, datos en vivo y límites de proceso."""
from pathlib import Path
from contextlib import contextmanager
import time

import pymupdf as fitz
import pytest

from app import conversion, creation, office365


def _stuck_worker(conn, *args):
    time.sleep(20)


@pytest.mark.parametrize("extension,operation", [("docx", "word_pdf"), ("xlsx", "excel_pdf"), ("pptx", "powerpoint_pdf")])
def test_m365_office_to_pdf_routes_native_application(tmp_path, monkeypatch, extension, operation):
    source = tmp_path / ("original." + extension)
    source.write_bytes(b"UNCHANGED")
    def export(kind, input_path, output_path, **kwargs):
        assert kind == operation and input_path == str(source)
        with fitz.open() as doc:
            doc.new_page().insert_text((30, 50), "NATIVE_OFFICE")
            doc.save(output_path)
    monkeypatch.setattr(office365, "run_office", export)
    out = creation.office_to_pdf_file(str(source), str(tmp_path / "out"))
    assert source.read_bytes() == b"UNCHANGED"
    with fitz.open(out) as doc:
        assert "NATIVE_OFFICE" in doc[0].get_text()


def test_m365_failed_office_export_keeps_previous_pdf(tmp_path, monkeypatch):
    source = tmp_path / "original.docx"
    source.write_bytes(b"UNCHANGED")
    output = tmp_path / "original.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((30, 50), "OLD_VALID_PDF")
        doc.save(output)
    before = output.read_bytes()
    def invalid(*args, **kwargs):
        Path(args[2]).write_bytes(b"CORRUPT")
    monkeypatch.setattr(office365, "run_office", invalid)
    with pytest.raises(Exception):
        creation.office_to_pdf_file(str(source), str(tmp_path))
    assert output.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp.pdf"))


def test_m365_timeout_terminates_only_worker(tmp_path, monkeypatch):
    source = tmp_path / "input.docx"
    source.write_bytes(b"DUMMY")
    monkeypatch.setattr(office365, "_office_process", _stuck_worker)
    before = time.monotonic()
    with pytest.raises(office365.OfficeConversionError, match="no completó"):
        # Probar el timeout del trabajador sin competir con conversiones reales
        # por el mutex global de Word (el mutex tiene su propia regresión).
        office365._run_office("word_pdf", str(source), str(tmp_path / "out.pdf"), timeout=.2)
    assert time.monotonic() - before < 8


def test_m365_cleanup_rejects_reused_pid(monkeypatch):
    class Unrelated:
        def create_time(self):
            return 99
        def name(self):
            return "WINWORD.EXE"
        def kill(self):
            pytest.fail("No terminar un PID reutilizado")
    monkeypatch.setattr(office365.psutil, "Process", lambda pid: Unrelated())
    office365._stop_owned({"pid": 123, "created": 1, "name": "winword.exe"})


def test_m365_existing_powerpoint_is_not_opened_or_closed(monkeypatch):
    import win32com.client
    class Existing:
        pid = 123
        info = {"name": "POWERPNT.EXE"}
    monkeypatch.setattr(office365.psutil, "process_iter", lambda *args: [Existing()])
    def unexpected(*args):
        pytest.fail("No conectar a PowerPoint del usuario")
    monkeypatch.setattr(win32com.client, "DispatchEx", unexpected)
    with pytest.raises(office365.OfficeConversionError, match="PowerPoint está abierto"):
        with office365._application("PowerPoint", None):
            pytest.fail("No abrir ni modificar una presentación del usuario")


def test_m365_parallel_jobs_cannot_share_application_lock():
    from concurrent.futures import ThreadPoolExecutor
    import uuid
    name = "Test_" + uuid.uuid4().hex
    def second():
        with pytest.raises(office365.OfficeConversionError, match="Otra conversión"):
            with office365._office_lock(name, .05):
                pytest.fail("Dos trabajos no deben adquirir el mismo bloqueo")
    with office365._office_lock(name, 1):
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(second).result(timeout=3)


def test_word_documents_falls_back_to_same_dispatch_without_creating_word(monkeypatch):
    import pythoncom
    import win32com.client
    collection = object()
    raw_collection = object()
    class Raw:
        def GetIDsOfNames(self, locale, name):
            assert (locale, name) == (0, "Documents")
            return 6
        def Invoke(self, dispid, locale, kind, result):
            assert (dispid, locale, kind, result) == (6, 0, pythoncom.DISPATCH_PROPERTYGET, True)
            return raw_collection
    class Word:
        _oleobj_ = Raw()
        @property
        def Documents(self):
            raise AttributeError("Word.Application.Documents")
    def wrap(value, name):
        assert value is raw_collection
        return collection
    monkeypatch.setattr(win32com.client, "Dispatch", wrap)
    monkeypatch.setattr(win32com.client, "DispatchEx", lambda *a: pytest.fail("No iniciar otra sesión"))
    assert office365._word_documents(Word()) is collection


def test_word_documents_falls_back_on_ole_registry_access_error(monkeypatch):
    import pythoncom
    import win32com.client
    collection = object()
    raw_collection = object()
    class Raw:
        def GetIDsOfNames(self, locale, name):
            assert (locale, name) == (0, "Documents")
            return 6
        def Invoke(self, dispid, locale, kind, result):
            assert (dispid, locale, kind, result) == (6, 0, pythoncom.DISPATCH_PROPERTYGET, True)
            return raw_collection
    class Word:
        _oleobj_ = Raw()
        @property
        def Documents(self):
            raise pythoncom.com_error(-2147319780, "Error al tener acceso al Registro OLE.", None, None)
    def wrap(value, name):
        assert value is raw_collection
        return collection
    monkeypatch.setattr(win32com.client, "Dispatch", wrap)
    monkeypatch.setattr(win32com.client, "DispatchEx", lambda *a: pytest.fail("No iniciar otra sesión"))
    assert office365._word_documents(Word()) is collection


def test_word_documents_falls_back_to_pure_cdispatch_when_dispatch_wrap_fails_registry(monkeypatch):
    import pythoncom
    import win32com.client
    import win32com.client.dynamic
    raw_collection = object()
    class Raw:
        def GetIDsOfNames(self, locale, name):
            return 6
        def Invoke(self, dispid, locale, kind, result):
            return raw_collection
    class Word:
        _oleobj_ = Raw()
        @property
        def Documents(self):
            raise pythoncom.com_error(-2147319780, "Error al tener acceso al Registro OLE.", None, None)
    def failing_wrap(value, name):
        raise pythoncom.com_error(-2147319780, "Error al tener acceso al Registro OLE.", None, None)
    monkeypatch.setattr(win32com.client, "Dispatch", failing_wrap)
    wrapped = office365._word_documents(Word())
    assert isinstance(wrapped, win32com.client.dynamic.CDispatch)
    assert wrapped._oleobj_ is raw_collection


def test_word_documents_retries_busy_startup_but_not_access_denied(monkeypatch):
    import pythoncom
    collection = object()
    class StartingWord:
        attempts = 0
        @property
        def Documents(self):
            self.attempts += 1
            if self.attempts < 3:
                raise pythoncom.com_error(-2147418111, "Call rejected", None, None)
            return collection
    monkeypatch.setattr(office365.time, "sleep", lambda seconds: None)
    word = StartingWord()
    assert office365._word_documents(word) is collection
    assert word.attempts == 3
    class RestrictedWord:
        @property
        def Documents(self):
            raise pythoncom.com_error(-2147024891, "Access denied", None, None)
    with pytest.raises(pythoncom.com_error) as error:
        office365._word_documents(RestrictedWord())
    assert error.value.hresult == -2147024891


def test_word_documents_busy_retry_is_bounded(monkeypatch):
    import pythoncom
    class Word:
        attempts = 0
        @property
        def Documents(self):
            self.attempts += 1
            raise pythoncom.com_error(-2147417846, "Retry later", None, None)
    monkeypatch.setattr(office365.time, "sleep", lambda seconds: None)
    word = Word()
    with pytest.raises(pythoncom.com_error):
        office365._word_documents(word)
    assert word.attempts == 8


def test_word_export_preserves_read_only_and_progress(tmp_path):
    source, target = str(tmp_path / "input.docx"), str(tmp_path / "output.pdf")
    stages = []
    class Document:
        def ExportAsFixedFormat(self, path, format_id, **options):
            assert (path, format_id, options) == (target, 17, {"OpenAfterExport": False})
    class Documents:
        def Open(self, path, **options):
            assert path == source
            assert options["ReadOnly"] is True
            assert options["AddToRecentFiles"] is False
            assert options["Visible"] is False
            return Document()
    documents = Documents()
    class Word:
        Documents = documents
    class Connection:
        def send(self, packet):
            stages.append(packet)
    office365._perform(Word(), "word_pdf", source, target, False, Connection())
    assert stages[-1] == ("stage", "exportar Word a PDF")


def test_office_cleanup_timeout_does_not_replace_conversion_error(monkeypatch):
    class StubbornOwnedProcess:
        killed = False
        def create_time(self):
            return 1
        def name(self):
            return "WINWORD.EXE"
        def wait(self, timeout):
            raise office365.psutil.TimeoutExpired(timeout, 123)
        def kill(self):
            self.killed = True
    process = StubbornOwnedProcess()
    monkeypatch.setattr(office365.psutil, "Process", lambda pid: process)
    with pytest.raises(office365.OfficeConversionError, match="error original"):
        try:
            raise office365.OfficeConversionError("error original")
        finally:
            office365._stop_owned({"pid": 123, "created": 1, "name": "winword.exe"})
    assert process.killed


def test_office_worker_reports_documents_error_with_stage(monkeypatch):
    packets = []
    class Connection:
        def send(self, packet):
            packets.append(packet)
        def close(self):
            pass
    @contextmanager
    def unavailable(name, conn):
        office365._stage(conn, "acceder a los documentos de Word")
        raise AttributeError("Word.Application.Documents")
        yield
    monkeypatch.setattr(office365, "_application", unavailable)
    office365._office_process(Connection(), "word_pdf", "a.docx", "a.pdf", False)
    kind, message = packets[-1]
    assert kind == "error"
    assert "Word.Application.Documents" in message
    assert "acceder a los documentos" in message
    assert "Registro OLE/COM" in message


def test_office_error_message_reports_ole_registry_access_hint():
    import pythoncom
    err = pythoncom.com_error(-2147319780, "Error al tener acceso al Registro OLE.", None, None)
    msg = office365._error_message("Word", err, "acceder a los documentos de Word")
    assert "Registro OLE/COM" in msg
    assert "Administrador" in msg
    assert "Reparación Rápida" in msg
    assert "-2147319780" in msg


def test_office_diagnostic_checks_pdf_text_and_preserves_source(tmp_path, monkeypatch):
    import json
    import zipfile
    from app.diagnostics import office_self_test
    def export(source, folder):
        with zipfile.ZipFile(source) as package:
            assert b"WORD_PDF_RUNTIME_CHECK" in package.read("word/document.xml")
            assert len(package.namelist()) == 3
        output = str(Path(folder) / "result.pdf")
        with fitz.open() as pdf:
            pdf.new_page().insert_text((30, 50), "WORD_PDF_RUNTIME_CHECK")
            pdf.save(output)
        return output
    monkeypatch.setattr(creation, "office_to_pdf_file", export)
    assert office_self_test(str(tmp_path)) == 0
    result = json.loads((tmp_path / "office_self_test_result.json").read_text(encoding="utf-8"))
    assert result["ok"] and result["checks"] == {"word_pdf": True}


def test_office_diagnostic_reports_original_error(tmp_path, monkeypatch):
    import json
    from app.diagnostics import office_self_test
    def fail(*args):
        raise office365.OfficeConversionError("Word.Application.Documents")
    monkeypatch.setattr(creation, "office_to_pdf_file", fail)
    assert office_self_test(str(tmp_path)) == 1
    result = json.loads((tmp_path / "office_self_test_result.json").read_text(encoding="utf-8"))
    assert result["ok"] is False
    assert "Word.Application.Documents" in result["error"]
