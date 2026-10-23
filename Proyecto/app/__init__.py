"""Editor PDF Portable."""
import os
import warnings

# Suprimir advertencia transitoria de importación de la API clásica de PyMuPDF
warnings.filterwarnings("ignore", category=FutureWarning, module=r"fitz(\..*)?")
warnings.filterwarnings("ignore", message=r".*The `fitz` API is deprecated.*", category=FutureWarning)

import pymupdf as fitz  # noqa: E402


def _install_fitz_hooks() -> None:
    """Registra en cada fitz.Document la contraseña autenticada (H04) y los bytes originales (H49)."""
    if getattr(fitz.Document, "_editorpdf_hooked", False):
        return

    orig_auth = fitz.Document.authenticate

    def _wrapped_authenticate(self, password: str) -> int:
        rc = orig_auth(self, password)
        if rc and rc > 0:
            try:
                setattr(self, "_editorpdf_password", password)
            except Exception:
                pass
        return rc

    fitz.Document.authenticate = _wrapped_authenticate

    orig_open = fitz.open

    def _wrapped_open(*args, **kwargs):
        doc = orig_open(*args, **kwargs)
        try:
            raw_bytes: bytes | None = None
            if "stream" in kwargs and isinstance(kwargs["stream"], (bytes, bytearray)):
                raw_bytes = bytes(kwargs["stream"])
            elif len(args) >= 2 and isinstance(args[1], (bytes, bytearray)):
                raw_bytes = bytes(args[1])
            elif len(args) == 1 and isinstance(args[0], (str, os.PathLike)) and os.path.isfile(args[0]):
                with open(args[0], "rb") as fh:
                    raw_bytes = fh.read()
            if raw_bytes is not None:
                setattr(doc, "_editorpdf_source_bytes", raw_bytes)
        except Exception:
            pass
        return doc

    fitz.open = _wrapped_open
    fitz.Document._editorpdf_hooked = True


_install_fitz_hooks()
