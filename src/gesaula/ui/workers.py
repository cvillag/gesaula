"""Trabajos en segundo plano para no bloquear la interfaz."""

import base64
import binascii
from urllib.parse import unquote_to_bytes

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gesaula.moodle.client import ClienteMoodle
from gesaula.moodle.errors import (
    ErrorConexionMoodle,
    MoodleEnMantenimiento,
    SesionMoodleExpirada,
)
from gesaula.moodle.http_client import comprobar_url
from gesaula.moodle.models import CursoMoodle


class SenalesComprobacionUrl(QObject):
    """Comunica a la interfaz el resultado de una comprobación."""

    completada = Signal(str)
    fallida = Signal(str)
    mantenimiento = Signal(str)


class ComprobarUrl(QRunnable):
    """Comprueba una URL sin bloquear el hilo de la interfaz."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url
        self.senales = SenalesComprobacionUrl()

    @Slot()
    def run(self) -> None:
        """Ejecuta la petición y emite su resultado."""
        try:
            url_final = comprobar_url(self.url)
        except MoodleEnMantenimiento as error:
            self.senales.mantenimiento.emit(str(error))
        except ErrorConexionMoodle as error:
            self.senales.fallida.emit(str(error))
        else:
            self.senales.completada.emit(url_final)


class SenalesOperacionMoodle(QObject):
    """Señales de error comunes para cualquier acción sobre Moodle."""

    fallido = Signal(str)
    mantenimiento = Signal(str)
    sesion_expirada = Signal(str)


class SenalesInicioSesion(SenalesOperacionMoodle):
    """Comunica a la interfaz el resultado del formulario de acceso."""

    completado = Signal(object, object)


def emitir_error_moodle(
    senales: SenalesOperacionMoodle, error: ErrorConexionMoodle
) -> None:
    """Emite la señal específica de un error Moodle reutilizable."""
    if isinstance(error, SesionMoodleExpirada):
        senales.sesion_expirada.emit(str(error))
    elif isinstance(error, MoodleEnMantenimiento):
        senales.mantenimiento.emit(str(error))
    else:
        senales.fallido.emit(str(error))


class IniciarSesion(QRunnable):
    """Inicia una sesión Moodle sin bloquear la interfaz."""

    def __init__(self, url: str, usuario: str, contrasena: str) -> None:
        super().__init__()
        self.url = url
        self.usuario = usuario
        self.contrasena = contrasena
        self.senales = SenalesInicioSesion()

    @Slot()
    def run(self) -> None:
        """Ejecuta el login y conserva el cliente si finaliza."""
        cliente = ClienteMoodle(self.url)
        try:
            resultado = cliente.iniciar_sesion(self.usuario, self.contrasena)
        except ErrorConexionMoodle as error:
            cliente.cerrar()
            emitir_error_moodle(self.senales, error)
        else:
            self.senales.completado.emit(cliente, resultado)
        finally:
            self.contrasena = ""


class SenalesCargaImagenes(SenalesOperacionMoodle):
    """Comunica las imágenes descargadas para los cursos."""

    imagen_cargada = Signal(int, bytes)
    estado_imagen = Signal(int, str)
    completada = Signal()


class CargarImagenesCursos(QRunnable):
    """Descarga imágenes de cursos usando la sesión autenticada."""

    def __init__(
        self, cliente: ClienteMoodle, cursos: tuple[CursoMoodle, ...]
    ) -> None:
        super().__init__()
        self.cliente = cliente
        self.cursos = cursos
        self.senales = SenalesCargaImagenes()

    @Slot()
    def run(self) -> None:
        """Descarga secuencialmente las imágenes disponibles."""
        try:
            for curso in self.cursos:
                if curso.imagen_url is None:
                    self.senales.estado_imagen.emit(
                        curso.id, "ERROR: el parser no encontró una ruta de imagen"
                    )
                    continue

                # Moodle genera fondos SVG distintos para los cursos sin una
                # imagen propia y los incrusta como data URI en el HTML.
                if curso.imagen_url.startswith("data:image/"):
                    datos = _decodificar_data_uri(curso.imagen_url)
                    if datos is not None:
                        self.senales.estado_imagen.emit(
                            curso.id, f"Decodificada: {len(datos)} bytes; enviando a Qt"
                        )
                        self.senales.imagen_cargada.emit(curso.id, datos)
                    else:
                        self.senales.estado_imagen.emit(
                            curso.id, "ERROR: no se pudo decodificar el data URI"
                        )
                    continue

                self.senales.estado_imagen.emit(
                    curso.id, f"Descargando: {curso.imagen_url}"
                )
                respuesta = self.cliente.obtener(curso.imagen_url)
                tipo = respuesta.headers.get("content-type", "")
                if tipo.casefold().startswith("image/"):
                    self.senales.estado_imagen.emit(
                        curso.id,
                        f"Descargada: {len(respuesta.content)} bytes ({tipo}); enviando a Qt",
                    )
                    self.senales.imagen_cargada.emit(curso.id, respuesta.content)
                else:
                    self.senales.estado_imagen.emit(
                        curso.id,
                        f"ERROR: respuesta HTTP {respuesta.status_code} "
                        f"de tipo {tipo or 'desconocido'}",
                    )
        except ErrorConexionMoodle as error:
            emitir_error_moodle(self.senales, error)
        else:
            self.senales.completada.emit()


def _decodificar_data_uri(uri: str) -> bytes | None:
    """Decodifica una imagen embebida por Moodle sin realizar una petición HTTP."""
    cabecera, separador, contenido = uri.partition(",")
    if not separador:
        return None

    try:
        if cabecera.casefold().endswith(";base64"):
            return base64.b64decode(contenido, validate=True)
        return unquote_to_bytes(contenido)
    except (binascii.Error, ValueError):
        return None
