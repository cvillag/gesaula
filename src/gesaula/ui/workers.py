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
    finalizada = Signal(object)


class ComprobarUrl(QRunnable):
    """Comprueba una URL sin bloquear el hilo de la interfaz."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self.setAutoDelete(False)
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
        finally:
            self.senales.finalizada.emit(self)


class SenalesOperacionMoodle(QObject):
    """Señales de error comunes para cualquier acción sobre Moodle."""

    fallido = Signal(str)
    mantenimiento = Signal(str)
    sesion_expirada = Signal(str)
    finalizada = Signal(object)


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
        self.setAutoDelete(False)
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
            self.senales.finalizada.emit(self)


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
        self.setAutoDelete(False)
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
        finally:
            self.senales.finalizada.emit(self)


class SenalesComprobacionRol(SenalesOperacionMoodle):
    """Comunica si el usuario tiene rol Profesor en un curso."""

    completada = Signal(int, bool, object)


class ComprobarRolProfesor(QRunnable):
    """Consulta el rol y las acciones del curso sin bloquear la interfaz."""

    def __init__(self, cliente: ClienteMoodle, curso_id: int) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.cliente = cliente
        self.curso_id = curso_id
        self.senales = SenalesComprobacionRol()

    @Slot()
    def run(self) -> None:
        """Emite el resultado de la comprobación o el error de sesión."""
        try:
            es_profesor = self.cliente.usuario_es_profesor(self.curso_id)
            url_level_up = (
                self.cliente.obtener_url_level_up(self.curso_id)
                if es_profesor
                else None
            )
        except ErrorConexionMoodle as error:
            emitir_error_moodle(self.senales, error)
        else:
            self.senales.completada.emit(
                self.curso_id,
                es_profesor,
                url_level_up,
            )
        finally:
            self.senales.finalizada.emit(self)


class SenalesInformeLevelUp(SenalesOperacionMoodle):
    """Comunica el alumnado obtenido del informe Level up."""

    completada = Signal(int, object)


class CargarInformeLevelUp(QRunnable):
    """Descarga y analiza el informe Level up sin bloquear la interfaz."""

    def __init__(
        self,
        cliente: ClienteMoodle,
        curso_id: int,
        url_informe: str,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.cliente = cliente
        self.curso_id = curso_id
        self.url_informe = url_informe
        self.senales = SenalesInformeLevelUp()

    @Slot()
    def run(self) -> None:
        """Emite los alumnos o el error de conexión correspondiente."""
        try:
            alumnos = self.cliente.obtener_alumnos_level_up(self.url_informe)
        except ErrorConexionMoodle as error:
            emitir_error_moodle(self.senales, error)
        else:
            self.senales.completada.emit(self.curso_id, alumnos)
        finally:
            self.senales.finalizada.emit(self)


class SenalesActualizarPxLevelUp(SenalesOperacionMoodle):
    """Comunica el resultado de actualizar los PX de un alumno."""

    completada = Signal(int, int, int)
    informe_actualizado = Signal(int, object)
    actualizacion_fallida = Signal(int, str)


class ActualizarPxLevelUp(QRunnable):
    """Envía un nuevo total de PX mediante el formulario dinámico de Moodle."""

    def __init__(
        self,
        cliente: ClienteMoodle,
        curso_id: int,
        alumno_id: int,
        context_id: int,
        nuevo_total: int,
        url_informe: str,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.cliente = cliente
        self.curso_id = curso_id
        self.alumno_id = alumno_id
        self.context_id = context_id
        self.nuevo_total = nuevo_total
        self.url_informe = url_informe
        self.senales = SenalesActualizarPxLevelUp()

    @Slot()
    def run(self) -> None:
        """Actualiza Moodle y conserva el total local sólo si lo confirma."""
        try:
            self.cliente.actualizar_px_level_up(
                self.alumno_id,
                self.context_id,
                self.nuevo_total,
            )
        except SesionMoodleExpirada as error:
            self.senales.sesion_expirada.emit(str(error))
        except ErrorConexionMoodle as error:
            self.senales.actualizacion_fallida.emit(self.alumno_id, str(error))
        else:
            self.senales.completada.emit(
                self.curso_id,
                self.alumno_id,
                self.nuevo_total,
            )
            try:
                alumnos = self.cliente.obtener_alumnos_level_up(self.url_informe)
            except SesionMoodleExpirada as error:
                self.senales.sesion_expirada.emit(str(error))
            except ErrorConexionMoodle:
                # La escritura ya fue confirmada. Conservamos el nuevo total
                # aunque no sea posible refrescar el nivel en este momento.
                pass
            else:
                self.senales.informe_actualizado.emit(self.curso_id, alumnos)
        finally:
            self.senales.finalizada.emit(self)


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
