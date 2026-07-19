"""Ventana principal de la aplicación."""

from PySide6.QtCore import QThreadPool
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gesaula.actions.calificaciones_ods import (
    InformeCalificaciones,
    SeleccionCalificaciones,
)
from gesaula.moodle.models import ActividadDescargable, ResultadoLogin
from gesaula.ui.course_detail_panel import (
    PanelDetalleCurso,
    crear_accion_guardar_examenes,
    crear_accion_level_up,
)
from gesaula.ui.courses_panel import PanelCursos
from gesaula.ui.exam_storage_panel import PanelAlmacenarExamenes
from gesaula.ui.grades_dialog import DialogoCalificaciones
from gesaula.ui.level_up_panel import PanelLevelUp
from gesaula.ui.login_panel import PanelConexion, PanelCredenciales
from gesaula.ui.workers import (
    ActualizarPxLevelUp,
    AplicarCalificacionesLevelUp,
    CargarActividadesCurso,
    CargarInformeLevelUp,
    ComprobarRolProfesor,
    GuardarCuestionarios,
)


class VentanaPrincipal(QMainWindow):
    """Contenedor principal de la interfaz."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("gesaula")
        self.resize(720, 680)
        self.cliente_moodle = None
        self._curso_comprobando: int | None = None
        self._trabajos_activos: set[object] = set()
        self._dialogo_calificaciones_activo: DialogoCalificaciones | None = None

        marco = QFrame(self)
        marco.setObjectName("marcoPrincipal")
        marco.setStyleSheet(
            "QFrame#marcoPrincipal { border: 3px solid #056bcf; }"
        )

        self.paginas = QStackedWidget(marco)
        self.panel_conexion = PanelConexion(self.paginas)
        self.panel_credenciales = PanelCredenciales(self.paginas)
        self.panel_cursos = PanelCursos(self.paginas)
        self.panel_detalle_curso = PanelDetalleCurso(self.paginas)
        self.panel_level_up = PanelLevelUp(self.paginas)
        self.panel_almacenar_examenes = PanelAlmacenarExamenes(self.paginas)
        self.paginas.addWidget(self.panel_conexion)
        self.paginas.addWidget(self.panel_credenciales)
        self.paginas.addWidget(self.panel_cursos)
        self.paginas.addWidget(self.panel_detalle_curso)
        self.paginas.addWidget(self.panel_level_up)
        self.paginas.addWidget(self.panel_almacenar_examenes)
        self.panel_conexion.url_comprobada.connect(self.mostrar_credenciales)
        self.panel_credenciales.sesion_iniciada.connect(self.conservar_sesion)
        self.panel_credenciales.sesion_expirada.connect(
            self.mostrar_sesion_expirada
        )
        self.panel_cursos.sesion_expirada.connect(self.mostrar_sesion_expirada)
        self.panel_cursos.curso_seleccionado.connect(self.mostrar_curso)
        self.panel_detalle_curso.volver_solicitado.connect(self.mostrar_cursos)
        self.panel_detalle_curso.accion_solicitada.connect(self.mostrar_accion)
        self.panel_level_up.volver_solicitado.connect(self.mostrar_detalle_curso)
        self.panel_level_up.sumar_px_solicitado.connect(self.sumar_px_level_up)
        self.panel_level_up.calificaciones_solicitadas.connect(
            self.aplicar_calificaciones_level_up
        )
        self.panel_almacenar_examenes.volver_solicitado.connect(
            self.mostrar_detalle_curso
        )
        self.panel_almacenar_examenes.descarga_solicitada.connect(
            self.guardar_cuestionarios
        )

        self.barra_sesion = QWidget(marco)
        self.barra_sesion.hide()
        self.boton_cerrar_sesion = QPushButton("Cerrar sesión")
        self.boton_cerrar_sesion.setFixedWidth(
            self.boton_cerrar_sesion.sizeHint().width()
        )
        self.boton_cerrar_sesion.clicked.connect(self.cerrar_sesion)

        disposicion_barra = QHBoxLayout(self.barra_sesion)
        disposicion_barra.setContentsMargins(8, 6, 8, 0)
        disposicion_barra.addStretch()
        disposicion_barra.addWidget(self.boton_cerrar_sesion)

        disposicion = QVBoxLayout(marco)
        disposicion.setContentsMargins(3, 3, 3, 3)
        disposicion.addWidget(self.barra_sesion)
        disposicion.addWidget(self.paginas)

        self.setCentralWidget(marco)

    def mostrar_credenciales(self, url: str) -> None:
        """Muestra la página de usuario y contraseña."""
        self.url_aula_virtual = url
        self.panel_credenciales.establecer_url(url)
        self.paginas.setCurrentWidget(self.panel_credenciales)
        self.panel_credenciales.entrada_usuario.setFocus()

    def conservar_sesion(
        self, cliente: object, resultado: ResultadoLogin
    ) -> None:
        """Conserva el cliente y muestra la página de cursos."""
        if self.cliente_moodle is not None:
            self.cliente_moodle.cerrar()
        self.cliente_moodle = cliente
        self.panel_cursos.mostrar(resultado.cursos)
        self.barra_sesion.show()
        self.paginas.setCurrentWidget(self.panel_cursos)
        self.panel_cursos.cargar_imagenes(cliente, resultado.cursos)

    def mostrar_curso(self, curso_id: int) -> None:
        """Comprueba el rol antes de abrir la página de acciones."""
        curso = self.panel_cursos.cursos.get(curso_id)
        if curso is None or self.cliente_moodle is None:
            return
        if self._curso_comprobando is not None:
            return

        self._curso_comprobando = curso_id
        self.panel_cursos.setEnabled(False)
        trabajo = ComprobarRolProfesor(self.cliente_moodle, curso_id)
        trabajo.senales.completada.connect(self.procesar_rol_profesor)
        trabajo.senales.fallido.connect(self.mostrar_error_comprobacion_rol)
        trabajo.senales.mantenimiento.connect(self.mostrar_error_comprobacion_rol)
        trabajo.senales.sesion_expirada.connect(self.mostrar_sesion_expirada)
        trabajo.senales.finalizada.connect(self._retirar_trabajo)
        self._trabajos_activos.add(trabajo)
        QThreadPool.globalInstance().start(trabajo)

    def _retirar_trabajo(self, trabajo: object) -> None:
        """Libera un trabajo una vez procesada su señal final en la interfaz."""
        self._trabajos_activos.discard(trabajo)

    def procesar_rol_profesor(
        self,
        curso_id: int,
        es_profesor: bool,
        url_level_up: object,
    ) -> None:
        """Abre el curso exclusivamente cuando Moodle confirma el rol Profesor."""
        self._finalizar_comprobacion_rol()
        if not es_profesor:
            QMessageBox.information(
                self,
                "Acceso al curso",
                "No tiene rol profesor en este curso.",
            )
            return
        curso = self.panel_cursos.cursos.get(curso_id)
        if curso is None:
            return
        acciones = []
        if isinstance(url_level_up, str):
            acciones.append(crear_accion_level_up(url_level_up))
        acciones.append(crear_accion_guardar_examenes(curso.url))
        self.panel_detalle_curso.mostrar(curso, acciones)
        self.paginas.setCurrentWidget(self.panel_detalle_curso)

    def mostrar_error_comprobacion_rol(self, mensaje: str) -> None:
        """Informa de un fallo técnico al consultar el rol."""
        self._finalizar_comprobacion_rol()
        QMessageBox.warning(self, "No se pudo comprobar el rol", mensaje)

    def _finalizar_comprobacion_rol(self) -> None:
        self._curso_comprobando = None
        self.panel_cursos.setEnabled(True)

    def mostrar_cursos(self) -> None:
        """Regresa al mosaico conservando cursos, imágenes y sesión."""
        self.paginas.setCurrentWidget(self.panel_cursos)

    def mostrar_detalle_curso(self) -> None:
        """Regresa desde una acción a la lista de acciones del curso."""
        self.paginas.setCurrentWidget(self.panel_detalle_curso)

    def mostrar_accion(self, identificador: str, url: str) -> None:
        """Abre la pantalla de una acción disponible para el curso."""
        curso = self.panel_detalle_curso.curso
        if curso is None or self.cliente_moodle is None:
            return

        if identificador == "level_up":
            self.panel_level_up.mostrar_cargando(curso, url)
            self.paginas.setCurrentWidget(self.panel_level_up)
            self.resize(max(self.width(), 1050), max(self.height(), 800))

            trabajo = CargarInformeLevelUp(self.cliente_moodle, curso.id, url)
            trabajo.senales.completada.connect(self.procesar_informe_level_up)
            trabajo.senales.fallido.connect(self.panel_level_up.mostrar_error)
            trabajo.senales.mantenimiento.connect(self.panel_level_up.mostrar_error)
            trabajo.senales.sesion_expirada.connect(self.mostrar_sesion_expirada)
            trabajo.senales.finalizada.connect(self._retirar_trabajo)
            self._trabajos_activos.add(trabajo)
            QThreadPool.globalInstance().start(trabajo)
            return

        if identificador != "guardar_examenes":
            return
        self.panel_almacenar_examenes.mostrar_cargando(curso)
        self.paginas.setCurrentWidget(self.panel_almacenar_examenes)
        self.resize(max(self.width(), 900), max(self.height(), 750))

        trabajo = CargarActividadesCurso(self.cliente_moodle, curso.id)
        trabajo.senales.completada.connect(self.procesar_actividades_curso)
        trabajo.senales.fallido.connect(
            self.panel_almacenar_examenes.mostrar_error
        )
        trabajo.senales.mantenimiento.connect(
            self.panel_almacenar_examenes.mostrar_error
        )
        trabajo.senales.sesion_expirada.connect(self.mostrar_sesion_expirada)
        trabajo.senales.finalizada.connect(self._retirar_trabajo)
        self._trabajos_activos.add(trabajo)
        QThreadPool.globalInstance().start(trabajo)

    def procesar_actividades_curso(
        self,
        curso_id: int,
        actividades: object,
    ) -> None:
        """Muestra las actividades si corresponden al curso abierto."""
        curso = self.panel_almacenar_examenes.curso
        if curso is None or curso.id != curso_id or not isinstance(actividades, tuple):
            return
        self.panel_almacenar_examenes.mostrar_actividades(actividades)

    def guardar_cuestionarios(
        self,
        actividades: object,
        destino: str,
    ) -> None:
        """Inicia el inventario y archivado de los cuestionarios seleccionados."""
        if (
            not isinstance(actividades, tuple)
            or not actividades
            or self.cliente_moodle is None
        ):
            return
        actividades_almacenables = tuple(
            actividad
            for actividad in actividades
            if isinstance(actividad, ActividadDescargable)
            and actividad.tipo in {"Cuestionario", "Tarea"}
        )
        if not actividades_almacenables:
            return
        self.panel_almacenar_examenes.iniciar_analisis(
            len(actividades_almacenables)
        )
        trabajo = GuardarCuestionarios(
            self.cliente_moodle,
            actividades_almacenables,
            destino,
        )
        trabajo.senales.analisis_elemento_iniciado.connect(
            self.panel_almacenar_examenes.iniciar_analisis_elemento
        )
        trabajo.senales.analisis_progreso.connect(
            self.panel_almacenar_examenes.actualizar_analisis
        )
        trabajo.senales.analisis_elemento_completado.connect(
            self.panel_almacenar_examenes.completar_analisis_elemento
        )
        trabajo.senales.analisis_tarea_iniciada.connect(
            self.panel_almacenar_examenes.iniciar_analisis_tarea
        )
        trabajo.senales.analisis_tarea_completada.connect(
            self.panel_almacenar_examenes.completar_analisis_tarea
        )
        trabajo.senales.inventario.connect(
            self.panel_almacenar_examenes.mostrar_inventario
        )
        trabajo.senales.elemento_iniciado.connect(
            self.panel_almacenar_examenes.iniciar_elemento
        )
        trabajo.senales.intento_guardado.connect(
            self.panel_almacenar_examenes.actualizar_intento
        )
        trabajo.senales.tarea_iniciada.connect(
            self.panel_almacenar_examenes.iniciar_tarea
        )
        trabajo.senales.entrega_guardada.connect(
            self.panel_almacenar_examenes.actualizar_entrega
        )
        trabajo.senales.elemento_completado.connect(
            self.panel_almacenar_examenes.completar_elemento
        )
        trabajo.senales.completada.connect(
            self.panel_almacenar_examenes.completar_descarga
        )
        trabajo.senales.descarga_fallida.connect(
            self.panel_almacenar_examenes.fallar_descarga
        )
        trabajo.senales.sesion_expirada.connect(self.mostrar_sesion_expirada)
        trabajo.senales.finalizada.connect(self._retirar_trabajo)
        self._trabajos_activos.add(trabajo)
        QThreadPool.globalInstance().start(trabajo)

    def procesar_informe_level_up(
        self,
        curso_id: int,
        alumnos: object,
    ) -> None:
        """Muestra el informe si todavía corresponde al curso seleccionado."""
        curso = self.panel_level_up.curso
        if curso is None or curso.id != curso_id or not isinstance(alumnos, tuple):
            return
        self.panel_level_up.mostrar_alumnos(alumnos)

    def sumar_px_level_up(self, alumno_id: int, puntos: int) -> None:
        """Suma puntos al total actual y solicita a Moodle que lo guarde."""
        curso = self.panel_level_up.curso
        alumno = self.panel_level_up.alumnos.get(alumno_id)
        if (
            curso is None
            or alumno is None
            or alumno.context_id is None
            or self.panel_level_up.url_informe is None
            or self.cliente_moodle is None
        ):
            return

        nuevo_total = alumno.px + puntos
        self.panel_level_up.iniciar_actualizacion(alumno_id)
        trabajo = ActualizarPxLevelUp(
            self.cliente_moodle,
            curso.id,
            alumno_id,
            alumno.context_id,
            nuevo_total,
            self.panel_level_up.url_informe,
        )
        trabajo.senales.completada.connect(self.procesar_actualizacion_px)
        trabajo.senales.informe_actualizado.connect(
            self.procesar_informe_level_up
        )
        trabajo.senales.actualizacion_fallida.connect(
            self.panel_level_up.cancelar_actualizacion
        )
        trabajo.senales.sesion_expirada.connect(self.mostrar_sesion_expirada)
        trabajo.senales.finalizada.connect(self._retirar_trabajo)
        self._trabajos_activos.add(trabajo)
        QThreadPool.globalInstance().start(trabajo)

    def procesar_actualizacion_px(
        self,
        curso_id: int,
        alumno_id: int,
        nuevo_total: int,
    ) -> None:
        """Actualiza la tabla después de la confirmación del servidor."""
        curso = self.panel_level_up.curso
        if curso is None or curso.id != curso_id:
            return
        self.panel_level_up.completar_actualizacion(alumno_id, nuevo_total)

    def aplicar_calificaciones_level_up(
        self,
        informe: object,
        seleccion: object,
        dialogo: object,
    ) -> None:
        """Valida las coincidencias y comienza la actualización secuencial."""
        curso = self.panel_level_up.curso
        url_informe = self.panel_level_up.url_informe
        if (
            not isinstance(informe, InformeCalificaciones)
            or not isinstance(seleccion, SeleccionCalificaciones)
            or not isinstance(dialogo, DialogoCalificaciones)
            or curso is None
            or url_informe is None
            or self.cliente_moodle is None
        ):
            return

        self._dialogo_calificaciones_activo = dialogo
        dialogo.finished.connect(self._finalizar_dialogo_calificaciones)
        dialogo.iniciar_preparacion()
        trabajo = AplicarCalificacionesLevelUp(
            self.cliente_moodle,
            curso.id,
            url_informe,
            informe,
            seleccion,
        )
        trabajo.senales.preparada.connect(dialogo.iniciar_proceso)
        trabajo.senales.preparacion_fallida.connect(
            dialogo.mostrar_error_preparacion
        )
        trabajo.senales.progreso.connect(self.actualizar_progreso_calificaciones)
        trabajo.senales.completada.connect(self.completar_calificaciones_level_up)
        trabajo.senales.aplicacion_fallida.connect(
            self.fallar_calificaciones_level_up
        )
        trabajo.senales.sesion_expirada.connect(dialogo.reject)
        trabajo.senales.sesion_expirada.connect(self.mostrar_sesion_expirada)
        trabajo.senales.finalizada.connect(self._retirar_trabajo)
        self._trabajos_activos.add(trabajo)
        QThreadPool.globalInstance().start(trabajo)

    def actualizar_progreso_calificaciones(
        self,
        procesados: int,
        total: int,
        nombre: str,
    ) -> None:
        """Actualiza la barra tras cada escritura confirmada."""
        if self._dialogo_calificaciones_activo is not None:
            self._dialogo_calificaciones_activo.actualizar_progreso(
                procesados,
                total,
                nombre,
            )

    def completar_calificaciones_level_up(
        self,
        curso_id: int,
        procesados: int,
    ) -> None:
        """Cierra el diálogo completo y recarga los datos de Level up."""
        curso = self.panel_level_up.curso
        if curso is None or curso.id != curso_id:
            return
        if self._dialogo_calificaciones_activo is not None:
            self._dialogo_calificaciones_activo.completar_proceso()
        self._recargar_informe_level_up()

    def fallar_calificaciones_level_up(self, mensaje: str) -> None:
        """Muestra el progreso parcial y refresca los cambios ya confirmados."""
        if self._dialogo_calificaciones_activo is not None:
            self._dialogo_calificaciones_activo.mostrar_error_proceso(mensaje)
        self._recargar_informe_level_up()

    def _recargar_informe_level_up(self) -> None:
        curso = self.panel_level_up.curso
        url = self.panel_level_up.url_informe
        if curso is None or url is None or self.cliente_moodle is None:
            return
        trabajo = CargarInformeLevelUp(self.cliente_moodle, curso.id, url)
        trabajo.senales.completada.connect(self.procesar_informe_level_up)
        trabajo.senales.fallido.connect(self.panel_level_up.mostrar_error)
        trabajo.senales.mantenimiento.connect(self.panel_level_up.mostrar_error)
        trabajo.senales.sesion_expirada.connect(self.mostrar_sesion_expirada)
        trabajo.senales.finalizada.connect(self._retirar_trabajo)
        self._trabajos_activos.add(trabajo)
        QThreadPool.globalInstance().start(trabajo)

    def _finalizar_dialogo_calificaciones(self, resultado: int) -> None:
        self._dialogo_calificaciones_activo = None

    def mostrar_sesion_expirada(self, mensaje: str) -> None:
        """Regresa al login cuando una acción detecta la sesión cerrada."""
        self._finalizar_comprobacion_rol()
        if self.cliente_moodle is not None:
            self.cliente_moodle.cerrar()
            self.cliente_moodle = None
        self.barra_sesion.hide()
        self.panel_detalle_curso.limpiar()
        self.panel_level_up.limpiar()
        self.panel_almacenar_examenes.limpiar()
        self.paginas.setCurrentWidget(self.panel_credenciales)
        self.panel_credenciales.mostrar_error(mensaje)
        self.panel_credenciales.entrada_contrasena.setFocus()

    def cerrar_sesion(self) -> None:
        """Cierra la sesión actual y vuelve a la pantalla inicial."""
        if self.cliente_moodle is not None:
            self.cliente_moodle.cerrar()
            self.cliente_moodle = None
        self.barra_sesion.hide()
        self.panel_credenciales.entrada_contrasena.clear()
        self.panel_credenciales.resultado.clear()
        self.panel_cursos.mostrar(())
        self.panel_detalle_curso.limpiar()
        self.panel_level_up.limpiar()
        self.panel_almacenar_examenes.limpiar()
        self.paginas.setCurrentWidget(self.panel_conexion)
        self.panel_conexion.entrada_url.setFocus()

    def closeEvent(self, evento: QCloseEvent) -> None:
        """Cierra la sesión HTTP al salir de la aplicación."""
        QThreadPool.globalInstance().waitForDone()
        if self.cliente_moodle is not None:
            self.cliente_moodle.cerrar()
        super().closeEvent(evento)
