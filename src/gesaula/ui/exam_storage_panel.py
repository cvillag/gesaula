"""Pantalla para seleccionar actividades que se almacenarán localmente."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gesaula.moodle.models import ActividadDescargable, CursoMoodle


class PanelAlmacenarExamenes(QWidget):
    """Muestra las actividades compatibles y su estado de selección."""

    volver_solicitado = Signal()
    descarga_solicitada = Signal(object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.curso: CursoMoodle | None = None
        self.actividades: tuple[ActividadDescargable, ...] = ()
        self.destino: Path | None = None
        self._descargando = False

        self.titulo = QLabel()
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.titulo.setWordWrap(True)
        self.titulo.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.estado = QLabel()
        self.estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.estado.setWordWrap(True)

        self.tabla = QTableWidget(0, 2)
        self.tabla.setHorizontalHeaderLabels(("Descargar", "Actividad"))
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla.setColumnWidth(0, 90)
        self.tabla.itemChanged.connect(self._actualizar_boton_descarga)

        self.boton_marcar_todos = QPushButton("Marcar todos")
        self.boton_marcar_todos.setEnabled(False)
        self.boton_marcar_todos.clicked.connect(self.marcar_todos)
        self.boton_desmarcar_todos = QPushButton("Desmarcar todos")
        self.boton_desmarcar_todos.setEnabled(False)
        self.boton_desmarcar_todos.clicked.connect(self.desmarcar_todos)
        disposicion_seleccion = QHBoxLayout()
        disposicion_seleccion.addStretch()
        disposicion_seleccion.addWidget(self.boton_marcar_todos)
        disposicion_seleccion.addWidget(self.boton_desmarcar_todos)

        self.boton_destino = QPushButton("Seleccionar carpeta…")
        self.boton_destino.clicked.connect(self.seleccionar_destino)
        self.etiqueta_destino = QLabel("Ninguna carpeta seleccionada")
        self.etiqueta_destino.setWordWrap(True)
        self.etiqueta_destino.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        disposicion_destino = QHBoxLayout()
        disposicion_destino.addWidget(self.boton_destino)
        disposicion_destino.addWidget(self.etiqueta_destino, stretch=1)

        self.boton_descargar = QPushButton("Guardar actividades seleccionadas")
        self.boton_descargar.setEnabled(False)
        self.boton_descargar.clicked.connect(self.iniciar_descarga)

        self.etiqueta_progreso_principal = QLabel()
        self.progreso_principal = QProgressBar()
        self.progreso_principal.hide()
        self.etiqueta_progreso_secundario = QLabel()
        self.progreso_secundario = QProgressBar()
        self.progreso_secundario.hide()

        self.boton_volver = QPushButton("Volver a Acciones")
        self.boton_volver.clicked.connect(self.volver_solicitado.emit)

        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(30, 24, 30, 24)
        disposicion.addWidget(self.titulo)
        disposicion.addWidget(self.estado)
        disposicion.addLayout(disposicion_seleccion)
        disposicion.addWidget(self.tabla)
        disposicion.addLayout(disposicion_destino)
        disposicion.addWidget(
            self.boton_descargar,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        disposicion.addWidget(self.etiqueta_progreso_principal)
        disposicion.addWidget(self.progreso_principal)
        disposicion.addWidget(self.etiqueta_progreso_secundario)
        disposicion.addWidget(self.progreso_secundario)
        disposicion.addWidget(
            self.boton_volver,
            alignment=Qt.AlignmentFlag.AlignHCenter,
        )

    def mostrar_cargando(self, curso: CursoMoodle) -> None:
        """Prepara la pantalla mientras se analiza la página del curso."""
        self.curso = curso
        self.actividades = ()
        self.destino = None
        self._descargando = False
        self.titulo.setText(
            f"Almacenar exámenes digitales — {curso.nombre}"
        )
        self.estado.setStyleSheet("")
        self.estado.setText("Buscando actividades compatibles…")
        self.tabla.setRowCount(0)
        self.tabla.setEnabled(False)
        self._habilitar_botones_seleccion(False)
        self.etiqueta_destino.setText("Ninguna carpeta seleccionada")
        self.boton_descargar.setEnabled(False)
        self._limpiar_progreso()

    def mostrar_actividades(
        self,
        actividades: tuple[ActividadDescargable, ...],
    ) -> None:
        """Crea una fila seleccionable para cada actividad encontrada."""
        self.actividades = actividades
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(actividades))
        for fila, actividad in enumerate(actividades):
            seleccion = QTableWidgetItem()
            implementada = actividad.tipo in {"Cuestionario", "Tarea"}
            banderas = (
                Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            if implementada:
                banderas |= Qt.ItemFlag.ItemIsEnabled
            seleccion.setFlags(banderas)
            seleccion.setCheckState(
                Qt.CheckState.Checked
                if implementada
                else Qt.CheckState.Unchecked
            )
            seleccion.setData(Qt.ItemDataRole.UserRole, actividad.id)
            seleccion.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            nombre = QTableWidgetItem(actividad.nombre)
            nombre.setData(Qt.ItemDataRole.UserRole, actividad.id)
            nombre.setToolTip(
                f"{actividad.tipo}\n{actividad.url}"
                + (
                    ""
                    if implementada
                    else "\nLa descarga de este tipo se añadirá más adelante."
                )
            )
            if not implementada:
                nombre.setFlags(nombre.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.tabla.setItem(fila, 0, seleccion)
            self.tabla.setItem(fila, 1, nombre)

        self.tabla.blockSignals(False)
        self.tabla.setEnabled(True)
        almacenables = sum(
            actividad.tipo in {"Cuestionario", "Tarea"}
            for actividad in actividades
        )
        cuestionarios = sum(
            actividad.tipo == "Cuestionario" for actividad in actividades
        )
        tareas = sum(actividad.tipo == "Tarea" for actividad in actividades)
        self._habilitar_botones_seleccion(almacenables > 0)
        self.estado.setStyleSheet("")
        self.estado.setText(
            f"{len(actividades)} actividades compatibles; "
            f"{cuestionarios} cuestionarios y {tareas} tareas disponibles para guardar."
            if actividades
            else "No se encontraron actividades compatibles en el curso."
        )
        self._actualizar_boton_descarga()

    def marcar_todos(self) -> None:
        """Marca todas las actividades cuya descarga está implementada."""
        self._cambiar_seleccion_total(Qt.CheckState.Checked)

    def desmarcar_todos(self) -> None:
        """Desmarca todas las actividades cuya descarga está implementada."""
        self._cambiar_seleccion_total(Qt.CheckState.Unchecked)

    def actividades_seleccionadas(self) -> tuple[ActividadDescargable, ...]:
        """Devuelve las actividades cuya casilla permanece marcada."""
        ids = {
            int(elemento.data(Qt.ItemDataRole.UserRole))
            for fila in range(self.tabla.rowCount())
            if (elemento := self.tabla.item(fila, 0)) is not None
            and elemento.checkState() == Qt.CheckState.Checked
        }
        return tuple(
            actividad for actividad in self.actividades if actividad.id in ids
        )

    def mostrar_error(self, mensaje: str) -> None:
        """Informa de un fallo al consultar las actividades."""
        self.estado.setStyleSheet("color: #b42318;")
        self.estado.setText(mensaje)
        self.tabla.setEnabled(False)
        self._habilitar_botones_seleccion(False)

    def seleccionar_destino(self) -> None:
        """Solicita la carpeta raíz donde se creará el archivo digital."""
        ruta = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta de destino",
            str(self.destino or Path.home()),
        )
        if not ruta:
            return
        self.destino = Path(ruta)
        self.etiqueta_destino.setText(str(self.destino))
        self.etiqueta_destino.setToolTip(str(self.destino))
        self._actualizar_boton_descarga()

    def iniciar_descarga(self) -> None:
        """Emite la selección preparada para comenzar el archivado."""
        actividades = self.actividades_seleccionadas()
        if not actividades or self.destino is None or self._descargando:
            return
        self.descarga_solicitada.emit(actividades, str(self.destino))

    def iniciar_analisis(self, total_elementos: int) -> None:
        """Bloquea la selección durante el inventario previo."""
        self._descargando = True
        self.tabla.setEnabled(False)
        self._habilitar_botones_seleccion(False)
        self.boton_destino.setEnabled(False)
        self.boton_descargar.setEnabled(False)
        self.boton_volver.setEnabled(False)
        self.progreso_principal.setRange(0, total_elementos)
        self.progreso_principal.setValue(0)
        self.progreso_principal.show()
        self.progreso_secundario.setRange(0, 1)
        self.progreso_secundario.setValue(0)
        self.progreso_secundario.show()
        self.etiqueta_progreso_principal.setText(
            "Analizando actividades seleccionadas…"
        )
        self.etiqueta_progreso_secundario.setText(
            "Esperando el primer cuestionario…"
        )

    def iniciar_analisis_elemento(
        self,
        numero: int,
        total: int,
        nombre: str,
        estimados: int,
    ) -> None:
        """Muestra la aproximación de la portada mientras consulta el informe."""
        self.progreso_principal.setRange(0, total)
        self.progreso_principal.setValue(numero - 1)
        self.etiqueta_progreso_principal.setText(
            f"Analizando {numero} de {total}: {nombre}"
        )
        self.progreso_secundario.setRange(0, max(1, estimados))
        self.progreso_secundario.setValue(0)
        self.etiqueta_progreso_secundario.setText(
            f"Buscando intentos revisables; aproximación de Moodle: {estimados}"
        )

    def actualizar_analisis(
        self,
        procesados: int,
        total: int,
        nombre: str,
    ) -> None:
        """Muestra el avance del inventario inicial."""
        self.progreso_principal.setMaximum(total)
        self.progreso_principal.setValue(procesados)
        self.etiqueta_progreso_principal.setText(
            f"Analizando {procesados} de {total}: {nombre}"
        )

    def completar_analisis_elemento(
        self,
        numero: int,
        total: int,
        nombre: str,
        estimados: int,
        reales: int,
    ) -> None:
        """Presenta el recuento real localizado en todas las páginas."""
        self.progreso_principal.setRange(0, total)
        self.progreso_principal.setValue(numero)
        self.progreso_secundario.setRange(0, max(1, reales))
        self.progreso_secundario.setValue(reales)
        diferencia = (
            f" (la portada indicaba aproximadamente {estimados})"
            if estimados != reales
            else ""
        )
        descripcion = (
            "1 intento revisable"
            if reales == 1
            else f"{reales} intentos revisables"
        )
        self.etiqueta_progreso_secundario.setText(
            f"{descripcion} encontrados en {nombre}{diferencia}"
        )

    def iniciar_analisis_tarea(
        self,
        numero: int,
        total: int,
        nombre: str,
    ) -> None:
        """Muestra la consulta de la pestaña Entregas de una tarea."""
        self.progreso_principal.setRange(0, total)
        self.progreso_principal.setValue(numero - 1)
        self.etiqueta_progreso_principal.setText(
            f"Analizando {numero} de {total}: {nombre}"
        )
        self.progreso_secundario.setRange(0, 0)
        self.etiqueta_progreso_secundario.setText(
            "Recorriendo las páginas de Entregas…"
        )

    def completar_analisis_tarea(
        self,
        numero: int,
        total: int,
        nombre: str,
        alumnos: int,
    ) -> None:
        """Muestra los alumnos encontrados en la tabla de entregas."""
        self.progreso_principal.setRange(0, total)
        self.progreso_principal.setValue(numero)
        self.progreso_secundario.setRange(0, max(1, alumnos))
        self.progreso_secundario.setValue(alumnos)
        descripcion = "1 alumno" if alumnos == 1 else f"{alumnos} alumnos"
        self.etiqueta_progreso_secundario.setText(
            f"{descripcion} encontrados en {nombre}"
        )

    def mostrar_inventario(
        self,
        elementos: int,
        alumnos: int,
        intentos: int,
    ) -> None:
        """Muestra el tamaño calculado antes de descargar las revisiones."""
        self.progreso_principal.setRange(0, elementos)
        self.progreso_principal.setValue(0)
        self.progreso_secundario.setRange(0, 1)
        self.progreso_secundario.setValue(0)
        self.etiqueta_progreso_principal.setText(
            f"{elementos} actividades · {alumnos} alumnos · "
            f"{intentos} registros"
        )
        self.etiqueta_progreso_secundario.setText(
            f"Máximo teórico: {elementos} elementos × {alumnos} alumnos; "
            f"{intentos} intentos o entregas reales."
        )

    def iniciar_elemento(
        self,
        numero: int,
        total: int,
        nombre: str,
        intentos: int,
    ) -> None:
        """Reinicia la barra secundaria para un cuestionario."""
        self.progreso_principal.setRange(0, total)
        self.progreso_principal.setValue(numero - 1)
        self.etiqueta_progreso_principal.setText(
            f"Cuestionario {numero} de {total}: {nombre}"
        )
        self.progreso_secundario.setRange(0, max(1, intentos))
        self.progreso_secundario.setValue(0)
        self.etiqueta_progreso_secundario.setText(
            f"0 de {intentos} intentos"
        )

    def actualizar_intento(
        self,
        procesados: int,
        total: int,
        alumno: str,
    ) -> None:
        """Avanza la barra secundaria tras guardar una revisión."""
        self.progreso_secundario.setMaximum(max(1, total))
        self.progreso_secundario.setValue(procesados)
        self.etiqueta_progreso_secundario.setText(
            f"{procesados} de {total}: {alumno}"
        )

    def iniciar_tarea(
        self,
        numero: int,
        total: int,
        nombre: str,
        entregas: int,
    ) -> None:
        """Reinicia la barra secundaria para una tarea."""
        self.progreso_principal.setRange(0, total)
        self.progreso_principal.setValue(numero - 1)
        self.etiqueta_progreso_principal.setText(
            f"Tarea {numero} de {total}: {nombre}"
        )
        self.progreso_secundario.setRange(0, max(1, entregas))
        self.progreso_secundario.setValue(0)
        self.etiqueta_progreso_secundario.setText(
            f"0 de {entregas} alumnos"
        )

    def actualizar_entrega(
        self,
        procesados: int,
        total: int,
        alumno: str,
    ) -> None:
        """Avanza la barra después de archivar una entrega o calificación."""
        self.progreso_secundario.setMaximum(max(1, total))
        self.progreso_secundario.setValue(procesados)
        self.etiqueta_progreso_secundario.setText(
            f"{procesados} de {total}: {alumno}"
        )

    def completar_elemento(self, procesados: int, total: int) -> None:
        """Avanza la barra principal al terminar un cuestionario."""
        self.progreso_principal.setMaximum(total)
        self.progreso_principal.setValue(procesados)

    def completar_descarga(
        self,
        destino: str,
        elementos: int,
        intentos: int,
    ) -> None:
        """Informa del resultado y restaura los controles."""
        self._descargando = False
        self.progreso_principal.setValue(self.progreso_principal.maximum())
        self.estado.setStyleSheet("color: #16752c;")
        self.estado.setText(
            f"Guardados {intentos} registros de {elementos} actividades en {destino}."
        )
        self.tabla.setEnabled(True)
        self._habilitar_botones_seleccion(True)
        self.boton_destino.setEnabled(True)
        self.boton_volver.setEnabled(True)
        self._actualizar_boton_descarga()
        self._mostrar_aviso_finalizacion(destino, elementos, intentos)

    def fallar_descarga(self, mensaje: str) -> None:
        """Detiene el proceso conservando los archivos ya escritos."""
        self._descargando = False
        self.estado.setStyleSheet("color: #b42318;")
        self.estado.setText(
            f"Descarga detenida: {mensaje}. Los archivos anteriores se conservan."
        )
        self.tabla.setEnabled(True)
        self._habilitar_botones_seleccion(True)
        self.boton_destino.setEnabled(True)
        self.boton_volver.setEnabled(True)
        self._actualizar_boton_descarga()

    def _mostrar_aviso_finalizacion(
        self,
        destino: str,
        elementos: int,
        registros: int,
    ) -> None:
        """Ofrece abrir el resultado o regresar a las acciones del curso."""
        aviso = QMessageBox(self)
        aviso.setIcon(QMessageBox.Icon.Information)
        aviso.setWindowTitle("Operación terminada")
        aviso.setText("El almacenamiento de exámenes ha terminado.")
        aviso.setInformativeText(
            f"Se han guardado {registros} registros de {elementos} "
            f"actividades en:\n{destino}"
        )
        boton_abrir = aviso.addButton(
            "Ver carpeta",
            QMessageBox.ButtonRole.ActionRole,
        )
        boton_volver = aviso.addButton(
            "Volver a las acciones",
            QMessageBox.ButtonRole.AcceptRole,
        )
        aviso.setDefaultButton(boton_volver)
        aviso.exec()

        if aviso.clickedButton() is boton_abrir:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(Path(destino).resolve()))
            )
        elif aviso.clickedButton() is boton_volver:
            self.volver_solicitado.emit()

    def limpiar(self) -> None:
        """Descarta los datos de la sesión anterior."""
        self.curso = None
        self.actividades = ()
        self.destino = None
        self._descargando = False
        self.titulo.clear()
        self.estado.clear()
        self.estado.setStyleSheet("")
        self.tabla.setRowCount(0)
        self._habilitar_botones_seleccion(False)
        self.etiqueta_destino.setText("Ninguna carpeta seleccionada")
        self.etiqueta_destino.setToolTip("")
        self._limpiar_progreso()

    def _actualizar_boton_descarga(self, elemento: object = None) -> None:
        self.boton_descargar.setEnabled(
            not self._descargando
            and self.destino is not None
            and bool(self.actividades_seleccionadas())
        )

    def _cambiar_seleccion_total(self, estado: Qt.CheckState) -> None:
        if self._descargando:
            return
        self.tabla.blockSignals(True)
        for fila in range(self.tabla.rowCount()):
            elemento = self.tabla.item(fila, 0)
            if (
                elemento is not None
                and elemento.flags() & Qt.ItemFlag.ItemIsEnabled
            ):
                elemento.setCheckState(estado)
        self.tabla.blockSignals(False)
        self._actualizar_boton_descarga()

    def _habilitar_botones_seleccion(self, habilitados: bool) -> None:
        self.boton_marcar_todos.setEnabled(habilitados and not self._descargando)
        self.boton_desmarcar_todos.setEnabled(
            habilitados and not self._descargando
        )

    def _limpiar_progreso(self) -> None:
        self.progreso_principal.hide()
        self.progreso_secundario.hide()
        self.etiqueta_progreso_principal.clear()
        self.etiqueta_progreso_secundario.clear()
