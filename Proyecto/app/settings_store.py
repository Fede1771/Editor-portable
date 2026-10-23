"""Acceso centralizado a las preferencias persistentes de la aplicación.

Permite aislar las preferencias (por ejemplo durante las pruebas automatizadas) definiendo la
variable de entorno ``EDITORPDF_SETTINGS_DIR``: en ese caso se usa un archivo INI dentro de esa
carpeta en lugar del Registro de Windows del usuario.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QSettings

SETTINGS_ORG = "EditorPDFPortable"
SETTINGS_APP = "Settings"


def app_settings() -> QSettings:
    """Devuelve el almacén de preferencias activo (aislado si se definió EDITORPDF_SETTINGS_DIR)."""
    override = os.environ.get("EDITORPDF_SETTINGS_DIR")
    if override:
        os.makedirs(override, exist_ok=True)
        return QSettings(os.path.join(override, "settings.ini"), QSettings.IniFormat)
    return QSettings(SETTINGS_ORG, SETTINGS_APP)
