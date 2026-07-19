"""Almacenamiento local de entregas y calificaciones de tareas."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from gesaula.actions.guardar_cuestionarios import (
    resolver_carpeta_alumno,
    sanitizar_nombre_ruta,
)
from gesaula.moodle.models import (
    ActividadDescargable,
    AdjuntoRevision,
    EntregaTarea,
)


@dataclass(frozen=True)
class TareaConEntregas:
    """Tarea y alumnos encontrados en todas sus páginas de Entregas."""

    actividad: ActividadDescargable
    entregas: tuple[EntregaTarea, ...]


def preparar_carpetas_tarea(
    destino: str | Path,
    actividad: ActividadDescargable,
    entregas: tuple[EntregaTarea, ...],
) -> tuple[Path, ...]:
    """Crea una carpeta alumno/tarea incluso cuando no exista entrega."""
    carpetas: dict[Path, None] = {}
    for entrega in entregas:
        carpeta = _carpeta_entrega(destino, actividad, entrega)
        carpeta.mkdir(parents=True, exist_ok=True)
        carpetas.setdefault(carpeta, None)
    return tuple(carpetas)


def guardar_entrega_tarea(
    destino: str | Path,
    actividad: ActividadDescargable,
    entrega: EntregaTarea,
    html_texto: tuple[str, str] | None,
    html_calificacion: tuple[str, str] | None,
    archivos: tuple[tuple[AdjuntoRevision, bytes], ...],
) -> Path:
    """Guarda resumen, texto, calificación, rúbrica y ficheros disponibles."""
    carpeta = _carpeta_entrega(destino, actividad, entrega)
    carpeta.mkdir(parents=True, exist_ok=True)
    carpeta_archivos = carpeta / "archivos"

    nombres_usados: set[str] = set()
    rutas_locales: dict[str, str] = {}
    for archivo, contenido in archivos:
        nombre = _nombre_unico(
            sanitizar_nombre_ruta(archivo.nombre),
            nombres_usados,
        )
        carpeta_archivos.mkdir(parents=True, exist_ok=True)
        (carpeta_archivos / nombre).write_bytes(contenido)
        rutas_locales[archivo.url] = f"archivos/{nombre}"

    resumen = f"<html><body><table>{entrega.html_resumen}</table></body></html>"
    _guardar_html(
        carpeta / "entrega.html",
        resumen,
        entrega.url_calificacion,
        rutas_locales,
    )
    if html_texto is not None:
        _guardar_html(
            carpeta / "texto-entrega.html",
            html_texto[0],
            html_texto[1],
            rutas_locales,
        )
    if html_calificacion is not None:
        _guardar_html(
            carpeta / "calificacion.html",
            html_calificacion[0],
            html_calificacion[1],
            rutas_locales,
        )
    return carpeta


def _guardar_html(
    ruta: Path,
    html: str,
    url_pagina: str,
    rutas_locales: dict[str, str],
) -> None:
    soup = BeautifulSoup(html, "html.parser")
    for elemento in soup.select("[href], [src]"):
        atributo = "href" if elemento.has_attr("href") else "src"
        url = urljoin(url_pagina, str(elemento.get(atributo, "")))
        if url in rutas_locales:
            elemento[atributo] = rutas_locales[url]
    ruta.write_text(str(soup), encoding="utf-8")


def _carpeta_entrega(
    destino: str | Path,
    actividad: ActividadDescargable,
    entrega: EntregaTarea,
) -> Path:
    return (
        resolver_carpeta_alumno(
            destino,
            entrega.alumno_id,
            entrega.alumno,
        )
        / sanitizar_nombre_ruta(actividad.nombre)
    )


def _nombre_unico(nombre: str, usados: set[str]) -> str:
    candidato = nombre
    base = Path(nombre).stem
    sufijo = Path(nombre).suffix
    numero = 2
    while candidato.casefold() in usados:
        candidato = f"{base}-{numero}{sufijo}"
        numero += 1
    usados.add(candidato.casefold())
    return candidato
