"""Módulo de privacidad, seguridad de datos corporativa y gestor de limpieza de temporales."""
from __future__ import annotations

import atexit
import ctypes
import os
import re
import shutil
import tempfile
import threading
import json
import time
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

_PID_RE = re.compile(r"^editorpdf_p(\d+)_")
_OWNER_TAG = "EditorPDFPortable-temp-v1"
_ORPHAN_MIN_AGE = 24 * 60 * 60


def _temp_root() -> str:
    root = os.path.abspath(os.path.join(tempfile.gettempdir(), "EditorPDFPortable"))
    if os.path.islink(root) or getattr(os.path, "isjunction", lambda p: False)(root):
        raise ValueError("La carpeta temporal de la aplicación no puede ser un enlace.")
    os.makedirs(root, exist_ok=True)
    return root


def _mark_owned(path: str) -> None:
    with open(path + ".owner.json", "x", encoding="utf-8") as stream:
        json.dump({"app": _OWNER_TAG, "pid": os.getpid(), "created": time.time()}, stream)


def register_private_mode_hook(cb: Callable[[bool], None]) -> None:
    """Registra un callback invocado al cambiar el estado de modo privado (H46)."""
    if cb not in _PRIVATE_MODE_HOOKS:
        _PRIVATE_MODE_HOOKS.append(cb)


def is_private_mode() -> bool:
    """Sesión sin recientes y con Undo en RAM; algunas conversiones requieren disco."""
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
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return ctypes.get_last_error() != 87  # acceso denegado u otro error: no borrar
            try:
                exit_code = ctypes.c_ulong()
                if kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return True
            finally:
                kernel.CloseHandle(handle)
        except Exception:
            return True  # no se pudo demostrar que terminó
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def secure_wipe_file(file_path: str) -> bool:
    """Sobreescribe el contenido del archivo con ceros antes de eliminarlo. Retorna True si dejó de existir (H03, H26)."""
    try:
        if os.path.islink(file_path):
            os.unlink(file_path)
            return True
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
    """Limpiar el árbol propio sin seguir enlaces o junctions hacia otros directorios."""
    try:
        if os.path.islink(dir_path) or getattr(os.path, "isjunction", lambda p: False)(dir_path):
            os.rmdir(dir_path) if os.path.isdir(dir_path) else os.unlink(dir_path)
            return True
        if not os.path.exists(dir_path):
            return True
        with os.scandir(dir_path) as entries:
            children = list(entries)
        for entry in children:
            if entry.is_dir(follow_symlinks=False):
                secure_wipe_dir(entry.path)
            else:
                secure_wipe_file(entry.path)
        os.rmdir(dir_path)
    except OSError:
        pass
    return not os.path.lexists(dir_path)


def _with_pid_prefix(prefix: str) -> str:
    """Incrusta el PID del proceso actual en el prefijo para distinguir instancias activas (H26)."""
    label = re.sub(r"[^a-zA-Z0-9_-]", "_", prefix).strip("_")
    return f"editorpdf_p{os.getpid()}_{label}_"


class TempManager:
    """Temporales aislados y limpieza verificable de mejor esfuerzo."""

    @classmethod
    def register(cls, path: str) -> str:
        """Registra un temporal para intentar limpiarlo y reintentar si falla."""
        if not path:
            return path
        abs_p = os.path.abspath(path)
        with _LOCK:
            _REGISTERED_TEMP_PATHS.add(abs_p)
        return abs_p

    @classmethod
    def create_temp_dir(cls, prefix: str = "editorpdf_") -> str:
        """Crea y registra un directorio temporal seguro asociado al PID actual (H26)."""
        d = tempfile.mkdtemp(prefix=_with_pid_prefix(prefix), dir=_temp_root())
        cls.register(d)
        _mark_owned(d)
        return d

    @classmethod
    def create_temp_file(cls, prefix: str = "editorpdf_", suffix: str = ".tmp", content: bytes | None = None) -> tuple[int, str] | str:
        """Crea y registra un archivo temporal seguro devolviendo (fd, path) o solo path si se pasó content."""
        fd, path = tempfile.mkstemp(prefix=_with_pid_prefix(prefix), suffix=suffix, dir=_temp_root())
        cls.register(path)
        _mark_owned(path)
        if content is not None:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
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
        if os.path.islink(abs_p):
            ok = secure_wipe_file(abs_p)
        elif os.path.isdir(abs_p):
            ok = secure_wipe_dir(abs_p)
        elif os.path.isfile(abs_p):
            ok = secure_wipe_file(abs_p)
        if ok and not os.path.exists(abs_p):
            secure_wipe_file(abs_p + ".owner.json")
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
        """Sólo residuos propios marcados, de más de 24 horas y con PID terminado."""
        count = 0
        try:
            temp_root = _temp_root()
            for entry in os.listdir(temp_root):
                if not entry.endswith(".owner.json"):
                    continue
                name = entry[:-len(".owner.json")]
                m = _PID_RE.match(name)
                marker = os.path.join(temp_root, entry)
                if not m or os.path.islink(marker):
                    continue
                try:
                    with open(marker, encoding="utf-8") as stream:
                        owner = json.load(stream)
                    if (owner.get("app") != _OWNER_TAG or owner.get("pid") != int(m.group(1))
                            or time.time() - float(owner["created"]) < _ORPHAN_MIN_AGE
                            or _is_pid_running(owner["pid"])):
                        continue
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                full_p = os.path.join(temp_root, name)
                if os.path.dirname(os.path.realpath(full_p)) != os.path.realpath(temp_root):
                    continue
                if os.path.abspath(full_p) in _REGISTERED_TEMP_PATHS:
                    continue
                try:
                    if cls.cleanup_path(full_p):
                        count += 1
                except Exception:
                    pass
        except Exception:
            pass
        return count


# Registrar limpiador al apagarse el proceso
atexit.register(TempManager.cleanup_all)
