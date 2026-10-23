"""Módulo de privacidad, seguridad de datos corporativa y gestor de limpieza de temporales."""
from __future__ import annotations

import atexit
import ctypes
import os
import re
import shutil
import tempfile
import threading
from typing import Callable

from .settings_store import app_settings

SETTINGS_ORG = "EditorPDFPortable"
SETTINGS_APP = "Settings"
KEY_PRIVATE_MODE = "security_private_mode"

_LOCK = threading.Lock()
_REGISTERED_TEMP_PATHS: set[str] = set()
_SESSION_PRIVATE_MODE: bool | None = None
_PRIVATE_MODE_HOOKS: list[Callable[[bool], None]] = []
_LAST_APP_CLIPBOARD_TEXT: str | None = None

_PID_RE = re.compile(r"^(?:editorpdf|pdf_attachment|pdf_word)_p(\d+)_")


def register_private_mode_hook(cb: Callable[[bool], None]) -> None:
    """Registra un callback invocado al cambiar el estado de modo privado (H46)."""
    if cb not in _PRIVATE_MODE_HOOKS:
        _PRIVATE_MODE_HOOKS.append(cb)


def is_private_mode() -> bool:
    """Verifica si la sesión actual está en modo privado (sin persistencia en Registro ni temporales)."""
    global _SESSION_PRIVATE_MODE
    if _SESSION_PRIVATE_MODE is not None:
        return _SESSION_PRIVATE_MODE
    settings = app_settings()
    _SESSION_PRIVATE_MODE = settings.value(KEY_PRIVATE_MODE, False, type=bool)
    return _SESSION_PRIVATE_MODE


def set_private_mode(enabled: bool) -> None:
    """Activa o desactiva el modo privado para la sesión y futuras sesiones (H46)."""
    global _SESSION_PRIVATE_MODE
    _SESSION_PRIVATE_MODE = bool(enabled)
    settings = app_settings()
    settings.setValue(KEY_PRIVATE_MODE, _SESSION_PRIVATE_MODE)
    if _SESSION_PRIVATE_MODE:
        # Al activar modo privado, limpiar inmediatamente el historial persistido
        from .welcome import clear_recent_files
        clear_recent_files()
    for cb in list(_PRIVATE_MODE_HOOKS):
        try:
            cb(_SESSION_PRIVATE_MODE)
        except Exception:
            pass


def copy_to_clipboard(text: str) -> None:
    """Copia explícitamente texto al portapapeles del sistema y registra su propiedad para limpieza segura (H47)."""
    global _LAST_APP_CLIPBOARD_TEXT
    if not text:
        return
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            cb = QApplication.clipboard()
            cb.setText(text)
            _LAST_APP_CLIPBOARD_TEXT = text
    except Exception:
        pass


def clear_app_clipboard_if_owned() -> bool:
    """Limpia el portapapeles únicamente si todavía contiene el texto copiado por esta sesión,
    respetando cualquier contenido nuevo copiado por el usuario desde otra aplicación (H47)."""
    global _LAST_APP_CLIPBOARD_TEXT
    if not _LAST_APP_CLIPBOARD_TEXT:
        return False
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            cb = QApplication.clipboard()
            if cb.text() == _LAST_APP_CLIPBOARD_TEXT:
                cb.clear()
                _LAST_APP_CLIPBOARD_TEXT = None
                return True
    except Exception:
        pass
    _LAST_APP_CLIPBOARD_TEXT = None
    return False


def _is_pid_running(pid: int) -> bool:
    """Verifica si un proceso con `pid` sigue activo en el sistema operativo (H26)."""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return True
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def secure_wipe_file(file_path: str) -> bool:
    """Sobreescribe el contenido del archivo con ceros antes de eliminarlo. Retorna True si dejó de existir (H03, H26)."""
    try:
        if not os.path.exists(file_path):
            return True
        if os.path.isfile(file_path):
            size = os.path.getsize(file_path)
            if size > 0:
                with open(file_path, "r+b") as f:
                    f.seek(0)
                    chunk_size = 65536
                    remaining = size
                    while remaining > 0:
                        to_write = min(remaining, chunk_size)
                        f.write(b"\x00" * to_write)
                        remaining -= to_write
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
            os.remove(file_path)
    except Exception:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass
    return not os.path.exists(file_path)


def secure_wipe_dir(dir_path: str) -> bool:
    """Sobrescribe y elimina recursivamente una carpeta y todos sus archivos temporales. Retorna True si se eliminó (H26)."""
    try:
        if not os.path.exists(dir_path):
            return True
        if os.path.isdir(dir_path):
            for root, dirs, files in os.walk(dir_path, topdown=False):
                for name in files:
                    secure_wipe_file(os.path.join(root, name))
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except Exception:
                        pass
            os.rmdir(dir_path)
    except Exception:
        shutil.rmtree(dir_path, ignore_errors=True)
    return not os.path.exists(dir_path)


def _with_pid_prefix(prefix: str) -> str:
    """Incrusta el PID del proceso actual en el prefijo para distinguir instancias activas (H26)."""
    if re.search(r"_p\d+_", prefix):
        return prefix
    base = prefix.rstrip("_")
    return f"{base}_p{os.getpid()}_"


class TempManager:
    """Gestor centralizado de ciclo de vida de archivos y carpetas temporales para cero huella."""

    @classmethod
    def register(cls, path: str) -> str:
        """Registra un archivo o carpeta temporal para su eliminación garantizada."""
        if not path:
            return path
        abs_p = os.path.abspath(path)
        with _LOCK:
            _REGISTERED_TEMP_PATHS.add(abs_p)
        return abs_p

    @classmethod
    def create_temp_dir(cls, prefix: str = "editorpdf_") -> str:
        """Crea y registra un directorio temporal seguro asociado al PID actual (H26)."""
        d = tempfile.mkdtemp(prefix=_with_pid_prefix(prefix))
        return cls.register(d)

    @classmethod
    def create_temp_file(cls, prefix: str = "editorpdf_", suffix: str = ".tmp", content: bytes | None = None) -> tuple[int, str] | str:
        """Crea y registra un archivo temporal seguro devolviendo (fd, path) o solo path si se pasó content."""
        fd, path = tempfile.mkstemp(prefix=_with_pid_prefix(prefix), suffix=suffix)
        cls.register(path)
        if content is not None:
            try:
                os.write(fd, content)
            finally:
                os.close(fd)
            return path
        return fd, path

    @classmethod
    def cleanup_path(cls, path: str) -> bool:
        """Elimina de forma segura un archivo o directorio temporal registrado.
        Conserva el registro en `_REGISTERED_TEMP_PATHS` si el borrado falla (H26)."""
        if not path:
            return False
        abs_p = os.path.abspath(path)
        existed = os.path.exists(abs_p)
        ok = True
        if os.path.isdir(abs_p):
            ok = secure_wipe_dir(abs_p)
        elif os.path.isfile(abs_p):
            ok = secure_wipe_file(abs_p)
        if ok and not os.path.exists(abs_p):
            with _LOCK:
                _REGISTERED_TEMP_PATHS.discard(abs_p)
            return existed
        return False

    @classmethod
    def cleanup_all(cls, exclude: set[str] | None = None) -> int:
        """Destruye con sobreescritura segura los temporales registrados en la sesión, excepto los excluidos.
        Si algún archivo está bloqueado y no puede borrarse, se mantiene registrado y no se cuenta como eliminado (H26, H47)."""
        exclude_set = {os.path.abspath(p) for p in (exclude or set())}
        with _LOCK:
            candidates = [p for p in _REGISTERED_TEMP_PATHS if p not in exclude_set]

        count = 0
        for p in candidates:
            try:
                existed = os.path.exists(p)
                if not existed:
                    with _LOCK:
                        _REGISTERED_TEMP_PATHS.discard(p)
                    continue
                if cls.cleanup_path(p):
                    count += 1
            except Exception:
                pass

        clear_app_clipboard_if_owned()
        return count

    @classmethod
    def sweep_orphaned_temps(cls) -> int:
        """Limpia residuos temporales huérfanos de sesiones previas en %TEMP% sin tocar procesos activos (H26)."""
        count = 0
        try:
            temp_root = tempfile.gettempdir()
            for entry in os.listdir(temp_root):
                if not (entry.startswith("editorpdf_") or entry.startswith("pdf_attachment_") or entry.startswith("pdf_word_")):
                    continue
                m = _PID_RE.match(entry)
                if m:
                    owner_pid = int(m.group(1))
                    if _is_pid_running(owner_pid):
                        continue
                full_p = os.path.join(temp_root, entry)
                if os.path.abspath(full_p) in _REGISTERED_TEMP_PATHS:
                    continue
                try:
                    if os.path.isdir(full_p):
                        if secure_wipe_dir(full_p):
                            count += 1
                    elif os.path.isfile(full_p):
                        if secure_wipe_file(full_p):
                            count += 1
                except Exception:
                    pass
        except Exception:
            pass
        return count


# Registrar limpiador al apagarse el proceso
atexit.register(TempManager.cleanup_all)
