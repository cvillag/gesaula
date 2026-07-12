"""Acceso a los recursos gráficos de la aplicación."""

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon

DIRECTORIO_ICONOS = Path(__file__).parent / "icons"


def crear_icono_aplicacion() -> QIcon:
    """Crea el icono con las resoluciones disponibles."""
    icono = QIcon()
    for tamano in (16, 32, 64, 128, 256, 512):
        ruta = DIRECTORIO_ICONOS / f"logo{tamano}.png"
        icono.addFile(str(ruta), QSize(tamano, tamano))
    return icono
