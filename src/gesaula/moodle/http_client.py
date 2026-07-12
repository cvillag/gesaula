"""Implementación HTTP de la sesión web de Moodle."""

from urllib.parse import urlparse

import httpx

from gesaula.moodle.errors import ErrorConexionMoodle, MoodleEnMantenimiento
from gesaula.moodle.parsers import MENSAJE_MANTENIMIENTO, esta_en_mantenimiento

TIEMPO_ESPERA = 10.0


def comprobar_url(url: str) -> str:
    """Comprueba que una URL web responde y devuelve su dirección final."""
    url = url.strip()
    partes = urlparse(url)
    if partes.scheme not in {"http", "https"} or not partes.netloc:
        raise ErrorConexionMoodle(
            "Introduce una URL completa que comience por http:// o https://."
        )

    try:
        respuesta = httpx.get(url, follow_redirects=True, timeout=TIEMPO_ESPERA)
    except httpx.TimeoutException as error:
        raise ErrorConexionMoodle(
            f"El servidor no respondió en {TIEMPO_ESPERA:g} segundos."
        ) from error
    except httpx.RequestError as error:
        raise ErrorConexionMoodle(f"No se pudo conectar: {error}") from error

    if esta_en_mantenimiento(respuesta.text):
        raise MoodleEnMantenimiento(f"{MENSAJE_MANTENIMIENTO}.")

    if respuesta.is_error:
        raise ErrorConexionMoodle(
            f"El servidor respondió con el estado HTTP {respuesta.status_code}."
        )

    return str(respuesta.url)
