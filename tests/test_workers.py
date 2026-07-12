"""Pruebas de los trabajos en segundo plano."""

from gesaula.ui.workers import _decodificar_data_uri


def test_decodifica_imagen_svg_base64_de_moodle() -> None:
    """Las imágenes predeterminadas llegan embebidas y no necesitan HTTP."""
    uri = "data:image/svg+xml;base64,PHN2Zy8+"

    assert _decodificar_data_uri(uri) == b"<svg/>"


def test_data_uri_invalida_no_interrumpe_la_carga() -> None:
    """Una tarjeta defectuosa no debe impedir que se procesen las siguientes."""
    assert _decodificar_data_uri("data:image/svg+xml;base64,%%%") is None
