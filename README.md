# Editor PDF Portable

Una suite completa, ligera y autónoma para la visualización, edición in situ, organización, creación, reconocimiento de texto (OCR), conversión, optimización y **seguridad activa** de documentos PDF en Windows.

Diseñado para ser **100% portable**: puede ejecutarse en cualquier PC con Windows sin necesidad de instalar Python, librerías adicionales ni software de terceros.

---

## Modos de Ejecución

### 1. Acceso Directo de Escritorio
Si utilizas el acceso directo creado en tu Escritorio de Windows:
- **Doble clic en:** `Editor PDF Portable` (con su icono oficial rojo).
- **Arranque ultra rápido:** Incorpora un *Splash Screen* nativo en C que responde de inmediato en pantalla (<50 ms).

### 2. Modo Portable (Para llevar en un Pendrive o a otra PC)
No requiere tener Python instalado ni permisos de administrador:
- **Doble clic en:** `Abrir_EditorPortable.bat` (en la raíz de la carpeta), o
- **Ejecutable directo:** `dist\EditorPDFPortable\EditorPDFPortable.exe`

> **Para compartir o usar en otra computadora:**  
> Basta con copiar la carpeta completa `dist\EditorPDFPortable` (o comprimirla en un archivo `.zip`) a cualquier memoria USB o disco externo. Funciona de inmediato en cualquier PC con Windows 10 u 11.

### 3. Modo Desarrollo (Código Fuente)
Para desarrolladores o usuarios que deseen modificar el código fuente con el entorno virtual:
- **Doble clic en:** `run.bat`
- O desde la consola de comandos de PowerShell:
  ```powershell
  .\.venv\Scripts\python.exe main.py [archivo.pdf]
  ```

---

## Resumen de Funcionalidades

### 1. Visor Avanzado y Experiencia de Usuario
- **Arranque instantáneo con Splash Screen:** Al hacer doble clic, la aplicación reacciona inmediatamente en pantalla mediante un splash screen de bajo nivel, eliminando los tiempos muertos de espera mientras cargan las librerías gráficas.
- **Selección de texto natural estilo Acrobat:**
  - Al arrastrar sobre el texto, se destacan franjas continuas de selección en color azul nativo translúcido ajustadas al milímetro sobre cada línea de texto real (sin recuadros punteados de recorte).
  - La selección se mantiene visible al soltar el ratón para interactuar con la pastilla flotante.
  - Se deselecciona naturalmente con un clic libre o presionando la tecla `Esc`.
- **Modos de visualización:** Página simple, desplazamiento vertical continuo y vista de dos páginas (estilo libro).
- **Zoom fluido:** De 25% hasta 500%, botones de ajuste automático al ancho de página (`Ctrl+1`) y a página completa (`Ctrl+2`).
- **Panel lateral compacto:**
  - **Miniaturas (`📄`):** navegación visual rápida, selección múltiple y reordenamiento arrastrando.
  - **Marcadores / Índice (`📑`):** navegación jerárquica por secciones y títulos del PDF.
  - **Comentarios embebidos (`💬`):** árbol con todas las notas y resaltados existentes en el PDF.
  - **Archivos adjuntos embebidos (`📎`):** detecta y lista todos los archivos incrustados en el PDF con sus iconos oficiales de Windows, peso y fecha.
- **Impresión nativa directa (`Ctrl+P`):** Cuadro de diálogo oficial de Windows para imprimir a cualquier impresora física o virtual con selección de rango de páginas.
- **Pastilla flotante de acciones rápidas:** Al seleccionar cualquier fragmento de texto con la herramienta de selección (`V`), se despliega una mini-burbuja flotante con acceso instantáneo a `[ Copiar ]`, `[ 🖍 Resaltar ]` y `[ ̶S̶ Tachar ]` (aplicados línea por línea de manera limpia).
- **Plegado inteligente del panel lateral:** En documentos breves (1 o 2 páginas) sin marcadores ni adjuntos, el panel lateral inicia plegado automáticamente para una visualización a pantalla completa.
- **Navegación ultra rápida con teclado:** Desplazamiento fluido con `Espacio` (avanzar) y `Shift+Espacio` (retroceder), flechas `←` / `→` o `RePág` / `AvPág`.
- **Búsqueda flotante inteligente (`Ctrl+F`):** Barra flotante moderna estilo navegador/Acrobat en la esquina superior derecha que cuenta coincidencias en tiempo real y se oculta con `Esc`.
- **Pantalla de bienvenida optimizada:** Área inicial limpia con acceso directo a archivos abiertos recientemente (`Archivo -> Abrir recientes`), creación en blanco o arrastrar y soltar directo, con carga instantánea de historial (< 1 ms).
- **Múltiples pestañas:** Apertura simultánea de varios documentos con navegación por pestañas independientes.
- **Protección por contraseña:** Apertura y autenticación de documentos PDF protegidos.

---

### 2. Seguridad Activa y Privacidad (0% Impacto en Rendimiento)
- **Escáner pasivo ultrarrápido (< 0.1 ms):** Al abrir cualquier documento, el motor analiza la cabecera en busca de posibles amenazas sin demorar la apertura.
- **Neutralización de JavaScript y Acciones Automáticas:**
  - Detecta y bloquea la ejecución de scripts `/JavaScript`, llamadas a programas externos (`/Launch`) y eventos automáticos de inicio (`/OpenAction`, `/AA`).
  - Muestra una barra de alerta discreta en la parte superior: `🛡️ Aviso de seguridad: Este documento contiene scripts interactivos (la ejecución automática fue bloqueada)`.
  - Botón de 1 clic para **"Desactivar y Limpiar Scripts"**, que purga definitivamente las rutinas activas del archivo.
- **Protección Anti-Phishing en Hipervínculos:**
  - Detección activa de enlaces al pasar el cursor (cambio a cursor interactivo y previsualización de destino).
  - Al hacer clic, abre un diálogo seguro (`SafeLinkDialog`) con el destino exacto antes de invocar al navegador.
  - Alerta roja destacada ante riesgos de seguridad: enlaces que apuntan a direcciones IP numéricas directas, descargas de ejecutables (`.exe`, `.bat`, `.scr`, `.vbs`, etc.) o suplantación de dominio (*spoofing*, donde el texto del PDF simula ser un banco u organismo pero la URL oculta redirige a otro sitio).
- **Guardar Copia Anónima (Limpieza de Metadatos y Huellas):**
  - Opción directa en menú **Archivo -> Guardar copia anónima…**
  - Despoja al PDF de nombres de usuario de Windows, rutas locales del equipo (`C:\Users\...`), software de autoría, historial de revisiones y registros XML/XMP de seguimiento.
- **Blindaje de Archivos Adjuntos Embebidos:**
  - Inspección estricta de adjuntos. Bloquea la apertura directa de archivos con extensiones ejecutables o de script para evitar que se ejecute malware en el sistema, forzando la opción de guardarlos en disco para analizarlos con antivirus.

---

### 3. Edición de Contenido In Situ (In-Place Editing)
- **Aislamiento estricto de renglón:** Al hacer clic sobre cualquier línea o encabezado (por ejemplo, títulos institucionales), el algoritmo aísla exclusivamente esa fila horizontal, garantizando que **jamás se trague ni altere la fila inferior ni sus fuentes**.
- **Limpieza de Formularios / Widgets Subyacentes:** Al modificar textos en documentos oficiales con campos interactivos (AcroForms/Widgets), el editor detecta y elimina los widgets de formulario subyacentes antes de insertar el nuevo texto, impidiendo que el texto original quede duplicado o encimado.
- **Expansión automática del área de redacción:** Si el texto modificado es más largo que el original, la zona de borrado se amplía en consecuencia, asegurando que no queden letras residuales debajo.
- **Detección inteligente de tipografía, tamaño, color y alineación:**
  - Tamaño de letra calibrado con precisión.
  - Detección de color por vector o muestreo espectral.
  - Reconocimiento de familia (Helvetica, Times Roman, Courier) y estilos (**Negrita** / *Cursiva*).
  - Alineación calculada según la geometría real de la página (evitando alineaciones forzadas).
- **Ajuste automático de tipografía (*Auto-fit*):** Si el nuevo texto supera el ancho de la tarjeta o celda, reduce proporcionalmente el puntaje para no desbordar.
- **Preservación total de recuadros y diagramas:** Detecta el contorno de tarjetas y casillas sin romper bordes ni líneas vectoriales.
- **Censura permanente (*Redact*):** Destrucción física e irreversible de texto e imágenes seleccionadas con relleno negro (`R`), o búsqueda y censura por palabras clave.
- **Insertar imágenes e hipervínculos:** Herramientas interactivas para agregar logotipos (`I`) o links (`L`).
- **Deshacer / Rehacer ilimitado:** Historial completo con `Ctrl+Z` y `Ctrl+Y` en todas las ediciones.

---

### 4. Organizar y Gestionar Páginas
- **Insertar:** Añade páginas en blanco o páginas de otros archivos PDF en cualquier posición.
- **Extraer:** Guarda páginas seleccionadas en un nuevo archivo PDF independiente.
- **Eliminar y Duplicar:** Borra páginas seleccionadas (`Supr`) o duplícalas al instante.
- **Rotación:** Gira páginas seleccionadas 90° o 180°.
- **Reordenar:** Arrastra miniaturas en el panel lateral o usa `Alt + Flecha Arriba / Abajo`.
- **Dividir PDF:** 
  - Dividir cada *N* páginas.
  - Dividir por rangos personalizados (ej. `1-3, 5, 8-10`).
  - Dividir automáticamente por marcadores de nivel superior.
- **Recortar márgenes:** Ajuste visual y milimétrico de márgenes en páginas seleccionadas o en todo el documento.
- **Marcas de agua:** Texto personalizado con ángulo, tamaño, color y nivel de opacidad.
- **Encabezados y Pies de página:** Plantillas configurables con sustitución dinámica de `{n}` (página), `{total}` y `{bates}` (numeración correlativa).
- **Color de fondo:** Aplicación de fondos de color personalizados.

---

### 5. Crear PDF desde Múltiples Fuentes
- **Combinar archivos:** Agrupa múltiples PDFs, imágenes y documentos en un único PDF con marcadores automáticos.
- **Conversión de Office:** Importa y convierte archivos de Microsoft Office (`.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, etc.) utilizando LibreOffice en segundo plano.
- **Desde imágenes:** Convierte colecciones de imágenes (PNG, JPG, TIFF, BMP) ajustándolas a página completa o tamaño original.
- **Desde texto o HTML:** Renderiza archivos de texto plano o páginas web HTML directamente a PDF.
- **Desde el portapapeles:** Pega cualquier captura o imagen del portapapeles como una nueva página de PDF.
- **Desde escáner:** Compatible con escáneres compatibles con Windows WIA para digitalizar páginas por lotes.

---

### 6. Anotaciones de Estudio y Dibujo Libre
- **Lápiz / Trazo libre (`P`):** Dibuja trazos, anotaciones manuscritas o flechas directamente sobre la hoja.
- **Anotaciones de estudio:**
  - **Resaltador fluorescente (`Shift+H`):** Marca párrafos e ideas clave en amarillo brillante.
  - **Subrayado (`Shift+U`):** Subraya frases o líneas en azul.
  - **Tachado (`Shift+K`):** Tacha fragmentos en rojo para revisiones o correcciones.
  - **Notas adhesivas / Comentarios (`N`):** Inserta comentarios con autor y fecha.
- **Inspección rápida al pasar el ratón (Tooltips):** Muestra autor y contenido al pasar el cursor sobre cualquier anotación.

---

### 7. Formularios Interactivos (AcroForms)
- **Completar campos de formulario:** Diálogo ordenado para rellenar campos de texto, casillas de verificación (*checkboxes*) y desplegables.
- **Aplanar formulario (*Flatten*):** Convierte todos los campos editables en texto estático integrado, impidiendo alteraciones posteriores.

---

### 8. Reconocimiento Óptico de Caracteres (OCR)
- **Motor Tesseract integrado:** No requiere instalar programas externos ni configurar variables de entorno.
- **Modelos multilingües incluidos:** Soporta español (`spa`) e inglés (`eng`) empaquetados localmente (**Español predeterminado**).
- **Capa de texto invisible:** Convierte PDFs escaneados o imágenes en documentos con texto seleccionable, copiable y editable con la herramienta de texto (`T`).
- **Máxima precisión por defecto:** Preconfigurado por omisión a **300 DPI** para esquemas técnicos, tablas y letras pequeñas.

---

### 9. Exportar y Convertir
- **A Microsoft Word (.docx):** Convierte el PDF a documento de Word editable conservando párrafos, columnas y formato.
- **A Microsoft Excel (.xlsx):** Detecta tablas y estructuras tabulares y las exporta a hojas de cálculo organizadas.
- **A Imágenes de alta resolución:** Exporta páginas completas a PNG o JPG con resolución configurable (72 a 300 DPI).
- **A Texto (.txt) y HTML:** Extrae el contenido en formato texto plano estructurado o página web navegable.

---

### 10. Optimización y Reducción de Tamaño
- **Recompresión de imágenes:** Reduce imágenes internas convirtiéndolas a JPEG con nivel de calidad (0-100%) y resolución límite (DPI).
- **Limpieza de metadatos:** Elimina metadatos ocultos para máxima privacidad.
- **Garbage collection & Deflate:** Elimina flujos no referenciados, fuentes huérfanas y compacta las tablas internas de objetos.

---

## Estructura del Proyecto

```
Editor portable/
├── .venv/                      # Entorno virtual de desarrollo Python
├── app/                        # Módulos del núcleo de la aplicación
│   ├── __init__.py             # Inicializador del paquete
│   ├── annotations.py          # Gestión de comentarios, resaltados, notas y trazos de tinta
│   ├── attachments.py          # Explorador, extracción y gestión segura de adjuntos embebidos
│   ├── background.py           # Tareas asíncronas en segundo plano (QThread)
│   ├── content_ops.py          # Edición in situ, censura, texto, imágenes y reemplazo limpio
│   ├── conversion.py           # Conversores a Word (.docx), Excel (.xlsx), HTML, TXT, imágenes
│   ├── creation.py             # Motor de creación de PDFs (Office, imágenes, escáner, web)
│   ├── dialogs.py              # Formularios y ventanas modales de interacción
│   ├── doc_tab.py              # Controlador de pestaña, árbol de comentarios, banner de seguridad y Undo/Redo
│   ├── forms.py                # Gestión, inspección y aplanado de AcroForms
│   ├── main_window.py          # Ventana principal, menús, barras de herramientas y atajos
│   ├── ocr.py                  # Integración del motor de OCR Tesseract de PyMuPDF
│   ├── operations.py           # Manipulación de páginas (rotar, dividir, bates, marcas)
│   ├── optimizer.py            # Motor de compresión y reducción de tamaño
│   ├── search_bar.py           # Barra de búsqueda flotante interactiva estilo navegador
│   ├── security.py             # Escáner pasivo de amenazas, sanitización, anti-phishing y privacidad
│   ├── selection_popup.py      # Mini-burbuja flotante de acciones rápidas sobre texto
│   ├── viewer.py               # Canvas gráfico, zoom, hipervínculos, selección fluida y eventos
│   └── welcome.py              # Pantalla de bienvenida minimalista y documentos recientes (<1 ms)
├── data/                       # Recursos estáticos de la aplicación
│   ├── tessdata/               # Modelos entrenados de OCR (spa.traineddata, eng.traineddata)
│   ├── app_icon.ico            # Icono oficial para el ejecutable y accesos directos
│   ├── app_icon.png            # Icono en alta resolución para la ventana y barra de tareas
│   └── splash.png              # Pantalla de carga nativa en C para arranque instantáneo
├── dist/                       # Distribución portable empaquetada
│   └── EditorPDFPortable/      # CARPETA PORTABLE (la que se copia a un pendrive)
│       ├── _internal/          # Binarios congelados y librerías C++
│       └── EditorPDFPortable.exe
├── tests/                      # Suite de pruebas automatizadas y muestras
│   ├── muestra.pdf             # PDF de muestra para pruebas
│   └── test_suite.py           # Suite automatizada integral (10 fases de validación)
├── .gitignore                  # Reglas de exclusión de archivos temporales y compilados
├── Abrir_EditorPortable.bat    # Lanzador de la versión portable compilada
├── build_portable.py           # Script para volver a compilar el portable con PyInstaller + Splash nativo
├── EditorPDFPortable.spec      # Configuración de compilación PyInstaller
├── main.py                     # Punto de entrada para ejecución desde código fuente con splash
├── README.md                   # Documentación y manual de usuario completo
├── requirements.txt            # Dependencias del proyecto
└── run.bat                     # Lanzador del entorno de desarrollo
```

---

## Atajos de Teclado Principales

| Atajo | Acción |
| :--- | :--- |
| `Ctrl + O` | Abrir documento PDF |
| `Ctrl + S` | Guardar cambios |
| `Ctrl + Shift + S` | Guardar como... |
| `Ctrl + P` | Imprimir documento |
| `Ctrl + W` | Cerrar pestaña activa |
| `Ctrl + N` | Crear nuevo PDF |
| `Ctrl + Shift + N` | Combinar archivos en un PDF |
| `Ctrl + Z` | Deshacer última acción |
| `Ctrl + Y` | Rehacer última acción |
| `Ctrl + C` | Copiar texto seleccionado al portapapeles |
| `Ctrl + A` | Seleccionar todo el texto de la página actual |
| `Ctrl + F` | Abrir buscador de texto flotante |
| `Esc` | Cerrar buscador / Cancelar selección de texto |
| `F3` / `Shift + F3` | Coincidencia siguiente / anterior en búsqueda |
| `F4` | Mostrar / ocultar panel lateral |
| `Ctrl + Shift + A` | Ver y gestionar archivos adjuntos embebidos |
| `Ctrl + +` / `Ctrl + -` | Aumentar / reducir zoom |
| `Ctrl + Rueda Ratón` | Zoom interactivo centrado en cursor |
| `Ctrl + 1` | Ajustar vista al ancho de página |
| `Ctrl + 2` | Ajustar vista a página completa |
| `Espacio` / `Shift + Espacio` | Avanzar / retroceder pantalla en lectura |
| `H` | Herramienta Mano (desplazamiento) |
| `V` | Herramienta Seleccionar y copiar texto (con pastilla flotante) |
| `T` | Herramienta Texto (editar in situ o insertar nuevo) |
| `R` | Herramienta Censurar / Redactar por área |
| `I` | Insertar imagen |
| `Shift + F` | Estampar firma manuscrita personal |
| `L` | Insertar hipervínculo |
| `P` | Herramienta Lápiz / Trazo libre a mano alzada |
| `Shift + H` | Resaltar texto o área seleccionada |
| `Shift + U` | Subrayar texto o área |
| `Shift + K` | Tachar texto o área |
| `N` | Insertar nota adhesiva o comentario |
| `Supr` (Delete) | Eliminar páginas seleccionadas |
| `Alt + Arriba / Abajo` | Mover páginas seleccionadas hacia arriba o abajo |
| `Ctrl + Shift + Izq / Der` | Girar páginas seleccionadas 90° |

---

## Suite de Pruebas Automatizadas

El proyecto incluye una suite de validación automatizada que comprueba todas las operaciones de páginas, edición in situ, motor de OCR, conversiones a formatos externos, compresión, anotaciones, formularios, adjuntos embebidos y **seguridad/anti-phishing**:

```powershell
.\.venv\Scripts\python.exe tests\test_suite.py
```

---

## Recompilación de la Versión Portable

Si en el futuro modificas algún archivo dentro de `app/` y deseas actualizar el ejecutable de `dist\EditorPDFPortable`, simplemente ejecuta:
```powershell
.\.venv\Scripts\python.exe build_portable.py
```
El script invocará a PyInstaller con los parámetros, iconos, splash nativo y carpetas de datos configurados y actualizará `EditorPDFPortable.exe` automáticamente sin dejar residuos en el directorio.
