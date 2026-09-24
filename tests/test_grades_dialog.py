"""Pruebas de confirmación y resumen de alumnos ausentes."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

from gesaula.actions.calificaciones_ods import (
    AlumnoSinCoincidencia,
    ColumnaCalificacion,
    InformeCalificaciones,
)
from gesaula.ui.grades_dialog import DialogoCalificaciones


def test_confirma_omision_y_conserva_resumen(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    aplicacion = QApplication.instance() or QApplication([])
    columna = ColumnaCalificacion(3, "Control")
    dialogo = DialogoCalificaciones(InformeCalificaciones("Notas", (columna,), ()))
    selecciones = []
    dialogo.aplicar_solicitado.connect(selecciones.append)
    dialogo.lista_columnas.item(0).setCheckState(Qt.CheckState.Checked)
    dialogo.boton_aplicar.click()
    assert not selecciones[-1].omitir_no_encontrados

    ausentes = (AlumnoSinCoincidencia("María Muñoz Pérez", 137),)
    dialogo.iniciar_preparacion()
    dialogo.mostrar_sin_coincidencia(ausentes, False)
    assert not dialogo.boton_continuar.isHidden()
    assert "1 alumnos" in dialogo.error.text()
    dialogo.boton_continuar.click()
    assert selecciones[-1].omitir_no_encontrados

    dialogo.iniciar_preparacion()
    dialogo.mostrar_sin_coincidencia(ausentes, True)
    dialogo.iniciar_proceso(1, 0)
    dialogo.completar_proceso()
    aplicacion.processEvents()
    assert dialogo.lista_omitidos.item(0).text() == "María Muñoz Pérez — 137 PX sin aplicar"
    assert not dialogo.boton_aplicar.isEnabled()
    assert dialogo.boton_continuar.isHidden()
    assert dialogo.boton_cancelar.isEnabled()
    dialogo.boton_cancelar.click()
    assert dialogo.result() == QDialog.DialogCode.Accepted


def test_cambiar_seleccion_requiere_nueva_confirmacion(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    aplicacion = QApplication.instance() or QApplication([])
    columna = ColumnaCalificacion(3, "Control")
    dialogo = DialogoCalificaciones(InformeCalificaciones("Notas", (columna,), ()))
    dialogo.lista_columnas.item(0).setCheckState(Qt.CheckState.Checked)
    dialogo.mostrar_sin_coincidencia((AlumnoSinCoincidencia("Ana Pérez", 10),), False)
    dialogo.multiplicador.setValue(2)
    assert dialogo.boton_continuar.isHidden()
    dialogo.boton_aplicar.click()
    assert not dialogo.seleccion.omitir_no_encontrados
    aplicacion.processEvents()
    dialogo.close()
