"""Trabajos en segundo plano para no bloquear la interfaz."""

import base64
import binascii
from pathlib import Path
from urllib.parse import unquote_to_bytes

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from gesaula.actions.calificaciones_ods import (
    ErrorPreparacionCalificaciones,
    InformeCalificaciones,
    SeleccionCalificaciones,
    preparar_plan_calificaciones,
)
from gesaula.actions.guardar_cuestionarios import (
    CuestionarioConIntentos,
    crear_inventario_cuestionarios,
    guardar_revision_cuestionario,
    preparar_carpetas_cuestionario,
)
from gesaula.actions.guardar_tareas import (
    TareaConEntregas,
    guardar_entrega_tarea,
    preparar_carpetas_tarea,
)
from gesaula.moodle.client import ClienteMoodle
from gesaula.moodle.errors import (
    ErrorConexionMoodle,
    MoodleEnMantenimiento,
    SesionMoodleExpirada,
)
from gesaula.moodle.http_client import comprobar_url
from gesaula.moodle.models import ActividadDescargable, CursoMoodle
from gesaula.moodle.parsers import (
    contiene_rubrica_tarea,
    extraer_adjuntos_revision,
    extraer_archivos_tarea,
    extraer_entregas_tarea,
)


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


class SenalesActividadesCurso(SenalesOperacionMoodle):
    """Comunica las actividades descargables encontradas en el curso."""

    completada = Signal(int, object)


class CargarActividadesCurso(QRunnable):
    """Busca actividades compatibles sin bloquear la interfaz."""

    def __init__(self, cliente: ClienteMoodle, curso_id: int) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.cliente = cliente
        self.curso_id = curso_id
        self.senales = SenalesActividadesCurso()

    @Slot()
    def run(self) -> None:
        """Obtiene las actividades o comunica el error de sesión."""
        try:
            actividades = self.cliente.obtener_actividades_descargables(
                self.curso_id
            )
        except ErrorConexionMoodle as error:
            emitir_error_moodle(self.senales, error)
        else:
            self.senales.completada.emit(self.curso_id, actividades)
        finally:
            self.senales.finalizada.emit(self)


class SenalesGuardarCuestionarios(SenalesOperacionMoodle):
    """Comunica el inventario y la descarga de revisiones."""

    analisis_elemento_iniciado = Signal(int, int, str, int)
    analisis_progreso = Signal(int, int, str)
    analisis_elemento_completado = Signal(int, int, str, int, int)
    analisis_tarea_iniciada = Signal(int, int, str)
    analisis_tarea_completada = Signal(int, int, str, int)
    inventario = Signal(int, int, int)
    elemento_iniciado = Signal(int, int, str, int)
    intento_guardado = Signal(int, int, str)
    tarea_iniciada = Signal(int, int, str, int)
    entrega_guardada = Signal(int, int, str)
    elemento_completado = Signal(int, int)
    completada = Signal(str, int, int)
    descarga_fallida = Signal(str)


class GuardarCuestionarios(QRunnable):
    """Archiva revisiones y adjuntos de cuestionarios secuencialmente."""

    def __init__(
        self,
        cliente: ClienteMoodle,
        actividades: tuple[ActividadDescargable, ...],
        destino: str | Path,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.cliente = cliente
        self.actividades = actividades
        self.destino = Path(destino)
        self.senales = SenalesGuardarCuestionarios()

    @Slot()
    def run(self) -> None:
        """Calcula primero el inventario y después descarga cada intento."""
        try:
            self.destino.mkdir(parents=True, exist_ok=True)
            cuestionarios: dict[int, CuestionarioConIntentos] = {}
            tareas: dict[int, TareaConEntregas] = {}
            total_elementos = len(self.actividades)
            for posicion, actividad in enumerate(self.actividades, start=1):
                if actividad.tipo == "Tarea":
                    self.senales.analisis_tarea_iniciada.emit(
                        posicion,
                        total_elementos,
                        actividad.nombre,
                    )
                    entregas_por_alumno = {}
                    for html, url_pagina in (
                        self.cliente.obtener_paginas_entregas_tarea(
                            actividad.id
                        )
                    ):
                        for entrega in extraer_entregas_tarea(
                            html,
                            url_pagina,
                            actividad.id,
                        ):
                            entregas_por_alumno.setdefault(
                                entrega.alumno_id,
                                entrega,
                            )
                    entregas = tuple(entregas_por_alumno.values())
                    preparar_carpetas_tarea(
                        self.destino,
                        actividad,
                        entregas,
                    )
                    tareas[actividad.id] = TareaConEntregas(
                        actividad,
                        entregas,
                    )
                    self.senales.analisis_progreso.emit(
                        posicion,
                        total_elementos,
                        actividad.nombre,
                    )
                    self.senales.analisis_tarea_completada.emit(
                        posicion,
                        total_elementos,
                        actividad.nombre,
                        len(entregas),
                    )
                    continue

                numero_intentos = (
                    self.cliente.obtener_numero_intentos_cuestionario(
                        actividad
                    )
                )
                self.senales.analisis_elemento_iniciado.emit(
                    posicion,
                    total_elementos,
                    actividad.nombre,
                    numero_intentos,
                )
                intentos = (
                    self.cliente.obtener_intentos_cuestionario(actividad.id)
                    if numero_intentos > 0
                    else ()
                )
                preparar_carpetas_cuestionario(
                    self.destino,
                    actividad,
                    intentos,
                )
                cuestionarios[actividad.id] = CuestionarioConIntentos(
                    actividad=actividad,
                    intentos=intentos,
                )
                self.senales.analisis_progreso.emit(
                    posicion,
                    total_elementos,
                    actividad.nombre,
                )
                self.senales.analisis_elemento_completado.emit(
                    posicion,
                    total_elementos,
                    actividad.nombre,
                    numero_intentos,
                    len(intentos),
                )

            inventario = crear_inventario_cuestionarios(
                tuple(cuestionarios.values())
            )
            alumnos = {
                *_ids_alumnos_cuestionarios(tuple(cuestionarios.values())),
                *(
                    f"user:{entrega.alumno_id}"
                    for tarea in tareas.values()
                    for entrega in tarea.entregas
                ),
            }
            total_registros = inventario.total_intentos + sum(
                len(tarea.entregas) for tarea in tareas.values()
            )
            self.senales.inventario.emit(
                total_elementos,
                len(alumnos),
                total_registros,
            )

            for numero_elemento, actividad in enumerate(
                self.actividades,
                start=1,
            ):
                if actividad.tipo == "Tarea":
                    tarea = tareas[actividad.id]
                    self._guardar_tarea(
                        tarea,
                        numero_elemento,
                        total_elementos,
                    )
                    continue

                cuestionario = cuestionarios[actividad.id]
                total_intentos = len(cuestionario.intentos)
                self.senales.elemento_iniciado.emit(
                    numero_elemento,
                    total_elementos,
                    cuestionario.actividad.nombre,
                    total_intentos,
                )
                for numero_intento, intento in enumerate(
                    cuestionario.intentos,
                    start=1,
                ):
                    respuesta = self.cliente.obtener(intento.url_revision)
                    adjuntos = extraer_adjuntos_revision(
                        respuesta.text,
                        str(respuesta.url),
                    )
                    contenidos = tuple(
                        (adjunto, self.cliente.obtener(adjunto.url).content)
                        for adjunto in adjuntos
                    )
                    guardar_revision_cuestionario(
                        self.destino,
                        cuestionario.actividad,
                        intento,
                        respuesta.text,
                        contenidos,
                    )
                    self.senales.intento_guardado.emit(
                        numero_intento,
                        total_intentos,
                        intento.alumno,
                    )
                self.senales.elemento_completado.emit(
                    numero_elemento,
                    total_elementos,
                )
            self.senales.completada.emit(
                str(self.destino),
                total_elementos,
                total_registros,
            )
        except SesionMoodleExpirada as error:
            self.senales.sesion_expirada.emit(str(error))
        except (ErrorConexionMoodle, OSError) as error:
            self.senales.descarga_fallida.emit(str(error))
        finally:
            self.senales.finalizada.emit(self)

    def _guardar_tarea(
        self,
        tarea: TareaConEntregas,
        numero_elemento: int,
        total_elementos: int,
    ) -> None:
        """Archiva todas las filas de Entregas y sus detalles opcionales."""
        total_entregas = len(tarea.entregas)
        self.senales.tarea_iniciada.emit(
            numero_elemento,
            total_elementos,
            tarea.actividad.nombre,
            total_entregas,
        )
        detalles: dict[int, tuple[str, str]] = {}
        usa_rubrica = False
        entrega_incompleta = next(
            (
                entrega
                for entrega in tarea.entregas
                if entrega.requiere_calificacion
            ),
            None,
        )
        if entrega_incompleta is not None:
            respuesta = self.cliente.obtener(
                entrega_incompleta.url_calificacion
            )
            detalle = (respuesta.text, str(respuesta.url))
            detalles[entrega_incompleta.alumno_id] = detalle
            usa_rubrica = contiene_rubrica_tarea(respuesta.text)

        for numero_entrega, entrega in enumerate(tarea.entregas, start=1):
            html_texto = None
            html_calificacion = None
            archivos = {archivo.url: archivo for archivo in entrega.archivos}

            if entrega.url_texto_completo is not None:
                respuesta = self.cliente.obtener(entrega.url_texto_completo)
                html_texto = (respuesta.text, str(respuesta.url))
                archivos.update(
                    (archivo.url, archivo)
                    for archivo in extraer_archivos_tarea(
                        respuesta.text,
                        str(respuesta.url),
                    )
                )
            if entrega.requiere_calificacion or usa_rubrica:
                html_calificacion = detalles.get(entrega.alumno_id)
                if html_calificacion is None:
                    respuesta = self.cliente.obtener(
                        entrega.url_calificacion
                    )
                    html_calificacion = (
                        respuesta.text,
                        str(respuesta.url),
                    )
                archivos.update(
                    (archivo.url, archivo)
                    for archivo in extraer_archivos_tarea(
                        html_calificacion[0],
                        html_calificacion[1],
                    )
                )

            contenidos = tuple(
                (archivo, self.cliente.obtener(archivo.url).content)
                for archivo in archivos.values()
            )
            guardar_entrega_tarea(
                self.destino,
                tarea.actividad,
                entrega,
                html_texto,
                html_calificacion,
                contenidos,
            )
            self.senales.entrega_guardada.emit(
                numero_entrega,
                total_entregas,
                entrega.alumno,
            )
        self.senales.elemento_completado.emit(
            numero_elemento,
            total_elementos,
        )


def _ids_alumnos_cuestionarios(
    cuestionarios: tuple[CuestionarioConIntentos, ...],
) -> set[str]:
    return {
        (
            f"user:{intento.alumno_id}"
            if intento.alumno_id is not None
            else f"nombre:{intento.alumno.casefold()}"
        )
        for cuestionario in cuestionarios
        for intento in cuestionario.intentos
    }


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


class SenalesAplicarCalificaciones(SenalesOperacionMoodle):
    """Comunica el avance de una actualización de PX por lotes."""

    preparada = Signal(int, int)
    progreso = Signal(int, int, str)
    completada = Signal(int, int)
    preparacion_fallida = Signal(str)
    aplicacion_fallida = Signal(str)


class AplicarCalificacionesLevelUp(QRunnable):
    """Actualiza secuencialmente los PX calculados desde calificaciones."""

    def __init__(
        self,
        cliente: ClienteMoodle,
        curso_id: int,
        url_informe: str,
        informe: InformeCalificaciones,
        seleccion: SeleccionCalificaciones,
    ) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.cliente = cliente
        self.curso_id = curso_id
        self.url_informe = url_informe
        self.informe = informe
        self.seleccion = seleccion
        self.senales = SenalesAplicarCalificaciones()

    @Slot()
    def run(self) -> None:
        """Detiene el lote ante el primer error para evitar resultados inciertos."""
        try:
            alumnos_level_up = self.cliente.obtener_alumnos_level_up(
                self.url_informe
            )
        except SesionMoodleExpirada as error:
            self.senales.sesion_expirada.emit(str(error))
            self.senales.finalizada.emit(self)
            return
        except ErrorConexionMoodle as error:
            self.senales.preparacion_fallida.emit(str(error))
            self.senales.finalizada.emit(self)
            return
        try:
            plan = preparar_plan_calificaciones(
                self.informe,
                self.seleccion,
                alumnos_level_up,
            )
        except ErrorPreparacionCalificaciones as error:
            self.senales.preparacion_fallida.emit(str(error))
            self.senales.finalizada.emit(self)
            return

        total = len(plan.incrementos)
        procesados = 0
        self.senales.preparada.emit(total, plan.alumnos_sin_calificacion)
        try:
            for incremento in plan.incrementos:
                try:
                    self.cliente.actualizar_px_level_up(
                        incremento.alumno_id,
                        incremento.context_id,
                        incremento.nuevo_total,
                    )
                except SesionMoodleExpirada as error:
                    self.senales.sesion_expirada.emit(str(error))
                    return
                except ErrorConexionMoodle as error:
                    self.senales.aplicacion_fallida.emit(
                        f"Proceso detenido tras {procesados} de {total}. "
                        f"No se pudo actualizar a {incremento.nombre}: {error} "
                        "Los cambios anteriores sí se guardaron."
                    )
                    return
                procesados += 1
                self.senales.progreso.emit(
                    procesados,
                    total,
                    incremento.nombre,
                )
            self.senales.completada.emit(self.curso_id, procesados)
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
