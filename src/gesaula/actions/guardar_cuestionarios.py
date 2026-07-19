"""Preparación y almacenamiento local de revisiones de cuestionarios."""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from gesaula.moodle.models import (
    ActividadDescargable,
    AdjuntoRevision,
    IntentoCuestionario,
)


@dataclass(frozen=True)
class CuestionarioConIntentos:
    """Cuestionario y sus intentos disponibles."""

    actividad: ActividadDescargable
    intentos: tuple[IntentoCuestionario, ...]


@dataclass(frozen=True)
class InventarioCuestionarios:
    """Resumen calculado antes de iniciar las descargas."""

    cuestionarios: tuple[CuestionarioConIntentos, ...]
    total_alumnos: int
    total_intentos: int


def crear_inventario_cuestionarios(
    cuestionarios: tuple[CuestionarioConIntentos, ...],
) -> InventarioCuestionarios:
    """Cuenta alumnos únicos e intentos en los cuestionarios analizados."""
    alumnos = {
        (
            f"id:{intento.alumno_id}"
            if intento.alumno_id is not None
            else f"nombre:{_clave_nombre(intento.alumno)}"
        )
        for cuestionario in cuestionarios
        for intento in cuestionario.intentos
    }
    return InventarioCuestionarios(
        cuestionarios=cuestionarios,
        total_alumnos=len(alumnos),
        total_intentos=sum(
            len(cuestionario.intentos) for cuestionario in cuestionarios
        ),
    )


def guardar_revision_cuestionario(
    destino: str | Path,
    actividad: ActividadDescargable,
    intento: IntentoCuestionario,
    html: str,
    adjuntos: tuple[tuple[AdjuntoRevision, bytes], ...],
) -> Path:
    """Guarda una revisión y adapta los enlaces de sus adjuntos locales."""
    carpeta = (
        resolver_carpeta_alumno(
            destino,
            intento.alumno_id,
            intento.alumno,
        )
        / sanitizar_nombre_ruta(actividad.nombre)
        / f"intento-{intento.id}"
    )
    carpeta_adjuntos = carpeta / "archivos"
    carpeta.mkdir(parents=True, exist_ok=True)

    nombres_usados: set[str] = set()
    rutas_locales: dict[str, str] = {}
    for adjunto, contenido in adjuntos:
        nombre = _nombre_unico(
            sanitizar_nombre_ruta(adjunto.nombre),
            nombres_usados,
        )
        carpeta_adjuntos.mkdir(parents=True, exist_ok=True)
        (carpeta_adjuntos / nombre).write_bytes(contenido)
        rutas_locales[adjunto.url] = f"archivos/{nombre}"

    soup = BeautifulSoup(html, "html.parser")
    for elemento in soup.select("[href], [src]"):
        atributo = "href" if elemento.has_attr("href") else "src"
        url_absoluta = urljoin(
            intento.url_revision,
            str(elemento.get(atributo, "")),
        )
        ruta_local = rutas_locales.get(url_absoluta)
        if ruta_local is not None:
            elemento[atributo] = ruta_local

    ruta_html = carpeta / "revision.html"
    ruta_html.write_text(str(soup), encoding="utf-8")
    return ruta_html


def preparar_carpetas_cuestionario(
    destino: str | Path,
    actividad: ActividadDescargable,
    intentos: tuple[IntentoCuestionario, ...],
) -> tuple[Path, ...]:
    """Crea las carpetas alumno/cuestionario antes de descargar revisiones."""
    carpetas: dict[Path, None] = {}
    for intento in intentos:
        carpeta = (
            resolver_carpeta_alumno(
                destino,
                intento.alumno_id,
                intento.alumno,
            )
            / sanitizar_nombre_ruta(actividad.nombre)
        )
        carpeta.mkdir(parents=True, exist_ok=True)
        carpetas.setdefault(carpeta, None)
    return tuple(carpetas)


def sanitizar_nombre_ruta(nombre: str) -> str:
    """Convierte un nombre Moodle en un componente de ruta portable."""
    nombre = unicodedata.normalize("NFC", nombre)
    nombre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nombre)
    nombre = " ".join(nombre.split()).strip(" .")
    if nombre in {"", ".", ".."}:
        nombre = "sin-nombre"
    return nombre[:120].rstrip(" .") or "sin-nombre"


def resolver_carpeta_alumno(
    destino: str | Path,
    alumno_id: int | None,
    nombre: str,
) -> Path:
    """Reutiliza la carpeta del mismo usuario aunque varíe su nombre visible."""
    raiz = Path(destino)
    nombre_seguro = sanitizar_nombre_ruta(nombre)
    if alumno_id is None:
        return raiz / nombre_seguro

    sufijo = f" [usuario-{alumno_id}]"
    carpeta_preferida = raiz / f"{nombre_seguro}{sufijo}"
    if carpeta_preferida.is_dir():
        return carpeta_preferida
    if raiz.is_dir():
        existentes = sorted(
            (
                ruta
                for ruta in raiz.iterdir()
                if ruta.is_dir() and ruta.name.endswith(sufijo)
            ),
            key=lambda ruta: ruta.name.casefold(),
        )
        if existentes:
            return existentes[0]
    return carpeta_preferida


def _clave_nombre(nombre: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", nombre.casefold())
    return "".join(
        caracter
        for caracter in descompuesto
        if not unicodedata.combining(caracter) and caracter.isalnum()
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
