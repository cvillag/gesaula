"""Lectura y escritura de configuración local."""

from PySide6.QtCore import QSettings

CLAVE_URLS_RECIENTES = "conexion/urls_recientes"
CLAVE_USUARIOS_RECIENTES = "conexion/usuarios_recientes"
MAX_ELEMENTOS_RECIENTES = 5


def _cargar_lista(clave: str, ajustes: QSettings) -> list[str]:
    """Carga una lista de textos desde QSettings."""
    valor = ajustes.value(clave, [])
    if isinstance(valor, str):
        elementos = [valor] if valor else []
    else:
        elementos = [str(elemento) for elemento in valor]
    return elementos[:MAX_ELEMENTOS_RECIENTES]


def _guardar_reciente(elemento: str, clave: str, ajustes: QSettings) -> list[str]:
    """Guarda un texto reciente sin duplicados."""
    elementos = _cargar_lista(clave, ajustes)
    elementos = [
        elemento,
        *(guardado for guardado in elementos if guardado != elemento),
    ][:MAX_ELEMENTOS_RECIENTES]
    ajustes.setValue(clave, elementos)
    ajustes.sync()
    return elementos


def cargar_urls_recientes(ajustes: QSettings | None = None) -> list[str]:
    """Carga las URL correctas desde la más reciente."""
    ajustes = ajustes if ajustes is not None else QSettings("gesaula", "gesaula")
    return _cargar_lista(CLAVE_URLS_RECIENTES, ajustes)


def guardar_url_reciente(url: str, ajustes: QSettings | None = None) -> list[str]:
    """Guarda una URL sin duplicados y devuelve el historial actualizado."""
    ajustes = ajustes if ajustes is not None else QSettings("gesaula", "gesaula")
    return _guardar_reciente(url, CLAVE_URLS_RECIENTES, ajustes)


def cargar_usuarios_recientes(ajustes: QSettings | None = None) -> list[str]:
    """Carga los usuarios correctos desde el más reciente."""
    ajustes = ajustes if ajustes is not None else QSettings("gesaula", "gesaula")
    return _cargar_lista(CLAVE_USUARIOS_RECIENTES, ajustes)


def guardar_usuario_reciente(
    usuario: str, ajustes: QSettings | None = None
) -> list[str]:
    """Guarda un usuario sin duplicados y devuelve el historial actualizado."""
    ajustes = ajustes if ajustes is not None else QSettings("gesaula", "gesaula")
    return _guardar_reciente(usuario, CLAVE_USUARIOS_RECIENTES, ajustes)
