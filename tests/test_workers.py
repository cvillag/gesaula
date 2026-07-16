"""Pruebas de los trabajos en segundo plano."""

from gesaula.actions.calificaciones_ods import (
    AlumnoCalificaciones,
    ColumnaCalificacion,
    InformeCalificaciones,
    SeleccionCalificaciones,
)
from gesaula.moodle.models import AlumnoLevelUp
from gesaula.ui.workers import (
    ActualizarPxLevelUp,
    AplicarCalificacionesLevelUp,
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
        AplicarCalificacionesLevelUp(
            cliente,  # type: ignore[arg-type]
            1203,
            "https://aula.test/informe",
            InformeCalificaciones(
                "Calificaciones",
                (ColumnaCalificacion(3, "Control"),),
                (AlumnoCalificaciones("Ana", "Ejemplo", "", (5.0,)),),
            ),
            SeleccionCalificaciones(
                (ColumnaCalificacion(3, "Control"),),
                10,
            ),
        ),
    )

    assert all(not trabajo.autoDelete() for trabajo in trabajos)


def test_aplica_calificaciones_en_orden_y_emite_progreso() -> None:
    columna = ColumnaCalificacion(3, "Control")
    informe = InformeCalificaciones(
        "Calificaciones",
        (columna,),
        (
            AlumnoCalificaciones("Ana", "Ejemplo", "", (7.1,)),
            AlumnoCalificaciones("Luis", "Prueba", "", (5.0,)),
        ),
    )

    class ClientePrueba:
        def __init__(self) -> None:
            self.llamadas: list[tuple[int, int, int]] = []

        def obtener_alumnos_level_up(
            self,
            url: str,
        ) -> tuple[AlumnoLevelUp, ...]:
            return (
                AlumnoLevelUp(42, "Ana Ejemplo", 1, 100, 85744),
                AlumnoLevelUp(43, "Luis Prueba", 1, 200, 85744),
            )

        def actualizar_px_level_up(
            self,
            alumno_id: int,
            context_id: int,
            nuevo_total: int,
        ) -> None:
            self.llamadas.append((alumno_id, context_id, nuevo_total))

    cliente = ClientePrueba()
    trabajo = AplicarCalificacionesLevelUp(
        cliente,  # type: ignore[arg-type]
        1203,
        "https://aula.test/informe",
        informe,
        SeleccionCalificaciones((columna,), 10),
    )
    progresos: list[tuple[int, int, str]] = []
    trabajo.senales.progreso.connect(
        lambda procesados, total, nombre: progresos.append(
            (procesados, total, nombre)
        )
    )

    trabajo.run()

    assert cliente.llamadas == [
        (42, 85744, 171),
        (43, 85744, 250),
    ]
    assert progresos == [
        (1, 2, "Ana Ejemplo"),
        (2, 2, "Luis Prueba"),
    ]
