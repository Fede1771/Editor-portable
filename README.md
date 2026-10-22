# Editor PDF Portable

Suite ligera, autónoma y **100% offline** para visualización, edición in situ, organización, compresión y seguridad de documentos PDF en Windows.

No requiere instalación, permisos de administrador, Python ni conexión a internet.

---

## 🚀 Cómo Ejecutar

### 1. Versión Portable (Para usuarios finales y distribución)
- **Ejecutable directo:** `dist\EditorPDFPortable\EditorPDFPortable.exe`
- **Lanzador rápido:** `Abrir_EditorPortable.bat`
- **Para compartir o distribuir:** Copiá la carpeta `dist\EditorPDFPortable` (o comprimila en un `.zip`) a cualquier pendrive, red compartida o equipo con Windows 10/11.

### 2. Modo Desarrollo (Código Fuente)
- Ejecutá `run.bat` o desde PowerShell:
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```

---

## 🛠️ Capacidades Principales

### 👁️ Visualización y Lectura Fluida
- **Selección natural de texto:** Herramienta de selección activa por defecto con menú contextual y pastilla flotante rápida (`Copiar`, `Resaltar`, `Tachar`).
- **Navegación completa:** Pestañas múltiples, panel lateral con miniaturas visuales, marcadores jerárquicos, adjuntos embebidos y comentarios.
- **Búsqueda flotante (`Ctrl+F`):** Conteo de coincidencias en tiempo real y navegación ágil (`F3` / `Shift+F3`).
- **Apertura inteligente:** Abre por defecto en la carpeta *Documentos* del usuario y recuerda la última ubicación utilizada durante la sesión.

### ✍️ Edición In Situ y Contenido
- **Edición directa de texto (`T`):** Modificá textos existentes en el PDF preservando tipografía, tamaño original, color y alineación sin romper tarjetas ni fondos.
- **Censura irreversible (*Redaction*):** Destrucción permanente de datos sensibles o áreas seleccionadas (`R`), o búsqueda y censura por palabras clave.
- **Imágenes y enlaces:** Inserción de imágenes (`I`) y creación de hipervínculos interactivos (`L`).
- **Anotaciones y dibujo:** Lápiz de trazo libre (`P`), notas adhesivas (`N`), resaltado fluorescente, subrayado y tachado.

### 🗜️ Compresión Inteligente (`Ctrl+Shift+C`)
- **📧 Envío por Correo / Póliza Ligera (< 5 MB):** Máxima compresión a 130 DPI con sanitización de metadatos para envíos sin rebotes.
- **📂 Archivo Digital Corporativo:** Balance óptimo de legibilidad en monitor y peso reducido (180 DPI, calidad 80%).
- **⚖️ Legajo Pericial / Siniestros:** Máxima fidelidad de firmas, sellos periciales y fotos de daños (300 DPI, calidad 92%).
- **⚙️ Ajuste personalizado:** Control libre de DPI y calidad JPEG.

### 🛡️ Seguridad y Privacidad Cero Huella
- **Sesión Privada (Cero Persistencia):** Al activarla, el programa no guarda rutas ni nombres de documentos en el Registro de Windows (`QSettings`).
- **Limpiador Forense de Temporales:** Todo archivo de trabajo temporal se sobreescribe con ceros (`secure_wipe`) antes de eliminarse al cerrar la aplicación.
- **Sanitización de metadatos:** Opción de guardar copias despojadas de nombres de usuario, rutas locales y software de autoría.
- **Bloqueo activo de amenazas:** Neutraliza scripts automáticos (`/JavaScript`, `/Launch`) y analiza enlaces externos contra phishing o URLs sospechosas.

### 📄 Organización de Páginas y Creación
- **Manipulación de páginas:** Insertar, reemplazar, extraer, duplicar, rotar, mover y recortar márgenes.
- **Dividir PDF:** Por número de páginas, rangos personalizados o marcadores.
- **Marcas de agua y numeración:** Bates, encabezados y pies de página dinámicos (`{n}/{total}`).
- **Creación y combinación:** Unir múltiples PDFs, imágenes o capturas del portapapeles.
- **Conversión y exportación:** A Word (`.docx`), Excel (`.xlsx`), texto plano e imágenes PNG/JPG.
- **OCR Integrado (Español/Inglés):** Genera capa de texto buscable a 300 DPI sobre documentos escaneados.
- **Formularios (AcroForms):** Rellenado interactivo y aplanado (*flatten*) definitivo.

---

## ⌨️ Atajos de Teclado Clave

| Atajo | Acción |
| :--- | :--- |
| `Ctrl + O` | Abrir documento PDF |
| `Ctrl + S` | Guardar cambios |
| `Ctrl + Shift + S` | Guardar como... |
| `Ctrl + Shift + C` | Comprimir PDF (Perfiles de pólizas y siniestros) |
| `Ctrl + P` | Imprimir documento |
| `Ctrl + W` | Cerrar pestaña activa |
| `Ctrl + F` | Buscar texto en el documento |
| `Ctrl + A` | Seleccionar todo el texto de la página |
| `Ctrl + Z` / `Ctrl + Y` | Deshacer / Rehacer |
| `Ctrl + 1` / `Ctrl + 2` | Ajustar vista al ancho / página completa |
| `F4` | Mostrar / ocultar panel lateral |
| `V` | Modo Selección de texto (Predeterminado) |
| `T` | Herramienta Texto (editar in situ o insertar) |
| `R` | Herramienta Censurar / Redactar |
| `I` | Insertar imagen |
| `L` | Insertar enlace |
| `P` | Lápiz de trazo libre |
| `N` | Insertar nota o comentario |
| `Supr` | Eliminar páginas seleccionadas |

---

## 🧪 Pruebas y Compilación

### Ejecutar Suite de Pruebas
Valida creación, operaciones, edición in situ, OCR, compresión, seguridad y cero huella:
```powershell
.\.venv\Scripts\python.exe tests\test_suite.py
```

### Recompilar el Ejecutable Portable
Genera el paquete distribuible en `dist\EditorPDFPortable\`:
```powershell
.\.venv\Scripts\python.exe build_portable.py
```
