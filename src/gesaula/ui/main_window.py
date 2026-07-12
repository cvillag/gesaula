"""Ventana principal de la aplicación."""

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gesaula.moodle.models import ResultadoLogin
from gesaula.ui.courses_panel import PanelCursos
from gesaula.ui.login_panel import PanelConexion, PanelCredenciales


class VentanaPrincipal(QMainWindow):
    """Contenedor principal de la interfaz."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("gesaula")
        self.resize(720, 680)
        self.cliente_moodle = None

        marco = QFrame(self)
        marco.setObjectName("marcoPrincipal")
        marco.setStyleSheet(
            "QFrame#marcoPrincipal { border: 3px solid #056bcf; }"
        )

        self.paginas = QStackedWidget(marco)
        self.panel_conexion = PanelConexion(self.paginas)
        self.panel_credenciales = PanelCredenciales(self.paginas)
        self.panel_cursos = PanelCursos(self.paginas)
        self.paginas.addWidget(self.panel_conexion)
        self.paginas.addWidget(self.panel_credenciales)
        self.paginas.addWidget(self.panel_cursos)
        self.panel_conexion.url_comprobada.connect(self.mostrar_credenciales)
        self.panel_credenciales.sesion_iniciada.connect(self.conservar_sesion)
        self.panel_credenciales.sesion_expirada.connect(
            self.mostrar_sesion_expirada
        )
        self.panel_cursos.sesion_expirada.connect(self.mostrar_sesion_expirada)

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

    def mostrar_sesion_expirada(self, mensaje: str) -> None:
        """Regresa al login cuando una acción detecta la sesión cerrada."""
        if self.cliente_moodle is not None:
            self.cliente_moodle.cerrar()
            self.cliente_moodle = None
        self.barra_sesion.hide()
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
        self.paginas.setCurrentWidget(self.panel_conexion)
        self.panel_conexion.entrada_url.setFocus()

    def closeEvent(self, evento: QCloseEvent) -> None:
        """Cierra la sesión HTTP al salir de la aplicación."""
        if self.cliente_moodle is not None:
            self.cliente_moodle.cerrar()
        super().closeEvent(evento)
