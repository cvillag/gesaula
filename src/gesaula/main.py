"""Punto de entrada de la aplicación."""

import sys

from PySide6.QtWidgets import QApplication

from gesaula.resources import crear_icono_aplicacion
from gesaula.ui.main_window import VentanaPrincipal


def main() -> int:
    """Arranca la aplicación."""
    aplicacion = QApplication(sys.argv)
    aplicacion.setApplicationName("gesaula")
    aplicacion.setWindowIcon(crear_icono_aplicacion())

    ventana = VentanaPrincipal()
    ventana.show()
    return aplicacion.exec()


if __name__ == "__main__":
    raise SystemExit(main())
