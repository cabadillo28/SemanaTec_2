# Clasificación de archivos y auditoría de PySide6

Práctica en Bash: descomprimir un ZIP, ordenar su contenido por extensión y revisar los archivos Python buscando **PySide6**, en lugar del ejemplo `cv2` del enunciado.

## Ejecutar

Requisitos: Linux, Bash 4+, `unzip` de Info-ZIP (incluida su opción `-^`), `find`, `grep`, `mkdir`, `mktemp`, `cp`, `rm` y `sort`. No hay que instalar PySide6 ni ejecutar los programas Python del ZIP.

Desde la raíz del repositorio:

```bash
cd organizador_auditor
./script.sh "$HOME/Downloads/proyecto_analisis.zip" ./resultados_nueva
```

El script recibe exactamente dos argumentos:

```bash
./script.sh <archivo.zip> <directorio_destino>
```

El destino debe ser nuevo o estar vacío. La ejecución local generó `resultados/`, pero esa carpeta no se publica en Git. Para repetir una ejecución, elige un destino nuevo. Las rutas con espacios deben ir entre comillas.

Para guardar también lo que aparece en terminal:

```bash
set -o pipefail
./script.sh "$HOME/Downloads/proyecto_analisis.zip" ./otra_salida | tee evidencias/otra_auditoria.txt
```

## Qué hace

1. Valida los argumentos, la entrada, las dependencias y el destino.
2. Revisa el índice y la integridad del ZIP; rechaza rutas con `..`, rutas absolutas y enlaces simbólicos.
3. Descomprime con `unzip` en un temporal creado con `mktemp -d`; `trap` lo elimina al salir.
4. Usa `find -print0` para copiar los archivos a carpetas por su última extensión, normalizada a minúsculas. Conserva la ruta relativa para evitar colisiones.
5. Separa `__MACOSX`, `.DS_Store` y nombres `._*` bajo `metadatos_macos/`, sin contarlos como Python real.
6. Revisa solo `py/` con `grep -n -i -E`. Por cada archivo indica si hay PySide6 y muestra las líneas exactas y su número. También distingue las líneas de importación detectadas.
7. Imprime el resumen contando archivos, no coincidencias. No modifica el ZIP original ni sobrescribe resultados anteriores.

Ejemplo de organización:

```text
resultados/
├── py/proyecto_analisis/...
├── csv/proyecto_analisis/...
├── jpg/proyecto_analisis/...
├── png/proyecto_analisis/...
├── ...otras extensiones encontradas...
├── sin_extension/proyecto_analisis/...
└── metadatos_macos/...
```

## Resultado con el archivo del profesor

Entrada: `~/Downloads/proyecto_analisis.zip`.

| Dato | Resultado |
| --- | ---: |
| Archivos de contenido organizados | 98 |
| Metadatos macOS separados | 100 |
| Archivos Python analizados | 60 |
| Archivos con menciones de PySide6 | 28 |
| Archivos con líneas de importación de PySide6 detectadas | 28 |

- `QT_ex0.py`: importa `PySide6` en las líneas **2, 3 y 5**.
- `QT_interface_example.py`: importa `PySide6` en las líneas **45 y 51**; la línea **46** es una importación comentada y solo se cuenta como mención.
- `PyQT_button_window.py`: aunque su nombre dice PyQT, importa `PySide6` en la línea **2**, por lo que sí se cuenta.
- `QT_change_font.py`: importa `PyQt6`, una librería distinta, por lo que no se cuenta. Tampoco se cuentan `PySide2` ni nombres parecidos como `PySide60`; se revisa el contenido, no el nombre del archivo.

Extensiones encontradas: `csv`, `gif`, `jpeg`, `jpg`, `mp3`, `pdf`, `png`, `py`, `svg`, `ttf`, `wav` y `webp`, además de un archivo sin extensión.

Informe completo: [`evidencias/informe_auditoria.txt`](evidencias/informe_auditoria.txt).

## Prompts cortos

Los dos primeros prompts se conservan literalmente como historial: nombraban PyQt por una confusión inicial. La tercera instrucción corrige el objetivo a **PySide6**, que es la librería buscada en la versión actual.

Primera generación, enviada a un agente de IA en esta sesión ([texto exacto](prompts/01_generacion.txt)):

> Haz un script de Bash que reciba un ZIP y una carpeta destino, valide los datos, descomprima y ordene por extensión. Busca PyQt en los .py con grep -n y muestra un resumen. Separa los metadatos de Mac, no sobrescribas archivos y no hagas nada de Git.

Instrucción de ajuste aplicada por el agente principal durante la revisión ([texto exacto](prompts/02_ajuste.txt)):

> Usa unzip para descomprimir y deja todo el script en Bash. Muestra también los .py sin PyQt, distingue comentarios de imports y conserva las rutas. Revisa que el mensaje de uso sea correcto y que no se sobrescriban archivos.

La primera versión usaba Python para extraer el ZIP; se reemplazó por `unzip` para cumplir el enunciado. También se corrigió la salida por archivo y la distinción entre menciones e importaciones. No se usó una segunda conversación externa para estos ajustes.

Corrección posterior del usuario ([texto exacto](prompts/03_correccion_pyside6.txt)):

> it wasnt pyqt its pyside6 please fix it push commit etc

Se corrigieron los patrones y mensajes a PySide6, se añadió una prueba para excluir PyQt/PySide2 y nombres similares, y se repitió la auditoría del ZIP. Los resultados anteriores de 2 menciones de PyQt y 1 importación ya no describen la búsqueda actual: ahora se detectan **28 archivos con PySide6**.

## Pruebas

Python 3 se usa **solo para las pruebas**, que crean ZIP sintéticos. No es una dependencia de `script.sh`.

```bash
bash -n script.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Las 16 pruebas cubren argumentos, ZIP inválido o corrupto, rutas con espacios, extensiones en mayúsculas, nombres especiales, metadatos Mac, colisiones, destinos existentes, limpieza de temporales, errores de `grep`, comentarios, imports y ausencia de Python. Incluyen una regresión que exige detectar solo PySide6, excluyendo PyQt, PySide2, PySide60 y nombres similares, aunque el nombre del archivo sugiera otra librería.

Evidencias: [`pruebas.txt`](evidencias/pruebas.txt) y [`verificacion.txt`](evidencias/verificacion.txt).

## Límites y precauciones

La auditoría es estática y textual: una mención puede estar en un comentario o una cadena. Las importaciones se reconocen mediante una expresión regular para formas comunes de una línea; no es un analizador completo de Python y no detecta todos los imports dinámicos o multilínea. Tampoco demuestra que una librería se ejecute o esté instalada.

La clasificación sirve para auditar, no para ejecutar después el proyecto con sus rutas originales de recursos. Usar el ZIP de práctica de confianza; estas comprobaciones no son un sandbox ni limitan el tamaño descomprimido.

Los ejemplos originales de correo contienen credenciales escritas en el código. No se ejecutaron ni se reproducen aquí. No publiques `resultados/` ni el ZIP; antes de compartir esos ejemplos, elimina las credenciales y, si son reales, revócalas.

## Control de versiones

Repositorio: https://github.com/cabadillo28/SemanaTec_2

El trabajo se desarrolla en `feature/organizer-auditor` con commits separados para el script y para las pruebas y documentación. La integración en `main` se realiza mediante un merge, sin sobrescribir el historial existente.

Se versionan el script, las pruebas, los prompts y las evidencias de la auditoría. `.gitignore` deja fuera el ZIP y los archivos extraídos; no forman parte de la entrega publicada.
