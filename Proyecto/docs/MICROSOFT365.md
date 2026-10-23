# Creación de PDFs con Microsoft 365 de escritorio

El editor permite crear documentos PDF a partir de archivos de Microsoft 365 (Word, Excel y PowerPoint) usando las aplicaciones locales mediante COM y pywin32. No envía documentos a servicios externos ni utiliza software de terceros para la conversión: todo el procesamiento es estrictamente local en el equipo del usuario.

## Motores utilizados

| Operación | Implementación |
|---|---|
| Word → PDF | `Documents.Open` como sólo lectura y `ExportAsFixedFormat` al formato 17. |
| Excel → PDF | `Workbooks.Open` sin actualizar enlaces, sólo lectura, cálculo manual; `ExportAsFixedFormat` tipo 0. |
| PowerPoint → PDF | `Presentations.Open` como sólo lectura, sin ventana; `SaveAs` al formato 32. |

El editor está enfocado exclusivamente en la lectura, edición y manipulación de PDFs. La única exportación disponible desde el visor es a imágenes (PNG/JPEG).

## Aislamiento y guardado

- Cada trabajo COM corre en un proceso creado con `multiprocessing.spawn`, inicializado como STA. Los objetos PDF y COM no se comparten entre hilos o procesos.
- Un mutex por aplicación serializa las operaciones entre distintas instancias del editor, incluyendo la activación de PowerPoint.
- Word y Excel se crean con `DispatchEx`. Se identifica la instancia creada antes de abrir el archivo de entrada. PowerPoint es MultiUse: si ya hay un proceso abierto se rechaza el trabajo antes de conectarse a él.
- Se solicita `AutomationSecurity = 3`, se desactivan eventos de Excel y se evita actualizar enlaces al abrir. No se alteran políticas del Centro de confianza ni se aceptan sus avisos.
- Un timeout termina el trabajador si la aplicación queda bloqueada. La limpieza de Office valida PID, hora de creación y nombre de la instancia registrada; nunca finaliza aplicaciones por nombre de forma global.
- La salida a PDF se escribe en un temporal aislado y se valida su estructura antes de publicar el archivo final. Un fallo conserva intacto cualquier destino anterior.

## Dependencias

Se requieren Microsoft 365 de escritorio para Windows, activación válida y las aplicaciones correspondientes (`WINWORD.EXE`, `EXCEL.EXE`, `POWERPNT.EXE`). La versión web de Microsoft 365 no sustituye las aplicaciones locales.

`pywin32` y `psutil` se distribuyen con el ejecutable portable. Microsoft 365 no se incluye en el paquete; el editor funciona de forma totalmente autónoma para leer, editar, anotar, firmar, comprimir, aplicar OCR y exportar a imágenes sin necesidad de tener Office instalado.

## Uso y diagnóstico

Para crear un PDF desde un archivo de Office, usá **Crear PDF desde archivos…** (`Ctrl + N`) o arrastrá el archivo compatible al editor; el resultado se genera en un PDF nuevo que podés revisar y guardar con `Ctrl + S`.

| Problema | Qué revisar |
|---|---|
| No se inicia la aplicación de Office. | Abrila manualmente y comprobá su activación y que no esté esperando configuración inicial. La suscripción web no sustituye la instalación local. |
| PowerPoint ya está abierto. | Guardá tus presentaciones, cerrá PowerPoint y reintentá. |
| Excel exporta un PDF con contenido recortado. | Revisá los anchos de columna, el área de impresión y la escala del archivo de origen en Excel. |
| La conversión supera el tiempo máximo. | Revisá contraseñas, avisos pendientes de Office y restricciones corporativas. |

## Referencias

- [Seguridad de automatización de Excel y límite con macros XLM](https://learn.microsoft.com/en-us/office/vba/api/excel.application.automationsecurity).
- [Seguridad de automatización de PowerPoint](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.application.automationsecurity).
- [Instancias SingleUse y MultiUse de Office](https://learn.microsoft.com/en-us/previous-versions/office/troubleshoot/office-developer/use-visual-c-automate-run-program-instance).
