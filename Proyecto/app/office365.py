"""Conversión local mediante Microsoft 365 de escritorio, en procesos aislados."""
from __future__ import annotations

from contextlib import contextmanager, suppress
import gc
import math
import multiprocessing
import os
from pathlib import Path
import time

import psutil


class OfficeConversionError(RuntimeError):
    """Office ausente, ocupado o conversión incompleta sin publicar su salida."""


_APPS = {"word_pdf": "Word", "excel_pdf": "Excel", "powerpoint_pdf": "PowerPoint"}


@contextmanager
def _office_lock(name, timeout):
    """Serializar trabajos de cada aplicación entre instancias del editor."""
    import win32api
    import win32event
    mutex = win32event.CreateMutex(None, False, "Local\\EditorPDFPortable.Office365." + name)
    locked = False
    try:
        state = win32event.WaitForSingleObject(mutex, min(int(timeout * 1000), 0xFFFFFFFE))
        if state not in (0, 0x80):
            raise OfficeConversionError(f"Otra conversión está usando {name}. Reintentá cuando termine.")
        locked = True
        yield
    finally:
        if locked:
            win32event.ReleaseMutex(mutex)
        win32api.CloseHandle(mutex)


def run_office(operation: str, source: str, target: str, timeout: float = 240):
    """Serializar por aplicación y ejecutar COM con un límite de tiempo."""
    if operation not in _APPS:
        raise ValueError("Operación de Microsoft 365 desconocida.")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("El tiempo máximo de conversión debe ser positivo y finito.")
    if os.name != "nt":
        raise OfficeConversionError("Esta conversión requiere Microsoft 365 de escritorio para Windows.")
    with _office_lock(_APPS[operation], timeout):
        return _run_office(operation, source, target, timeout)


def _stop_owned(identity):
    """Nunca finalizar por nombre: validar PID, creación e identidad registrados."""
    if not identity:
        return
    try:
        process = psutil.Process(identity["pid"])
        if (abs(process.create_time() - identity["created"]) > 0.01
                or process.name().lower() != identity["name"]):
            return
        try:
            process.wait(timeout=2)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def _run_office(operation: str, source: str, target: str, timeout: float = 240):
    """Sólo rutas y resultados simples cruzan el límite de proceso COM."""
    source, target = str(Path(source).resolve()), str(Path(target).resolve())
    if not Path(source).is_file() or source == target:
        raise ValueError("El archivo de entrada debe existir y ser distinto de la salida.")
    from .privacy import is_private_mode
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_office_process,
                              args=(send, operation, source, target, is_private_mode()))
    owned = None
    packet = None
    try:
        process.start()
        send.close()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if receive.poll(min(0.1, max(0, deadline - time.monotonic()))):
                try:
                    kind, value = receive.recv()
                except EOFError:
                    break
                if kind == "owned":
                    owned = value
                else:
                    packet = kind, value
                    break
            if not process.is_alive() and not receive.poll():
                break
        if packet is None:
            raise OfficeConversionError(
                f"{_APPS[operation]} no completó la conversión. Puede haber un aviso, "
                "un archivo protegido o un bloqueo de Office. Revisá la instalación y reintentá."
            )
        if packet[0] == "error":
            raise OfficeConversionError(packet[1])
        return packet[1]
    finally:
        if process.pid is not None:
            process.join(timeout=3)
            if process.is_alive():
                process.terminate()
                process.join(timeout=3)
            _stop_owned(owned)
            process.close()
        receive.close()
        send.close()

@contextmanager
def _application(name, conn):
    import pythoncom
    import win32com.client
    import win32process
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    app = None
    owned = False
    options = {}
    word_options = {}
    try:
        processes = list(psutil.process_iter(["name"]))
        before = {p.pid for p in processes}
        if name == "PowerPoint" and any((p.info["name"] or "").lower() == "powerpnt.exe" for p in processes):
            raise OfficeConversionError("PowerPoint está abierto. Cerralo antes de convertir para proteger sus presentaciones.")
        app = win32com.client.DispatchEx(name + ".Application")
        if name == "PowerPoint":
            # PowerPoint es MultiUse y una sesión sin ventanas no publica HWND.
            candidates = [p for p in psutil.process_iter(["name"]) if p.pid not in before
                          and (p.info["name"] or "").lower() == "powerpnt.exe"]
            if len(candidates) != 1 or app.Presentations.Count or bool(app.Visible):
                raise OfficeConversionError("No se pudo aislar una instancia de PowerPoint sin presentaciones del usuario.")
            pid = candidates[0].pid
        elif name == "Word":
            blank = app.Documents.Add(Visible=False)
            hwnd = blank.Windows(1).Hwnd
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            blank.Close(0)
            blank = None
        else:
            _, pid = win32process.GetWindowThreadProcessId(app.Hwnd)
        if pid in before:
            raise OfficeConversionError(
                f"{name} está abierto en una instancia compartida. Cerrá esa aplicación "
                "antes de convertir; no se modificaron sus documentos."
            )
        owned = True
        p = psutil.Process(pid)
        conn.send(("owned", {"pid": pid, "created": p.create_time(), "name": p.name().lower()}))
        for key, value in {"AutomationSecurity": 3, "DisplayAlerts": 0 if name == "Word" else (1 if name == "PowerPoint" else False)}.items():
            options[key] = getattr(app, key)
            setattr(app, key, value)
        if name != "PowerPoint":
            app.Visible = False
        if name == "Excel":
            for key in ("EnableEvents", "AskToUpdateLinks"):
                options[key] = getattr(app, key)
                setattr(app, key, False)
        if name == "Word":
            for key in ("UpdateLinksAtOpen", "ConfirmConversions", "SaveNormalPrompt"):
                word_options[key] = getattr(app.Options, key)
                setattr(app.Options, key, False)
        yield app
    finally:
        if app is not None and owned:
            collection = app.Documents if name == "Word" else (app.Workbooks if name == "Excel" else app.Presentations)
            with suppress(Exception):
                for i in range(collection.Count, 0, -1):
                    document = collection(i)
                    if name == "PowerPoint":
                        document.Saved = True
                        document.Close()
                    else:
                        document.Close(0 if name == "Word" else False)
            for key, value in word_options.items():
                with suppress(Exception):
                    setattr(app.Options, key, value)
            for key, value in options.items():
                with suppress(Exception):
                    setattr(app, key, value)
            with suppress(Exception):
                app.Quit()
        app = None
        gc.collect()
        pythoncom.CoUninitialize()


def _perform(app, operation, source, target, private):
    password = "EditorPDF-" + os.urandom(16).hex()
    if operation == "word_pdf":
        document = app.Documents.Open(source, ConfirmConversions=False, ReadOnly=True,
                                      AddToRecentFiles=False, Visible=False, NoEncodingDialog=True,
                                      PasswordDocument=password, WritePasswordDocument=password)
        document.ExportAsFixedFormat(target, 17, OpenAfterExport=False)
        return None
    if operation == "excel_pdf":
        app.Workbooks.Add(-4167)
        app.Calculation = -4135
        document = app.Workbooks.Open(source, UpdateLinks=0, ReadOnly=True, AddToMru=False,
                                      IgnoreReadOnlyRecommended=True, Password=password, WriteResPassword=password)
        document.ExportAsFixedFormat(0, target, OpenAfterPublish=False)
        return None
    if operation == "powerpoint_pdf":
        document = app.Presentations.Open(source, ReadOnly=True, Untitled=False, WithWindow=False)
        document.SaveAs(target, 32)
        return None
    raise ValueError(f"Operación de Microsoft 365 desconocida: {operation}")


def _office_process(conn, operation, source, target, private):
    try:
        with _application(_APPS[operation], conn) as app:
            result = _perform(app, operation, source, target, private)
        conn.send(("result", result))
    except Exception as exc:
        conn.send(("error", f"Microsoft 365 ({_APPS[operation]}): {exc}"))
    finally:
        conn.close()
