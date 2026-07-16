"""Lectura independiente de exportaciones de calificaciones en formato ODS."""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from gesaula.moodle.models import AlumnoLevelUp

ESPACIO_NOMBRES = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}
ATRIBUTO_REPETICIONES = (
    f"{{{ESPACIO_NOMBRES['table']}}}number-columns-repeated"
)
ATRIBUTO_TIPO = f"{{{ESPACIO_NOMBRES['office']}}}value-type"
ATRIBUTO_VALOR = f"{{{ESPACIO_NOMBRES['office']}}}value"
ATRIBUTO_NOMBRE_TABLA = f"{{{ESPACIO_NOMBRES['table']}}}name"

CABECERAS_PERSONALES = {
    "nombre",
    "apellido s",
    "numero de id",
    "institucion",
    "departamento",
    "direccion de correo",
}
CABECERAS_METADATOS = {"ultima descarga de este curso"}


class ErrorArchivoCalificaciones(ValueError):
    """El archivo no tiene una exportación de calificaciones utilizable."""


class ErrorPreparacionCalificaciones(ValueError):
    """Las calificaciones no se pueden asociar con seguridad al alumnado."""


@dataclass(frozen=True)
class ColumnaCalificacion:
    """Columna seleccionable dentro de la hoja."""

    indice: int
    nombre: str


@dataclass(frozen=True)
class AlumnoCalificaciones:
    """Alumno y calificaciones encontradas en el ODS."""

    nombre: str
    apellidos: str
    correo: str
    calificaciones: tuple[float | None, ...]

    @property
    def nombre_completo(self) -> str:
        return " ".join(f"{self.nombre} {self.apellidos}".split())


@dataclass(frozen=True)
class InformeCalificaciones:
    """Contenido relevante de una exportación de calificaciones."""

    hoja: str
    columnas: tuple[ColumnaCalificacion, ...]
    alumnos: tuple[AlumnoCalificaciones, ...]


@dataclass(frozen=True)
class SeleccionCalificaciones:
    """Parámetros elegidos para una futura aplicación de PX."""

    columnas: tuple[ColumnaCalificacion, ...]
    multiplicador: int


@dataclass(frozen=True)
class IncrementoExperiencia:
    """Incremento de PX listo para enviarse a un alumno Moodle."""

    alumno_id: int
    context_id: int
    nombre: str
    incremento: int
    nuevo_total: int


@dataclass(frozen=True)
class PlanCalificaciones:
    """Actualizaciones validadas antes de modificar Moodle."""

    incrementos: tuple[IncrementoExperiencia, ...]
    alumnos_sin_calificacion: int


@dataclass(frozen=True)
class _Celda:
    texto: str
    tipo: str | None
    valor: str | None


def leer_calificaciones_ods(ruta: str | Path) -> InformeCalificaciones:
    """Lee la primera hoja que contenga nombre, apellidos y calificaciones."""
    ruta = Path(ruta)
    try:
        with ZipFile(ruta) as archivo:
            contenido = archivo.read("content.xml")
    except FileNotFoundError as error:
        raise ErrorArchivoCalificaciones("El archivo seleccionado no existe.") from error
    except (BadZipFile, KeyError) as error:
        raise ErrorArchivoCalificaciones(
            "El archivo no es una hoja de cálculo ODS válida."
        ) from error

    try:
        raiz = ElementTree.fromstring(contenido)
    except ElementTree.ParseError as error:
        raise ErrorArchivoCalificaciones(
            "No se pudo interpretar el contenido XML del archivo ODS."
        ) from error

    errores: list[str] = []
    for hoja in raiz.findall(".//table:table", ESPACIO_NOMBRES):
        filas = _extraer_filas(hoja)
        if not filas:
            continue
        try:
            return _convertir_hoja(
                str(hoja.get(ATRIBUTO_NOMBRE_TABLA, "Calificaciones")),
                filas,
            )
        except ErrorArchivoCalificaciones as error:
            errores.append(str(error))

    detalle = errores[0] if errores else "El archivo no contiene hojas con datos."
    raise ErrorArchivoCalificaciones(detalle)


def normalizar_nombre(texto: str) -> str:
    """Normaliza un nombre para poder compararlo sin perder seguridad."""
    descompuesto = unicodedata.normalize("NFKD", texto.casefold())
    sin_tildes = "".join(
        caracter
        for caracter in descompuesto
        if not unicodedata.combining(caracter)
    )
    return " ".join(re.findall(r"[a-z0-9]+", sin_tildes))


def preparar_plan_calificaciones(
    informe: InformeCalificaciones,
    seleccion: SeleccionCalificaciones,
    alumnos_level_up: tuple[AlumnoLevelUp, ...],
) -> PlanCalificaciones:
    """Relaciona alumnos de forma exacta y calcula los incrementos de PX."""
    if not seleccion.columnas:
        raise ErrorPreparacionCalificaciones(
            "Debe seleccionar al menos una columna de calificación."
        )
    if (
        not isinstance(seleccion.multiplicador, int)
        or isinstance(seleccion.multiplicador, bool)
        or seleccion.multiplicador <= 0
    ):
        raise ErrorPreparacionCalificaciones(
            "El multiplicador debe ser un número entero positivo."
        )

    posiciones = {
        columna: posicion
        for posicion, columna in enumerate(informe.columnas)
    }
    try:
        posiciones_seleccionadas = tuple(
            posiciones[columna] for columna in seleccion.columnas
        )
    except KeyError as error:
        raise ErrorPreparacionCalificaciones(
            "La selección contiene una columna que no pertenece al archivo."
        ) from error

    nombres_ods = [
        normalizar_nombre(alumno.nombre_completo)
        for alumno in informe.alumnos
    ]
    nombres_moodle = [
        normalizar_nombre(alumno.nombre)
        for alumno in alumnos_level_up
    ]
    repeticiones_ods = Counter(nombres_ods)
    repeticiones_moodle = Counter(nombres_moodle)
    moodle_por_nombre = {
        nombre: alumno
        for nombre, alumno in zip(
            nombres_moodle,
            alumnos_level_up,
            strict=True,
        )
        if nombre and repeticiones_moodle[nombre] == 1
    }

    incrementos: list[IncrementoExperiencia] = []
    sin_calificacion = 0
    sin_coincidencia = 0
    ambiguos = 0
    sin_contexto = 0
    for alumno_ods, nombre_normalizado in zip(
        informe.alumnos,
        nombres_ods,
        strict=True,
    ):
        notas = tuple(
            alumno_ods.calificaciones[posicion]
            for posicion in posiciones_seleccionadas
        )
        notas_presentes = tuple(nota for nota in notas if nota is not None)
        if not notas_presentes:
            sin_calificacion += 1
            continue
        if (
            not nombre_normalizado
            or repeticiones_ods[nombre_normalizado] != 1
            or repeticiones_moodle[nombre_normalizado] > 1
        ):
            ambiguos += 1
            continue

        alumno_moodle = moodle_por_nombre.get(nombre_normalizado)
        if alumno_moodle is None:
            sin_coincidencia += 1
            continue
        if alumno_moodle.context_id is None:
            sin_contexto += 1
            continue

        incremento = sum(
            ceil(nota * seleccion.multiplicador)
            for nota in notas_presentes
        )
        if incremento <= 0:
            sin_calificacion += 1
            continue
        incrementos.append(
            IncrementoExperiencia(
                alumno_id=alumno_moodle.id,
                context_id=alumno_moodle.context_id,
                nombre=alumno_moodle.nombre,
                incremento=incremento,
                nuevo_total=alumno_moodle.px + incremento,
            )
        )

    problemas = []
    if sin_coincidencia:
        problemas.append(f"{sin_coincidencia} sin coincidencia en Level up")
    if ambiguos:
        problemas.append(f"{ambiguos} con nombre duplicado o ambiguo")
    if sin_contexto:
        problemas.append(f"{sin_contexto} sin contexto Moodle")
    if problemas:
        raise ErrorPreparacionCalificaciones(
            "No se puede iniciar la actualización: " + "; ".join(problemas) + "."
        )
    if not incrementos:
        raise ErrorPreparacionCalificaciones(
            "Ningún alumno tiene calificaciones numéricas en las columnas seleccionadas."
        )
    return PlanCalificaciones(
        incrementos=tuple(incrementos),
        alumnos_sin_calificacion=sin_calificacion,
    )


def _convertir_hoja(
    nombre_hoja: str,
    filas: list[list[_Celda]],
) -> InformeCalificaciones:
    cabeceras = [celda.texto.strip() for celda in filas[0]]
    cabeceras_normalizadas = [normalizar_nombre(cabecera) for cabecera in cabeceras]
    indice_nombre = _buscar_cabecera(cabeceras_normalizadas, {"nombre"})
    indice_apellidos = _buscar_cabecera(
        cabeceras_normalizadas,
        {"apellido s", "apellidos"},
    )
    indice_correo = _buscar_cabecera(
        cabeceras_normalizadas,
        {"direccion de correo", "correo", "email"},
        obligatoria=False,
    )
    indices_calificaciones = [
        indice
        for indice, cabecera in enumerate(cabeceras_normalizadas)
        if cabecera
        and cabecera not in CABECERAS_PERSONALES
        and cabecera not in CABECERAS_METADATOS
    ]
    if not indices_calificaciones:
        raise ErrorArchivoCalificaciones(
            "No se encontraron columnas de calificación en el archivo."
        )

    columnas = tuple(
        ColumnaCalificacion(indice=indice, nombre=cabeceras[indice])
        for indice in indices_calificaciones
    )
    alumnos: list[AlumnoCalificaciones] = []
    for fila in filas[1:]:
        nombre = _texto_celda(fila, indice_nombre)
        apellidos = _texto_celda(fila, indice_apellidos)
        if not nombre and not apellidos:
            continue
        alumnos.append(
            AlumnoCalificaciones(
                nombre=nombre,
                apellidos=apellidos,
                correo=(
                    _texto_celda(fila, indice_correo)
                    if indice_correo is not None
                    else ""
                ),
                calificaciones=tuple(
                    _valor_numerico(fila[indice]) if indice < len(fila) else None
                    for indice in indices_calificaciones
                ),
            )
        )
    if not alumnos:
        raise ErrorArchivoCalificaciones(
            "No se encontraron alumnos en el archivo de calificaciones."
        )
    return InformeCalificaciones(
        hoja=nombre_hoja,
        columnas=columnas,
        alumnos=tuple(alumnos),
    )


def _extraer_filas(hoja: ElementTree.Element) -> list[list[_Celda]]:
    filas: list[list[_Celda]] = []
    for fila_xml in hoja.findall("table:table-row", ESPACIO_NOMBRES):
        fila: list[_Celda] = []
        for celda_xml in fila_xml.findall("table:table-cell", ESPACIO_NOMBRES):
            repeticiones = min(int(celda_xml.get(ATRIBUTO_REPETICIONES, "1")), 10_000)
            celda = _Celda(
                texto=" ".join(
                    "".join(parrafo.itertext()).strip()
                    for parrafo in celda_xml.findall(
                        ".//text:p",
                        ESPACIO_NOMBRES,
                    )
                ).strip(),
                tipo=celda_xml.get(ATRIBUTO_TIPO),
                valor=celda_xml.get(ATRIBUTO_VALOR),
            )
            fila.extend([celda] * repeticiones)
        while fila and not fila[-1].texto and fila[-1].valor is None:
            fila.pop()
        if fila:
            filas.append(fila)
    return filas


def _buscar_cabecera(
    cabeceras: list[str],
    nombres: set[str],
    *,
    obligatoria: bool = True,
) -> int | None:
    indice = next(
        (posicion for posicion, cabecera in enumerate(cabeceras) if cabecera in nombres),
        None,
    )
    if indice is None and obligatoria:
        esperado = " o ".join(sorted(nombres))
        raise ErrorArchivoCalificaciones(
            f"No se encontró la columna obligatoria {esperado!r}."
        )
    return indice


def _texto_celda(fila: list[_Celda], indice: int | None) -> str:
    return fila[indice].texto.strip() if indice is not None and indice < len(fila) else ""


def _valor_numerico(celda: _Celda) -> float | None:
    if celda.tipo == "float" and celda.valor is not None:
        try:
            return float(celda.valor)
        except ValueError:
            return None
    texto = celda.texto.strip().replace(",", ".")
    if not texto or texto == "-":
        return None
    try:
        return float(texto)
    except ValueError:
        return None
