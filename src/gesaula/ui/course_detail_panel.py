"""Página de acciones disponibles para un curso."""

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gesaula.moodle.models import CursoMoodle
from gesaula.resources import DIRECTORIO_ICONOS

TAMANO_BOTON_ACCION = QSize(240, 88)
TAMANO_ICONO_ACCION = QSize(180, 48)


@dataclass(frozen=True)
class AccionCurso:
    """Datos necesarios para presentar una acción disponible."""

    identificador: str
    nombre: str
    url: str
    icono: QIcon
    tamano_icono: QSize = TAMANO_ICONO_ACCION


class PanelDetalleCurso(QWidget):
    """Muestra el curso elegido y los botones de sus acciones."""

    volver_solicitado = Signal()
    accion_solicitada = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.curso: CursoMoodle | None = None

        self.nombre_curso = QLabel()
        self.nombre_curso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nombre_curso.setWordWrap(True)
        fuente = QFont(self.nombre_curso.font())
        fuente.setPointSize(16)
        fuente.setBold(True)
        self.nombre_curso.setFont(fuente)

        self.titulo_acciones = QLabel("Acciones")
        self.titulo_acciones.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.contenedor_acciones = QWidget(self)
        self.disposicion_acciones = QHBoxLayout(self.contenedor_acciones)
        self.disposicion_acciones.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )

        self.sin_acciones = QLabel("Todavía no hay acciones disponibles para este curso.")
        self.sin_acciones.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sin_acciones.setWordWrap(True)
        self.disposicion_acciones.addWidget(self.sin_acciones)

        self.boton_volver = QPushButton("Volver a Mis cursos")
        self.boton_volver.setFixedWidth(self.boton_volver.sizeHint().width())
        self.boton_volver.clicked.connect(self.volver_solicitado.emit)

        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(40, 30, 40, 30)
        disposicion.addWidget(self.nombre_curso)
        disposicion.addSpacing(24)
        disposicion.addWidget(self.titulo_acciones)
        disposicion.addWidget(self.contenedor_acciones)
        disposicion.addStretch()
        disposicion.addWidget(
            self.boton_volver,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

    def mostrar(
        self,
        curso: CursoMoodle,
        acciones: Sequence[AccionCurso] = (),
    ) -> None:
        """Actualiza el encabezado y crea un botón para cada acción indicada."""
        self.curso = curso
        self.nombre_curso.setText(curso.nombre)
        self._vaciar_acciones()

        self.sin_acciones.setVisible(not acciones)
        for accion in acciones:
            boton = QPushButton()
            boton.setFixedSize(TAMANO_BOTON_ACCION)
            boton.setIcon(accion.icono)
            boton.setIconSize(accion.tamano_icono)
            boton.setToolTip(accion.nombre)
            boton.setAccessibleName(accion.nombre)
            boton.setStyleSheet(
                "QPushButton { background: #263746; border: 2px solid #056bcf; "
                "border-radius: 10px; padding: 18px 28px; }"
                "QPushButton:hover { background: #30485d; }"
                "QPushButton:pressed { background: #1d2b37; }"
                "QPushButton:focus { border: 3px solid #f43737; }"
            )
            boton.clicked.connect(
                lambda comprobado=False, accion=accion: self.accion_solicitada.emit(
                    accion.identificador, accion.url
                )
            )
            self.disposicion_acciones.addWidget(boton)

    def limpiar(self) -> None:
        """Descarta el curso cuando se cierra la sesión."""
        self.curso = None
        self.nombre_curso.clear()
        self._vaciar_acciones()
        self.sin_acciones.show()

    def _vaciar_acciones(self) -> None:
        """Elimina los botones de la selección anterior y conserva el aviso."""
        while self.disposicion_acciones.count() > 1:
            elemento = self.disposicion_acciones.takeAt(1)
            widget = elemento.widget()
            if widget is not None:
                widget.deleteLater()


def crear_accion_level_up(url: str) -> AccionCurso:
    """Crea la presentación homogénea de la acción Level up."""
    return AccionCurso(
        identificador="level_up",
        nombre="Level up / Sube de nivel",
        url=url,
        icono=QIcon(str(DIRECTORIO_ICONOS / "logo-inverse.svg")),
    )


def crear_accion_guardar_examenes(url: str) -> AccionCurso:
    """Crea la acción para seleccionar actividades que se almacenarán."""
    return AccionCurso(
        identificador="guardar_examenes",
        nombre="Almacenar exámenes digitales",
        url=url,
        icono=QIcon(str(DIRECTORIO_ICONOS / "GuardarExamenes2.png")),
        tamano_icono=QSize(180, 60),
    )
