"""Pruebas de los trabajos en segundo plano."""

from gesaula.ui.workers import (
    ActualizarPxLevelUp,
    CargarImagenesCursos,
    CargarInformeLevelUp,
    ComprobarRolProfesor,
    ComprobarUrl,
    IniciarSesion,
    _decodificar_data_uri,
)


def test_decodifica_imagen_svg_base64_de_moodle() -> None:
    """Las imágenes predeterminadas llegan embebidas y no necesitan HTTP."""
    uri = "data:image/svg+xml;base64,PHN2Zy8+"

    assert _decodificar_data_uri(uri) == b"<svg/>"


def test_data_uri_invalida_no_interrumpe_la_carga() -> None:
    """Una tarjeta defectuosa no debe impedir que se procesen las siguientes."""
    assert _decodificar_data_uri("data:image/svg+xml;base64,%%%") is None


def test_qt_no_autodestruye_trabajos_antes_de_procesar_sus_senales() -> None:
    """La interfaz conserva los QRunnable para evitar dobles liberaciones nativas."""
    cliente = object()
    trabajos = (
        ComprobarUrl("https://aula.test"),
        IniciarSesion("https://aula.test", "usuario", "secreto"),
        CargarImagenesCursos(cliente, ()),  # type: ignore[arg-type]
        ComprobarRolProfesor(cliente, 1203),  # type: ignore[arg-type]
        CargarInformeLevelUp(cliente, 1203, "https://aula.test/informe"),  # type: ignore[arg-type]
        ActualizarPxLevelUp(
            cliente,
            1203,
            42,
            85744,
            150,
            "https://aula.test/informe",
        ),  # type: ignore[arg-type]
    )

    assert all(not trabajo.autoDelete() for trabajo in trabajos)
