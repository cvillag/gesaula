"""Pantalla del informe de alumnos de Level up."""

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gesaula.moodle.models import AlumnoLevelUp, CursoMoodle

PUNTOS_DISPONIBLES = (10, 50, 100, 200, 400, 600, 800, 1000)
FILAS_VISIBLES = 15
ALTO_FILA = 36


class PanelLevelUp(QWidget):
    """Muestra el alumnado y prepara las futuras acciones de puntos."""

    volver_solicitado = Signal()
    sumar_px_solicitado = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.curso: CursoMoodle | None = None
        self.url_informe: str | None = None
        self.archivo_seleccionado: Path | None = None
        self.alumnos: dict[int, AlumnoLevelUp] = {}
        self._fila_por_alumno: dict[int, int] = {}

        self.titulo = QLabel()
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.titulo.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.estado = QLabel()
        self.estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.estado.setWordWrap(True)

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(("Nombre", "Nivel", "PX", "Acciones"))
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setWordWrap(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(ALTO_FILA)
        self.tabla.setFixedHeight(
            self.tabla.horizontalHeader().sizeHint().height()
            + FILAS_VISIBLES * ALTO_FILA
            + 4
        )
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        cabecera.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        cabecera.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tabla.setColumnWidth(1, 70)
        self.tabla.setColumnWidth(2, 90)
        self.tabla.setColumnWidth(3, 500)

        separador = QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        separador.setFrameShadow(QFrame.Shadow.Sunken)

        self.boton_archivo = QPushButton("Seleccionar archivo…")
        self.boton_archivo.clicked.connect(self.seleccionar_archivo)
        self.nombre_archivo = QLabel("Ningún archivo seleccionado")
        self.nombre_archivo.setWordWrap(True)
        self.nombre_archivo.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        disposicion_archivo = QHBoxLayout()
        disposicion_archivo.addWidget(self.boton_archivo)
        disposicion_archivo.addWidget(self.nombre_archivo, stretch=1)

        self.boton_volver = QPushButton("Volver a Acciones")
        self.boton_volver.clicked.connect(self.volver_solicitado.emit)

        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(30, 24, 30, 24)
        disposicion.addWidget(self.titulo)
        disposicion.addWidget(self.estado)
        disposicion.addWidget(self.tabla)
        disposicion.addWidget(separador)
        disposicion.addLayout(disposicion_archivo)
        disposicion.addStretch()
        disposicion.addWidget(
            self.boton_volver,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

    def mostrar_cargando(self, curso: CursoMoodle, url_informe: str) -> None:
        """Prepara la pantalla mientras se descarga el informe."""
        self.curso = curso
        self.url_informe = url_informe
        self.archivo_seleccionado = None
        self.titulo.setText(f"Level up — {curso.nombre}")
        self.estado.setStyleSheet("")
        self.estado.setText("Cargando alumnado…")
        self.tabla.setRowCount(0)
        self.tabla.setEnabled(False)
        self.alumnos.clear()
        self._fila_por_alumno.clear()
        self.nombre_archivo.setText("Ningún archivo seleccionado")
        self.nombre_archivo.setToolTip("")

    def mostrar_alumnos(self, alumnos: tuple[AlumnoLevelUp, ...]) -> None:
        """Rellena la tabla con los datos obtenidos de Moodle."""
        self.tabla.setRowCount(len(alumnos))
        self.alumnos = {alumno.id: alumno for alumno in alumnos}
        self._fila_por_alumno = {
            alumno.id: fila for fila, alumno in enumerate(alumnos)
        }
        for fila, alumno in enumerate(alumnos):
            nombre = QTableWidgetItem(alumno.nombre)
            nombre.setData(Qt.ItemDataRole.UserRole, alumno.id)
            nivel = QTableWidgetItem(str(alumno.nivel))
            px = QTableWidgetItem(str(alumno.px))
            nivel.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            px.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabla.setItem(fila, 0, nombre)
            self.tabla.setItem(fila, 1, nivel)
            self.tabla.setItem(fila, 2, px)
            self.tabla.setCellWidget(fila, 3, self._crear_botones(alumno))

        self.tabla.setEnabled(True)
        self.estado.setStyleSheet("")
        self.estado.setText(
            f"{len(alumnos)} alumno{'s' if len(alumnos) != 1 else ''}"
            if alumnos
            else "No se encontraron alumnos en el informe."
        )

    def mostrar_error(self, mensaje: str) -> None:
        """Informa de un error al obtener el informe."""
        self.tabla.setEnabled(False)
        self.estado.setStyleSheet("color: #b42318;")
        self.estado.setText(mensaje)

    def iniciar_actualizacion(self, alumno_id: int) -> None:
        """Bloquea la fila mientras Moodle procesa el nuevo total."""
        self._habilitar_acciones(alumno_id, False)
        self.estado.setStyleSheet("")
        self.estado.setText("Actualizando PX…")

    def completar_actualizacion(self, alumno_id: int, nuevo_total: int) -> None:
        """Refleja el total confirmado por Moodle y reactiva la fila."""
        alumno = self.alumnos.get(alumno_id)
        fila = self._fila_por_alumno.get(alumno_id)
        if alumno is None or fila is None:
            return
        self.alumnos[alumno_id] = replace(alumno, px=nuevo_total)
        elemento_px = self.tabla.item(fila, 2)
        if elemento_px is not None:
            elemento_px.setText(str(nuevo_total))
        self._habilitar_acciones(alumno_id, True)
        self.estado.setStyleSheet("color: #16752c;")
        self.estado.setText(f"PX de {alumno.nombre} actualizados a {nuevo_total}.")

    def cancelar_actualizacion(self, alumno_id: int, mensaje: str) -> None:
        """Reactiva la fila cuando Moodle rechaza o no completa el cambio."""
        self._habilitar_acciones(alumno_id, True)
        self.estado.setStyleSheet("color: #b42318;")
        self.estado.setText(mensaje)

    def limpiar(self) -> None:
        """Descarta los datos del informe al cerrar la sesión."""
        self.curso = None
        self.url_informe = None
        self.archivo_seleccionado = None
        self.titulo.clear()
        self.estado.clear()
        self.estado.setStyleSheet("")
        self.tabla.setRowCount(0)
        self.alumnos.clear()
        self._fila_por_alumno.clear()
        self.nombre_archivo.setText("Ningún archivo seleccionado")
        self.nombre_archivo.setToolTip("")

    def seleccionar_archivo(self) -> None:
        """Permite elegir el archivo que se procesará en una fase posterior."""
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo",
            str(
                self.archivo_seleccionado.parent
                if self.archivo_seleccionado
                else Path.home()
            ),
            "Todos los archivos (*)",
        )
        if not ruta:
            return
        self.archivo_seleccionado = Path(ruta)
        self.nombre_archivo.setText(str(self.archivo_seleccionado))
        self.nombre_archivo.setToolTip(str(self.archivo_seleccionado))

    def _crear_botones(self, alumno: AlumnoLevelUp) -> QWidget:
        contenedor = QWidget()
        disposicion = QHBoxLayout(contenedor)
        disposicion.setContentsMargins(4, 2, 4, 2)
        disposicion.setSpacing(4)
        for puntos in PUNTOS_DISPONIBLES:
            boton = QPushButton(str(puntos))
            boton.setFixedWidth(54)
            boton.setProperty("alumno_id", alumno.id)
            boton.setProperty("puntos", puntos)
            boton.setEnabled(alumno.context_id is not None)
            boton.setToolTip(
                f"Añadir {puntos} PX"
                if alumno.context_id is not None
                else "No se encontró el contexto Moodle del alumno"
            )
            boton.clicked.connect(
                lambda comprobado=False, alumno_id=alumno.id, puntos=puntos: (
                    self.sumar_px_solicitado.emit(alumno_id, puntos)
                )
            )
            disposicion.addWidget(boton)
        return contenedor

    def _habilitar_acciones(self, alumno_id: int, habilitadas: bool) -> None:
        fila = self._fila_por_alumno.get(alumno_id)
        if fila is None:
            return
        contenedor = self.tabla.cellWidget(fila, 3)
        if contenedor is not None:
            contenedor.setEnabled(habilitadas)
