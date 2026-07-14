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

from gesaula.moodle.models import ResultadoLogin
from gesaula.ui.course_detail_panel import PanelDetalleCurso, crear_accion_level_up
from gesaula.ui.courses_panel import PanelCursos
from gesaula.ui.login_panel import PanelConexion, PanelCredenciales
from gesaula.ui.workers import ComprobarRolProfesor


class VentanaPrincipal(QMainWindow):
    """Contenedor principal de la interfaz."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("gesaula")
        self.resize(720, 680)
        self.cliente_moodle = None
        self._curso_comprobando: int | None = None
        self._trabajos_activos: set[object] = set()

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
        self.paginas.addWidget(self.panel_conexion)
        self.paginas.addWidget(self.panel_credenciales)
        self.paginas.addWidget(self.panel_cursos)
        self.paginas.addWidget(self.panel_detalle_curso)
        self.panel_conexion.url_comprobada.connect(self.mostrar_credenciales)
        self.panel_credenciales.sesion_iniciada.connect(self.conservar_sesion)
        self.panel_credenciales.sesion_expirada.connect(
            self.mostrar_sesion_expirada
        )
        self.panel_cursos.sesion_expirada.connect(self.mostrar_sesion_expirada)
        self.panel_cursos.curso_seleccionado.connect(self.mostrar_curso)
        self.panel_detalle_curso.volver_solicitado.connect(self.mostrar_cursos)

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
        acciones = (
            (crear_accion_level_up(url_level_up),)
            if isinstance(url_level_up, str)
            else ()
        )
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

    def mostrar_sesion_expirada(self, mensaje: str) -> None:
        """Regresa al login cuando una acción detecta la sesión cerrada."""
        self._finalizar_comprobacion_rol()
        if self.cliente_moodle is not None:
            self.cliente_moodle.cerrar()
            self.cliente_moodle = None
        self.barra_sesion.hide()
        self.panel_detalle_curso.limpiar()
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
        self.paginas.setCurrentWidget(self.panel_conexion)
        self.panel_conexion.entrada_url.setFocus()

    def closeEvent(self, evento: QCloseEvent) -> None:
        """Cierra la sesión HTTP al salir de la aplicación."""
        QThreadPool.globalInstance().waitForDone()
        if self.cliente_moodle is not None:
            self.cliente_moodle.cerrar()
        super().closeEvent(evento)
