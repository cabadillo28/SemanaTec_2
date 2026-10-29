#!/usr/bin/env bash
# Clasificación por extensión y auditoría estática de PySide6. Requiere Bash 4+.
set -euo pipefail
export LC_ALL=C

fallar() { printf 'Error: %s\n' "$*" >&2; exit 1; }

# 1. Validar parámetros, entrada y destino antes de copiar nada.
if [[ $# -ne 2 ]]; then
    printf 'Uso: ./script.sh <archivo.zip> <directorio_destino>\n' >&2
    exit 1
fi
archivo_zip=$1
destino=$2
[[ -f "$archivo_zip" && -r "$archivo_zip" ]] || fallar 'El archivo ZIP no existe o no se puede leer.'
[[ "${archivo_zip,,}" == *.zip ]] || fallar 'El archivo debe tener extensión .zip.'
[[ -n "$destino" ]] || fallar 'La ruta del destino no puede estar vacía.'
for comando in unzip find grep mkdir mktemp cp rm sort; do
    command -v "$comando" >/dev/null || fallar "Falta el comando: $comando"
done
# Evitar que unzip confunda un nombre relativo como -archivo.zip con una opción.
[[ "$archivo_zip" == /* ]] || archivo_zip="$PWD/$archivo_zip"
[[ "$destino" == /* ]] || destino="$PWD/$destino"
while [[ "$destino" != / && "$destino" == */ ]]; do destino=${destino%/}; done
[[ ! -L "$destino" ]] || fallar 'El destino no puede ser un enlace simbólico.'
if [[ -e "$destino" ]]; then
    [[ -d "$destino" ]] || fallar 'El destino existe y no es una carpeta.'
    contenido=$(find "$destino" -mindepth 1 -print -quit) || fallar 'No se pudo revisar el destino.'
    [[ -z "$contenido" ]] || fallar 'El destino debe ser nuevo o estar vacío; no se sobrescribirá nada.'
fi

# 2. Crear un temporal privado. El trap nunca borra la carpeta destino.
temporal=$(mktemp -d "${TMPDIR:-/tmp}/organizador.XXXXXXXX")
trap 'rm -rf -- "$temporal"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Revisar el índice antes de extraer: rechazar rutas peligrosas y enlaces.
# unzip -Z representa ciertos caracteres de control con escapes en su listado;
# los nombres reales se recorren después con find -print0, no con ese listado.
vacio=0
if unzip -Z -l "$archivo_zip" >"$temporal/indice" 2>"$temporal/error"; then
    :
elif grep -Fq 'number of entries: 0' "$temporal/indice"; then
    vacio=1
else
    fallar 'El archivo no es un ZIP válido o no se pudo leer su índice.'
fi
mkdir -p -- "$temporal/extraido"
if (( vacio == 0 )); then
    if grep -q '^l' "$temporal/indice"; then
        fallar 'No se admiten enlaces simbólicos dentro del ZIP.'
    fi
    unzip -Z -1 "$archivo_zip" >"$temporal/nombres" || fallar 'No se pudieron listar las entradas del ZIP.'
    while IFS= read -r entrada; do
        case "/$entrada/" in
            */../*) fallar 'El ZIP contiene una ruta con ..' ;;
        esac
        case "$entrada" in
            /*|[A-Za-z]:*|*\\*) fallar 'El ZIP contiene una ruta absoluta o no admitida.' ;;
        esac
    done <"$temporal/nombres"
    # -P '' y stdin cerrado evitan quedar esperando una contraseña.
    unzip -P '' -tqq "$archivo_zip" </dev/null >"$temporal/prueba" 2>&1 \
        || fallar 'El ZIP está dañado, cifrado o no es compatible.'
    # -^ conserva nombres con saltos de línea; find -print0 los maneja completos.
    unzip -^ -P '' -qq "$archivo_zip" -d "$temporal/extraido" </dev/null \
        || fallar 'No se pudo descomprimir el ZIP.'
fi

# 3. Copiar por extensión conservando las rutas para evitar colisiones.
patron_mencion='(^|[^[:alnum:]_])PySide6([^[:alnum:]_]|$)'
mkdir -p -- "$destino" || fallar 'No se pudo crear el destino.'
destino=$(cd -- "$destino" && pwd -P)
find "$temporal/extraido" -type f -print0 | sort -z >"$temporal/archivos"
organizados=0
metadatos=0
while IFS= read -r -d '' origen; do
    relativo=${origen#"$temporal/extraido/"}
    nombre=${origen##*/}
    case "/$relativo" in
        */__MACOSX/*|*/._*|*/.DS_Store)
            categoria=metadatos_macos
            metadatos=$((metadatos + 1))
            ;;
        *)
            categoria=sin_extension
            sin_punto_inicial=${nombre#.}
            if [[ "$sin_punto_inicial" == *.* && -n "${nombre##*.}" ]]; then
                categoria=${nombre##*.}
                categoria=${categoria,,}
            fi
            organizados=$((organizados + 1))
            ;;
    esac
    # Los Python con menciones van a su subcarpeta, sin dejar copias duplicadas.
    if [[ "$categoria" == py ]]; then
        mkdir -p -- "$destino/py/con_pyside6"
        if grep -q -a -i -E -- "$patron_mencion" "$origen"; then
            categoria=py/con_pyside6
        else
            estado=$?
            [[ $estado -eq 1 ]] || fallar "No se pudo analizar: $origen"
        fi
    fi
    salida="$destino/$categoria/$relativo"
    mkdir -p -- "${salida%/*}"
    [[ ! -e "$salida" && ! -L "$salida" ]] || fallar "El archivo de salida ya existe: $salida"
    cp -- "$origen" "$salida"
done <"$temporal/archivos"

# 4. Auditar py/ y su subcarpeta con_pyside6/ una sola vez por archivo.
# Es una búsqueda de texto, no ejecuta Python ni demuestra uso en tiempo real.
patron_import='^[[:space:]]*(from[[:space:]]+PySide6[.[:space:]]|import[[:space:]]+([^#;]*,[[:space:]]*)?PySide6([.[:space:],;]|$))'
: >"$temporal/python"
if [[ -d "$destino/py" ]]; then
    find "$destino/py" -type f -print0 | sort -z >"$temporal/python"
fi
analizados=0
con_menciones=0
con_importaciones=0
printf '\nAUDITORÍA DE PYSIDE6\n'
while IFS= read -r -d '' archivo_py; do
    analizados=$((analizados + 1))
    printf '\nArchivo: %s\n' "$archivo_py"
    if grep -n -a -i -E -- "$patron_mencion" "$archivo_py" >"$temporal/menciones"; then
        con_menciones=$((con_menciones + 1))
        printf 'Contiene PySide6: sí\nCoincidencias (línea:texto):\n'
        # Imprimir sin modificar el texto encontrado por grep -n.
        while IFS= read -r linea || [[ -n "$linea" ]]; do
            printf '%s\n' "$linea"
        done <"$temporal/menciones"
    else
        estado=$?
        [[ $estado -eq 1 ]] || fallar "No se pudo analizar: $archivo_py"
        printf 'Contiene PySide6: no\n'
    fi
    if grep -n -a -i -E -- "$patron_import" "$archivo_py" >"$temporal/importaciones"; then
        con_importaciones=$((con_importaciones + 1))
        printf 'Líneas de importación de PySide6 detectadas (heurística):\n'
        while IFS= read -r linea || [[ -n "$linea" ]]; do
            printf '%s\n' "$linea"
        done <"$temporal/importaciones"
    else
        estado=$?
        [[ $estado -eq 1 ]] || fallar "No se pudieron revisar las importaciones: $archivo_py"
        printf 'No se detectaron importaciones de PySide6.\n'
    fi
done <"$temporal/python"

# 5. Contar archivos, no el número de líneas coincidentes.
printf '\nRESUMEN FINAL\nDestino: %s\n' "$destino"
printf 'Archivos de contenido organizados: %d\n' "$organizados"
printf 'Metadatos macOS separados: %d\n' "$metadatos"
printf 'Archivos .py analizados: %d\n' "$analizados"
printf 'Archivos con menciones de PySide6: %d\n' "$con_menciones"
printf 'Archivos con importaciones de PySide6 detectadas: %d\n' "$con_importaciones"
if [[ -d "$destino/py" ]]; then
    printf 'Subcarpeta de archivos con PySide6: %s\n' "$destino/py/con_pyside6"
fi
