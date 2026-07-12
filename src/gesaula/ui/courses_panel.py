"""Panel de visualización de cursos."""

from PySide6.QtCore import QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gesaula.moodle.client import ClienteMoodle
from gesaula.moodle.models import CursoMoodle
from gesaula.resources import DIRECTORIO_ICONOS
from gesaula.ui.workers import CargarImagenesCursos

ANCHO_IMAGEN = 200
ALTO_IMAGEN = 100
ANCHO_TARJETA = 220
ALTO_TARJETA = 215


class PanelCursos(QWidget):
    """Muestra los cursos encontrados para la sesión actual."""

    curso_seleccionado = Signal(int)
    sesion_expirada = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cursos: dict[int, CursoMoodle] = {}
        self._elementos: dict[int, QListWidgetItem] = {}
        self._estados_imagen: dict[int, str] = {}

        logotipo = QLabel()
        logotipo.setPixmap(QPixmap(str(DIRECTORIO_ICONOS / "logo32.png")))
        titulo = QLabel("Mis cursos")

        cabecera = QHBoxLayout()
        cabecera.addWidget(logotipo)
        cabecera.addWidget(titulo)
        cabecera.addStretch()

        self.mosaico = QListWidget()
        self.mosaico.setViewMode(QListView.ViewMode.IconMode)
        self.mosaico.setResizeMode(QListView.ResizeMode.Adjust)
        self.mosaico.setMovement(QListView.Movement.Static)
        self.mosaico.setWrapping(True)
        self.mosaico.setWordWrap(True)
        self.mosaico.setSpacing(10)
        self.mosaico.setIconSize(QSize(ANCHO_IMAGEN, ALTO_IMAGEN))
        self.mosaico.setGridSize(QSize(ANCHO_TARJETA, ALTO_TARJETA))
        self.mosaico.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.mosaico.itemClicked.connect(self._emitir_curso_seleccionado)

        disposicion = QVBoxLayout(self)
        disposicion.addLayout(cabecera)
        disposicion.addWidget(self.mosaico)

    def mostrar(self, cursos: tuple[CursoMoodle, ...]) -> None:
        """Crea una tarjeta para cada curso encontrado."""
        self.mosaico.clear()
        self.cursos = {curso.id: curso for curso in cursos}
        self._elementos.clear()
        self._estados_imagen.clear()

        if not cursos:
            elemento = QListWidgetItem(
                "No se encontraron cursos en la página Mis cursos."
            )
            elemento.setFlags(Qt.ItemFlag.NoItemFlags)
            self.mosaico.addItem(elemento)
            return

        icono_provisional = QIcon(self._crear_imagen_provisional())
        for curso in cursos:
            origen = self._describir_origen_imagen(curso.imagen_url)
            self._estados_imagen[curso.id] = f"Pendiente: {origen}"
            elemento = QListWidgetItem(
                icono_provisional,
                self._texto_tarjeta(curso.id),
            )
            elemento.setData(Qt.ItemDataRole.UserRole, curso.id)
            elemento.setData(Qt.ItemDataRole.UserRole + 1, curso.url)
            elemento.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            elemento.setToolTip(
                f"{curso.nombre}\nID: {curso.id}\n"
                f"Origen completo: {curso.imagen_url or 'sin imagen'}"
            )
            self.mosaico.addItem(elemento)
            self._elementos[curso.id] = elemento

    def cargar_imagenes(
        self, cliente: ClienteMoodle, cursos: tuple[CursoMoodle, ...]
    ) -> None:
        """Carga las imágenes sin bloquear la interfaz."""
        trabajo = CargarImagenesCursos(cliente, cursos)
        trabajo.senales.imagen_cargada.connect(self.mostrar_imagen)
        trabajo.senales.estado_imagen.connect(self.mostrar_estado_imagen)
        trabajo.senales.sesion_expirada.connect(self.sesion_expirada.emit)
        QThreadPool.globalInstance().start(trabajo)

    def mostrar_imagen(self, curso_id: int, datos: bytes) -> None:
        """Coloca una imagen descargada en la tarjeta correspondiente."""
        elemento = self._elementos.get(curso_id)
        imagen = QPixmap()
        if elemento is None:
            return
        if not imagen.loadFromData(datos):
            self.mostrar_estado_imagen(
                curso_id,
                f"ERROR: Qt no reconoce los {len(datos)} bytes recibidos",
            )
            return

        ajustada = imagen.scaled(
            ANCHO_IMAGEN,
            ALTO_IMAGEN,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (ajustada.width() - ANCHO_IMAGEN) // 2)
        y = max(0, (ajustada.height() - ALTO_IMAGEN) // 2)
        elemento.setIcon(
            QIcon(ajustada.copy(x, y, ANCHO_IMAGEN, ALTO_IMAGEN))
        )
        self.mostrar_estado_imagen(
            curso_id,
            f"MOSTRADA: {len(datos)} bytes, {imagen.width()}x{imagen.height()} px",
        )

    def mostrar_estado_imagen(self, curso_id: int, estado: str) -> None:
        """Hace visible en la tarjeta cada etapa de la carga para facilitar el debug."""
        elemento = self._elementos.get(curso_id)
        if elemento is None:
            return
        self._estados_imagen[curso_id] = estado
        elemento.setText(self._texto_tarjeta(curso_id))

    def _texto_tarjeta(self, curso_id: int) -> str:
        curso = self.cursos[curso_id]
        return f"{curso.nombre}\n{self._estados_imagen[curso_id]}"

    @staticmethod
    def _describir_origen_imagen(imagen_url: str | None) -> str:
        """Resume los data URI enormes; las URL HTTP se muestran completas."""
        if imagen_url is None:
            return "sin ruta de imagen"
        if imagen_url.startswith("data:"):
            cabecera, separador, contenido = imagen_url.partition(",")
            if separador:
                return f"{cabecera},... ({len(contenido)} caracteres embebidos)"
        return imagen_url

    def _emitir_curso_seleccionado(self, elemento: QListWidgetItem) -> None:
        curso_id = elemento.data(Qt.ItemDataRole.UserRole)
        if curso_id is not None:
            self.curso_seleccionado.emit(int(curso_id))

    @staticmethod
    def _crear_imagen_provisional() -> QPixmap:
        imagen = QPixmap(ANCHO_IMAGEN, ALTO_IMAGEN)
        imagen.fill(QColor("#e8eef5"))

        logo = QPixmap(str(DIRECTORIO_ICONOS / "logo64.png"))
        pintor = QPainter(imagen)
        pintor.drawPixmap(
            (ANCHO_IMAGEN - logo.width()) // 2,
            (ALTO_IMAGEN - logo.height()) // 2,
            logo,
        )
        pintor.end()
        return imagen
