"""Diálogo para preparar columnas de calificaciones y su multiplicador."""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gesaula.actions.calificaciones_ods import (
    ColumnaCalificacion,
    InformeCalificaciones,
    SeleccionCalificaciones,
)


class DialogoCalificaciones(QDialog):
    """Recoge las columnas que se usarán y el factor de conversión."""

    aplicar_solicitado = Signal(object)

    def __init__(
        self,
        informe: InformeCalificaciones,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.informe = informe
        self.seleccion: SeleccionCalificaciones | None = None
        self.proceso_completado = False
        self.setWindowTitle("Preparar calificaciones")
        self.resize(760, 520)

        explicacion = QLabel(
            "Seleccione una o varias columnas de calificación y establezca "
            "el multiplicador que se aplicará a sus valores."
        )
        explicacion.setWordWrap(True)

        resumen = QLabel(
            f"Hoja: {informe.hoja} · "
            f"{len(informe.alumnos)} alumnos · "
            f"{len(informe.columnas)} columnas de calificación"
        )
        resumen.setStyleSheet("color: #52606d;")

        self.lista_columnas = QListWidget()
        self.lista_columnas.setAlternatingRowColors(True)
        for columna in informe.columnas:
            elemento = QListWidgetItem(columna.nombre)
            elemento.setData(Qt.ItemDataRole.UserRole, columna)
            elemento.setFlags(
                elemento.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            elemento.setCheckState(Qt.CheckState.Unchecked)
            elemento.setToolTip(columna.nombre)
            self.lista_columnas.addItem(elemento)

        self.multiplicador = QSpinBox()
        self.multiplicador.setRange(1, 100_000)
        self.multiplicador.setValue(1)

        formulario = QFormLayout()
        formulario.addRow("Multiplicador:", self.multiplicador)

        self.error = QLabel()
        self.error.setStyleSheet("color: #b42318;")
        self.error.setWordWrap(True)

        self.progreso = QProgressBar()
        self.progreso.setMinimum(0)
        self.progreso.hide()
        self.estado_progreso = QLabel()
        self.estado_progreso.setWordWrap(True)

        self.boton_cancelar = QPushButton("Cancelar")
        self.boton_cancelar.clicked.connect(self.reject)
        self.boton_aplicar = QPushButton("Aplicar")
        self.boton_aplicar.setDefault(True)
        self.boton_aplicar.clicked.connect(self.aplicar)

        botones = QHBoxLayout()
        botones.addStretch()
        botones.addWidget(self.boton_cancelar)
        botones.addWidget(self.boton_aplicar)

        disposicion = QVBoxLayout(self)
        disposicion.addWidget(explicacion)
        disposicion.addWidget(resumen)
        disposicion.addWidget(self.lista_columnas)
        disposicion.addLayout(formulario)
        disposicion.addWidget(self.error)
        disposicion.addWidget(self.progreso)
        disposicion.addWidget(self.estado_progreso)
        disposicion.addLayout(botones)

    def aplicar(self) -> None:
        """Valida la selección y solicita que comience la actualización."""
        columnas: list[ColumnaCalificacion] = []
        for indice in range(self.lista_columnas.count()):
            elemento = self.lista_columnas.item(indice)
            columna = elemento.data(Qt.ItemDataRole.UserRole)
            if (
                elemento.checkState() == Qt.CheckState.Checked
                and isinstance(columna, ColumnaCalificacion)
            ):
                columnas.append(columna)
        if not columnas:
            self.error.setText("Seleccione al menos una columna de calificación.")
            return

        self.seleccion = SeleccionCalificaciones(
            columnas=tuple(columnas),
            multiplicador=self.multiplicador.value(),
        )
        self.error.clear()
        self.boton_aplicar.setEnabled(False)
        self.aplicar_solicitado.emit(self.seleccion)

    def mostrar_error_preparacion(self, mensaje: str) -> None:
        """Permite corregir la selección cuando el plan no es seguro."""
        self.error.setText(mensaje)
        self.lista_columnas.setEnabled(True)
        self.multiplicador.setEnabled(True)
        self.boton_aplicar.setEnabled(True)
        self.boton_cancelar.setEnabled(True)
        self.progreso.hide()
        self.estado_progreso.clear()

    def iniciar_preparacion(self) -> None:
        """Bloquea el diálogo mientras se comprueban los PX actuales."""
        self.lista_columnas.setEnabled(False)
        self.multiplicador.setEnabled(False)
        self.boton_aplicar.setEnabled(False)
        self.boton_cancelar.setEnabled(False)
        self.progreso.setRange(0, 0)
        self.progreso.show()
        self.estado_progreso.setStyleSheet("")
        self.estado_progreso.setText(
            "Comprobando alumnado y experiencia actuales…"
        )

    def iniciar_proceso(self, total: int, omitidos: int) -> None:
        """Bloquea el formulario y muestra el progreso de las peticiones."""
        self.lista_columnas.setEnabled(False)
        self.multiplicador.setEnabled(False)
        self.boton_aplicar.setEnabled(False)
        self.boton_cancelar.setEnabled(False)
        self.progreso.setRange(0, total)
        self.progreso.setValue(0)
        self.progreso.show()
        texto_omitidos = (
            f" · {omitidos} sin calificación, no se modificarán"
            if omitidos
            else ""
        )
        self.estado_progreso.setStyleSheet("")
        self.estado_progreso.setText(
            f"Preparando {total} actualizaciones{texto_omitidos}…"
        )

    def actualizar_progreso(
        self,
        procesados: int,
        total: int,
        nombre: str,
    ) -> None:
        """Refleja cada alumno confirmado por Moodle."""
        self.progreso.setMaximum(total)
        self.progreso.setValue(procesados)
        self.estado_progreso.setText(
            f"{procesados} de {total}: {nombre}"
        )

    def completar_proceso(self) -> None:
        """Completa la barra y cierra el diálogo tras una breve confirmación."""
        self.progreso.setValue(self.progreso.maximum())
        self.estado_progreso.setStyleSheet("color: #16752c;")
        self.estado_progreso.setText("Actualización completada. Recargando Level up…")
        self.proceso_completado = True
        QTimer.singleShot(250, self.accept)

    def mostrar_error_proceso(self, mensaje: str) -> None:
        """Mantiene visible el progreso parcial cuando una petición falla."""
        self.estado_progreso.setStyleSheet("color: #b42318;")
        self.estado_progreso.setText(mensaje)
        self.boton_cancelar.setText("Cerrar")
        self.boton_cancelar.setEnabled(True)
