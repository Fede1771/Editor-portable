"""Módulo de privacidad, seguridad de datos corporativa y gestor de limpieza de temporales."""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QSettings

SETTINGS_ORG = "EditorPDFPortable"
SETTINGS_APP = "Settings"
KEY_PRIVATE_MODE = "security_private_mode"

_LOCK = threading.Lock()
_REGISTERED_TEMP_PATHS: set[str] = set()
_SESSION_PRIVATE_MODE: bool | None = None


def is_private_mode() -> bool:
    """Verifica si la sesión actual está en modo privado (sin persistencia en Registro ni temporales)."""
    global _SESSION_PRIVATE_MODE
    if _SESSION_PRIVATE_MODE is not None:
        return _SESSION_PRIVATE_MODE
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    _SESSION_PRIVATE_MODE = settings.value(KEY_PRIVATE_MODE, False, type=bool)
    return _SESSION_PRIVATE_MODE


def set_private_mode(enabled: bool) -> None:
    """Activa o desactiva el modo privado para la sesión y futuras sesiones."""
    global _SESSION_PRIVATE_MODE
    _SESSION_PRIVATE_MODE = bool(enabled)
    settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
    settings.setValue(KEY_PRIVATE_MODE, _SESSION_PRIVATE_MODE)
    if _SESSION_PRIVATE_MODE:
        # Al activar modo privado, limpiar inmediatamente el historial persistido
        from .welcome import clear_recent_files
        clear_recent_files()


def secure_wipe_file(file_path: str) -> None:
    """Sobreescribe el contenido del archivo con ceros antes de eliminarlo (borrado seguro forense)."""
    try:
        if not os.path.isfile(file_path):
            return
        size = os.path.getsize(file_path)
        if size > 0:
            with open(file_path, "ba+", buffering=0) as f:
                f.seek(0)
                # Sobrescribir con ceros en bloques de 64 KB
                chunk_size = 65536
                remaining = size
                while remaining > 0:
                    to_write = min(remaining, chunk_size)
                    f.write(b"\x00" * to_write)
                    remaining -= to_write
                f.flush()
                os.fsync(f.fileno())
        os.remove(file_path)
    except Exception:
        # Fallback a borrado estándar si está bloqueado o con permisos restringidos
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass


def secure_wipe_dir(dir_path: str) -> None:
    """Sobrescribe y elimina recursivamente una carpeta y todos sus archivos temporales."""
    try:
        if not os.path.isdir(dir_path):
            return
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
        """Crea y registra un directorio temporal seguro."""
        d = tempfile.mkdtemp(prefix=prefix)
        return cls.register(d)

    @classmethod
    def create_temp_file(cls, prefix: str = "editorpdf_", suffix: str = ".tmp", content: bytes | None = None) -> tuple[int, str] | str:
        """Crea y registra un archivo temporal seguro devolviendo (fd, path) o solo path si se pasó content."""
        fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
        cls.register(path)
        if content is not None:
            try:
                os.write(fd, content)
            finally:
                os.close(fd)
            return path
        return fd, path

    @classmethod
    def cleanup_path(cls, path: str) -> None:
        """Elimina de forma segura un archivo o directorio temporal registrado."""
        if not path:
            return
        abs_p = os.path.abspath(path)
        with _LOCK:
            _REGISTERED_TEMP_PATHS.discard(abs_p)

        if os.path.isdir(abs_p):
            secure_wipe_dir(abs_p)
        elif os.path.isfile(abs_p):
            secure_wipe_file(abs_p)

    @classmethod
    def cleanup_all(cls) -> None:
        """Destruye con sobreescritura segura todos los temporales registrados en la sesión."""
        with _LOCK:
            paths = list(_REGISTERED_TEMP_PATHS)
            _REGISTERED_TEMP_PATHS.clear()

        for p in paths:
            try:
                if os.path.isdir(p):
                    secure_wipe_dir(p)
                elif os.path.isfile(p):
                    secure_wipe_file(p)
            except Exception:
                pass

    @classmethod
    def sweep_orphaned_temps(cls) -> int:
        """Limpia residuos temporales huérfanos de sesiones previas en %TEMP%."""
        count = 0
        try:
            temp_root = tempfile.gettempdir()
            for entry in os.listdir(temp_root):
                if entry.startswith("editorpdf_") or entry.startswith("pdf_attachment_"):
                    full_p = os.path.join(temp_root, entry)
                    try:
                        if os.path.isdir(full_p):
                            secure_wipe_dir(full_p)
                            count += 1
                        elif os.path.isfile(full_p):
                            secure_wipe_file(full_p)
                            count += 1
                    except Exception:
                        pass
        except Exception:
            pass
        return count


# Registrar limpiador al apagarse el proceso
atexit.register(TempManager.cleanup_all)
