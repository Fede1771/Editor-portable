"""Editor PDF Portable."""
import warnings

# Suprimir advertencia transitoria de importación de la API clásica de PyMuPDF
warnings.filterwarnings("ignore", category=FutureWarning, module=r"fitz(\..*)?")
warnings.filterwarnings("ignore", message=r".*The `fitz` API is deprecated.*", category=FutureWarning)
