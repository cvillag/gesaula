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
        self._trabajos_activos: set[object] = set()
        self.cursos: dict[int, CursoMoodle] = {}
        self._elementos: dict[int, QListWidgetItem] = {}

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
        # Las tarjetas se comportan como botones y abren la página del curso.
        self.mosaico.setStyleSheet(
            "QListWidget::item { border: 1px solid #b8c7d9; border-radius: 8px; "
            "background: white; padding: 6px; }"
            "QListWidget::item:hover { border: 2px solid #056bcf; "
            "background: #f2f7fc; }"
            "QListWidget::item:selected { border: 2px solid #056bcf; "
            "background: #e7f1fb; color: black; }"
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

        if not cursos:
            elemento = QListWidgetItem(
                "No se encontraron cursos en la página Mis cursos."
            )
            elemento.setFlags(Qt.ItemFlag.NoItemFlags)
            self.mosaico.addItem(elemento)
            return

        icono_provisional = QIcon(self._crear_imagen_provisional())
        for curso in cursos:
            elemento = QListWidgetItem(
                icono_provisional,
                curso.nombre,
            )
            elemento.setData(Qt.ItemDataRole.UserRole, curso.id)
            elemento.setData(Qt.ItemDataRole.UserRole + 1, curso.url)
            elemento.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            elemento.setToolTip(f"{curso.nombre}\nID: {curso.id}")
            self.mosaico.addItem(elemento)
            self._elementos[curso.id] = elemento

    def cargar_imagenes(
        self, cliente: ClienteMoodle, cursos: tuple[CursoMoodle, ...]
    ) -> None:
        """Carga las imágenes sin bloquear la interfaz."""
        trabajo = CargarImagenesCursos(cliente, cursos)
        trabajo.senales.imagen_cargada.connect(self.mostrar_imagen)
        trabajo.senales.sesion_expirada.connect(self.sesion_expirada.emit)
        trabajo.senales.finalizada.connect(self._retirar_trabajo)
        self._trabajos_activos.add(trabajo)
        QThreadPool.globalInstance().start(trabajo)

    def _retirar_trabajo(self, trabajo: object) -> None:
        """Libera un trabajo una vez procesada su señal final en la interfaz."""
        self._trabajos_activos.discard(trabajo)

    def mostrar_imagen(self, curso_id: int, datos: bytes) -> None:
        """Coloca una imagen descargada en la tarjeta correspondiente."""
        elemento = self._elementos.get(curso_id)
        imagen = QPixmap()
        if elemento is None:
            return
        if not imagen.loadFromData(datos):
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
