"""Panel inicial para indicar la dirección del Aula Virtual."""

from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from gesaula.config.storage import (
    cargar_urls_recientes,
    cargar_usuarios_recientes,
    guardar_url_reciente,
    guardar_usuario_reciente,
)
from gesaula.moodle.models import ResultadoLogin
from gesaula.resources import DIRECTORIO_ICONOS
from gesaula.ui.workers import ComprobarUrl, IniciarSesion


def anadir_cabecera(disposicion: QVBoxLayout) -> None:
    """Añade el logotipo y los títulos comunes a una página."""
    logotipo = QLabel()
    logotipo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    logotipo.setPixmap(QPixmap(str(DIRECTORIO_ICONOS / "logo256.png")))

    titulo1 = QLabel("Cliente de automatización")
    titulo2 = QLabel("Conectar con el Aula Virtual")
    titulo1.setAlignment(Qt.AlignmentFlag.AlignCenter)
    titulo2.setAlignment(Qt.AlignmentFlag.AlignCenter)

    disposicion.addWidget(logotipo)
    disposicion.addWidget(titulo1)
    disposicion.addWidget(titulo2)


class PanelConexion(QWidget):
    """Solicita los datos necesarios para comenzar la conexión."""

    url_comprobada = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._trabajos_activos: set[object] = set()

        etiqueta_url = QLabel("URL del Aula Virtual Moodle")
        etiqueta_url.setMinimumWidth(400)
        etiqueta_url.setMaximumWidth(520)

        self.entrada_url = QComboBox()
        self.entrada_url.setEditable(True)
        self.entrada_url.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.entrada_url.addItems(cargar_urls_recientes())
        self.entrada_url.setMinimumWidth(400)
        self.entrada_url.setMaximumWidth(520)
        editor_url = self.entrada_url.lineEdit()
        if editor_url is not None:
            editor_url.setPlaceholderText("https://aulavirtual.example.org/centro/")
            editor_url.returnPressed.connect(self.comprobar_url)

        self.boton_continuar = QPushButton("Continuar")
        self.boton_continuar.setFixedWidth(self.boton_continuar.sizeHint().width())
        self.boton_continuar.clicked.connect(self.comprobar_url)
        self._url_en_comprobacion = ""

        self.progreso = QProgressBar()
        self.progreso.setRange(0, 0)
        self.progreso.setTextVisible(False)
        self.progreso.setFixedWidth(400)
        self.progreso.hide()

        self.estado = QLabel()
        self.estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.estado.setWordWrap(True)

        self.icono_estado = QLabel()
        self.icono_estado.setFixedSize(24, 24)
        self.icono_estado.hide()

        contenedor_estado = QWidget()
        contenedor_estado.setFixedWidth(520)
        disposicion_estado = QHBoxLayout(contenedor_estado)
        disposicion_estado.setContentsMargins(0, 0, 0, 0)
        disposicion_estado.addStretch()
        disposicion_estado.addWidget(self.icono_estado)
        disposicion_estado.addWidget(self.estado)
        disposicion_estado.addStretch()

        disposicion = QVBoxLayout(self)
        anadir_cabecera(disposicion)
        disposicion.addWidget(etiqueta_url, alignment=Qt.AlignmentFlag.AlignHCenter)
        disposicion.addWidget(self.entrada_url, alignment=Qt.AlignmentFlag.AlignHCenter)
        disposicion.addWidget(self.boton_continuar, alignment=Qt.AlignmentFlag.AlignHCenter)
        disposicion.addWidget(self.progreso, alignment=Qt.AlignmentFlag.AlignHCenter)
        disposicion.addWidget(contenedor_estado, alignment=Qt.AlignmentFlag.AlignHCenter)
        disposicion.addStretch()

    def comprobar_url(self) -> None:
        """Inicia la comprobación de la dirección introducida."""
        url = self.entrada_url.currentText().strip()
        if not url:
            self.mostrar_error("Introduce la URL del Aula Virtual.")
            return

        self._url_en_comprobacion = url
        self.entrada_url.setEnabled(False)
        self.boton_continuar.setEnabled(False)
        self.icono_estado.hide()
        self.estado.setStyleSheet("")
        self.estado.setText("Comprobando la dirección…")
        self.progreso.show()

        trabajo = ComprobarUrl(url)
        trabajo.senales.completada.connect(self.mostrar_resultado)
        trabajo.senales.fallida.connect(self.mostrar_error)
        trabajo.senales.mantenimiento.connect(self.mostrar_advertencia)
        trabajo.senales.finalizada.connect(self._retirar_trabajo)
        self._trabajos_activos.add(trabajo)
        QThreadPool.globalInstance().start(trabajo)

    def _retirar_trabajo(self, trabajo: object) -> None:
        """Libera un trabajo una vez procesada su señal final en la interfaz."""
        self._trabajos_activos.discard(trabajo)

    def mostrar_resultado(self, url_final: str) -> None:
        """Muestra que el servidor respondió correctamente."""
        urls = guardar_url_reciente(self._url_en_comprobacion)
        self.entrada_url.clear()
        self.entrada_url.addItems(urls)
        self.entrada_url.setCurrentIndex(0)
        self.icono_estado.hide()
        self.estado.setStyleSheet("color: #16752c;")
        self.estado.setText(f"Dirección accesible: {url_final}")
        self.finalizar_comprobacion()
        self.url_comprobada.emit(self._url_en_comprobacion)

    def mostrar_error(self, mensaje: str) -> None:
        """Muestra un error de validación o conexión."""
        self.mostrar_icono(QStyle.StandardPixmap.SP_MessageBoxCritical)
        self.estado.setStyleSheet("color: #b42318;")
        self.estado.setText(mensaje)
        self.finalizar_comprobacion()

    def mostrar_advertencia(self, mensaje: str) -> None:
        """Muestra una advertencia cuando Moodle está en mantenimiento."""
        self.mostrar_icono(QStyle.StandardPixmap.SP_MessageBoxWarning)
        self.estado.setStyleSheet("color: #8a6100;")
        self.estado.setText(mensaje)
        self.finalizar_comprobacion()

    def mostrar_icono(self, icono_estandar: QStyle.StandardPixmap) -> None:
        """Muestra un icono estándar junto al estado."""
        icono = self.style().standardIcon(icono_estandar)
        self.icono_estado.setPixmap(icono.pixmap(24, 24))
        self.icono_estado.show()

    def finalizar_comprobacion(self) -> None:
        """Restaura los controles tras finalizar la petición."""
        self.progreso.hide()
        self.entrada_url.setEnabled(True)
        self.boton_continuar.setEnabled(True)


class PanelCredenciales(QWidget):
    """Solicita las credenciales del Aula Virtual."""

    sesion_iniciada = Signal(object, object)
    sesion_expirada = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._trabajos_activos: set[object] = set()
        self.url_aula_virtual = ""
        self._usuario_en_comprobacion = ""

        etiqueta_usuario = QLabel("Usuario")
        etiqueta_contrasena = QLabel("Contraseña")
        for etiqueta in (etiqueta_usuario, etiqueta_contrasena):
            etiqueta.setMinimumWidth(400)
            etiqueta.setMaximumWidth(520)

        self.entrada_usuario = QComboBox()
        self.entrada_usuario.setEditable(True)
        self.entrada_usuario.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.entrada_usuario.addItems(cargar_usuarios_recientes())
        self.entrada_contrasena = QLineEdit()
        self.entrada_contrasena.setEchoMode(QLineEdit.EchoMode.Password)
        for entrada in (self.entrada_usuario, self.entrada_contrasena):
            entrada.setMinimumWidth(400)
            entrada.setMaximumWidth(520)

        self.boton_iniciar_sesion = QPushButton("Iniciar sesión")
        self.boton_iniciar_sesion.setFixedWidth(
            self.boton_iniciar_sesion.sizeHint().width()
        )
        self.boton_iniciar_sesion.clicked.connect(self.iniciar_sesion)
        self.entrada_contrasena.returnPressed.connect(self.iniciar_sesion)

        self.progreso = QProgressBar()
        self.progreso.setRange(0, 0)
        self.progreso.setTextVisible(False)
        self.progreso.setFixedWidth(400)
        self.progreso.hide()

        self.resultado = QLabel()
        self.resultado.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.resultado.setWordWrap(True)
        self.resultado.setFixedWidth(560)

        disposicion = QVBoxLayout(self)
        anadir_cabecera(disposicion)
        disposicion.addWidget(
            etiqueta_usuario, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        disposicion.addWidget(
            self.entrada_usuario, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        disposicion.addWidget(
            etiqueta_contrasena, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        disposicion.addWidget(
            self.entrada_contrasena, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        disposicion.addWidget(
            self.boton_iniciar_sesion, alignment=Qt.AlignmentFlag.AlignHCenter
        )
        disposicion.addWidget(self.progreso, alignment=Qt.AlignmentFlag.AlignHCenter)
        disposicion.addWidget(self.resultado, alignment=Qt.AlignmentFlag.AlignHCenter)
        disposicion.addStretch()

    def establecer_url(self, url: str) -> None:
        """Indica el Aula Virtual contra la que se iniciará sesión."""
        self.url_aula_virtual = url

    def iniciar_sesion(self) -> None:
        """Valida los campos y lanza el login en segundo plano."""
        usuario = self.entrada_usuario.currentText().strip()
        contrasena = self.entrada_contrasena.text()
        if not usuario or not contrasena:
            self.mostrar_error("Introduce el usuario y la contraseña.")
            return

        self._usuario_en_comprobacion = usuario
        self.entrada_contrasena.clear()
        self._activar_controles(False)
        self.resultado.setStyleSheet("")
        self.resultado.setText("Iniciando sesión…")
        self.progreso.show()

        trabajo = IniciarSesion(
            self.url_aula_virtual,
            usuario,
            contrasena,
        )
        trabajo.senales.completado.connect(self.procesar_resultado_login)
        trabajo.senales.fallido.connect(self.mostrar_error)
        trabajo.senales.mantenimiento.connect(self.mostrar_advertencia)
        trabajo.senales.sesion_expirada.connect(self.sesion_expirada.emit)
        trabajo.senales.finalizada.connect(self._retirar_trabajo)
        self._trabajos_activos.add(trabajo)
        QThreadPool.globalInstance().start(trabajo)

    def _retirar_trabajo(self, trabajo: object) -> None:
        """Libera un trabajo una vez procesada su señal final en la interfaz."""
        self._trabajos_activos.discard(trabajo)

    def procesar_resultado_login(
        self, cliente: object, resultado: ResultadoLogin
    ) -> None:
        """Acepta el login solo si se cumplen las cuatro comprobaciones."""
        comprobaciones = resultado.comprobaciones
        if comprobaciones.aceptado:
            usuarios = guardar_usuario_reciente(self._usuario_en_comprobacion)
            self.entrada_usuario.clear()
            self.entrada_usuario.addItems(usuarios)
            self.entrada_usuario.setCurrentIndex(0)
            self.resultado.clear()
            self.finalizar_login()
            self.sesion_iniciada.emit(cliente, resultado)
        else:
            cliente.cerrar()
            self.mostrar_error(
                "No se pudo confirmar el inicio de sesión en Moodle."
            )

    def mostrar_error(self, mensaje: str) -> None:
        """Muestra un error del formulario o de la conexión."""
        self.resultado.setStyleSheet("color: #b42318;")
        self.resultado.setText(f"✗ {mensaje}")
        self.finalizar_login()

    def mostrar_advertencia(self, mensaje: str) -> None:
        """Muestra que Moodle está en mantenimiento."""
        self.resultado.setStyleSheet("color: #8a6100;")
        self.resultado.setText(f"⚠ {mensaje}")
        self.finalizar_login()

    def finalizar_login(self) -> None:
        """Restaura el formulario después del intento."""
        self.progreso.hide()
        self._activar_controles(True)

    def _activar_controles(self, activos: bool) -> None:
        self.entrada_usuario.setEnabled(activos)
        self.entrada_contrasena.setEnabled(activos)
        self.boton_iniciar_sesion.setEnabled(activos)
