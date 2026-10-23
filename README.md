# Editor PDF Portable

Suite ligera, autónoma y **100% offline** para visualización, edición in situ, organización, compresión y seguridad de documentos PDF en Windows.

Diseñada con una **interfaz moderna de una sola fila** (estilo Chrome / Acrobat actual), compatibilidad total con **Modo Oscuro de Windows** y **cero rastros en disco o registro**.

---

## 🚀 Modos de Ejecución y Distribución

### 1. Versión Portable (Para usuarios y despliegue en la empresa)
- **Ejecutable directo:** `dist\EditorPDFPortable\EditorPDFPortable.exe`
- **Lanzador rápido:** `Abrir_EditorPortable.bat`
- **Distribución corporativa:**
  - **Sin instalación:** No requiere privilegios de administrador (UAC) ni dependencias externas.
  - **Carpeta compartida o USB:** Basta con copiar la carpeta `dist\EditorPDFPortable` (o comprimirla en `.zip`) en un recurso de red (`\\servidor\Apps\`) o memoria USB.
  - **Despliegue con Microsoft Intune:** Puede empaquetarse en `.intunewin` y publicarse en el *Portal de Empresa* para auto-instalación en un clic.

### 2. Modo Desarrollo (Código Fuente)
- Ejecutá `run.bat` o desde PowerShell:
  ```powershell
  .\.venv\Scripts\python.exe main.py
  ```

---

## ✨ Características Principales

### 🖥️ Interfaz Moderna y Minimalista (Una Sola Fila)
- **Cabecera unificada:** Se eliminó la doble fila de menús tradicionales. Todo el control avanzado se reúne en el botón **`☰ Menú ▾`**, maximizando el espacio de lectura.
- **Acceso rápido a 1 clic:** Abrir, Guardar, Comprimir, Selección, Texto, Censura, Imagen, Anotaciones, Zoom y Navegación siempre visibles.
- **Modo Oscuro Nativo:** Adaptación automática a la paleta de colores de Windows (alto contraste y textos nítidos tanto en tema oscuro como claro).
- **Apertura inteligente:** Abre por defecto en la carpeta *Documentos* del usuario y recuerda la última carpeta utilizada durante la sesión.

### ✍️ Edición In Situ de Contenido
- **Edición directa de texto (`T`):** Modificá párrafos y encabezados preservando la tipografía, tamaño original, color y alineación sin romper tarjetas ni fondos.
- **Censura irreversible (*Redaction - R*):** Destrucción física de texto o áreas seleccionadas con relleno negro definitivo, o búsqueda y censura por palabras clave.
- **Imágenes y enlaces:** Inserción de logotipos/imágenes (`I`) y creación de hipervínculos interactivos (`L`).
- **Anotaciones y trazo:** Lápiz libre (`P`), notas adhesivas (`N`), resaltador fluorescente, subrayado y tachado.

### 🗜️ Compresión Inteligente para Aseguradoras (`Ctrl+Shift+C`)
- **📧 Envío por Correo / Póliza Ligera (< 5 MB):** Máxima compresión a 130 DPI con sanitización de metadatos para envíos por email sin rebotes.
- **📂 Archivo Digital Corporativo:** Balance óptimo entre fidelidad en pantalla y peso reducido (180 DPI, calidad 80%).
- **⚖️ Legajo Pericial / Siniestros:** Máxima nitidez para fotos de daños, sellos periciales y firmas (300 DPI, calidad 92%).
- **⚙️ Personalizado:** Control libre y granular de resolución (DPI) y compresión JPEG.

### 🛡️ Seguridad y Privacidad "Cero Huella"
- **Sesión Privada (Cero Persistencia):** Conmutable desde la barra. Cuando está activa, la aplicación **no guarda rutas ni historial en el Registro de Windows** (`QSettings`).
- **Limpieza Forense de Temporales:** Los archivos temporales se sobreescriben con ceros (`\x00`) y se fuerzan a disco (`fsync`) antes de eliminarse al cerrar la aplicación.
- **Sanitización de metadatos:** Opción para generar copias anónimas libres de nombres de usuario, rutas locales del equipo y software de creación.
- **Protección contra amenazas:** Neutraliza ejecución automática de scripts (`/JavaScript`, `/Launch`) y analiza enlaces externos contra phishing o suplantación de dominio.

### 📑 Gestión de Páginas y Creación
- **Herramientas de página:** Insertar, reemplazar, extraer, duplicar, rotar, mover y recortar márgenes.
- **Dividir PDF:** Por número de páginas, rangos personalizados o marcadores.
- **Marcas de agua y numeración:** Bates correlativo, encabezados y pies de página dinámicos (`{n}/{total}`).
- **Creación y combinación:** Unir múltiples PDFs, imágenes o capturas del portapapeles en un solo archivo.
- **Exportación:** A Word (`.docx`), Excel (`.xlsx`), texto plano e imágenes PNG/JPG.
- **OCR Integrado (Español/Inglés):** Reconocimiento óptico de caracteres a 300 DPI para digitalizar escaneos.
- **Formularios (AcroForms):** Completado de campos interactivos y aplanado (*flatten*) definitivo.

---

## ⌨️ Atajos de Teclado

| Atajo | Acción |
| :--- | :--- |
| `Ctrl + O` | Abrir documento PDF |
| `Ctrl + S` | Guardar cambios |
| `Ctrl + Shift + S` | Guardar como... |
| `Ctrl + Shift + C` | Comprimir PDF (Perfiles de pólizas y siniestros) |
| `Ctrl + P` | Imprimir documento |
| `Ctrl + W` | Cerrar pestaña activa |
| `Ctrl + Q` | Salir de la aplicación |
| `Ctrl + F` | Abrir buscador de texto flotante |
| `F3` / `Shift + F3` | Coincidencia siguiente / anterior |
| `Ctrl + A` | Seleccionar todo el texto de la página |
| `Ctrl + Z` / `Ctrl + Y` | Deshacer / Rehacer |
| `Ctrl + 1` / `Ctrl + 2` | Ajustar vista al ancho / página completa |
| `F4` | Mostrar / ocultar panel lateral |
| `V` | Herramienta Selección (Predeterminada) |
| `T` | Herramienta Texto (editar in situ o insertar) |
| `R` | Herramienta Censurar / Redactar |
| `I` | Insertar imagen |
| `L` | Insertar hipervínculo |
| `P` | Lápiz de trazo libre |
| `N` | Insertar nota adhesiva o comentario |
| `Supr` | Eliminar páginas seleccionadas |

---

## 🧪 Validación y Compilación

### Suite de Pruebas Automatizadas
Ejecuta las validaciones integrales de edición, OCR, compresión, privacidad y seguridad:
```powershell
.\.venv\Scripts\python.exe tests\test_suite.py
```

### Recompilar el Ejecutable Portable
Genera el paquete distribuible actualizado en `dist\EditorPDFPortable\`:
```powershell
.\.venv\Scripts\python.exe build_portable.py
```
