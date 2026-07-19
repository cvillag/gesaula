"""Pruebas de los trabajos en segundo plano."""

from pathlib import Path

from gesaula.actions.calificaciones_ods import (
    AlumnoCalificaciones,
    ColumnaCalificacion,
    InformeCalificaciones,
    SeleccionCalificaciones,
)
from gesaula.moodle.models import (
    ActividadDescargable,
    AlumnoLevelUp,
    IntentoCuestionario,
)
from gesaula.ui.workers import (
    ActualizarPxLevelUp,
    AplicarCalificacionesLevelUp,
    CargarActividadesCurso,
    CargarImagenesCursos,
    CargarInformeLevelUp,
    ComprobarRolProfesor,
    ComprobarUrl,
    GuardarCuestionarios,
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
        CargarActividadesCurso(cliente, 1203),  # type: ignore[arg-type]
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
        GuardarCuestionarios(cliente, (), "/tmp"),  # type: ignore[arg-type]
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


def test_guarda_cuestionarios_y_emite_dos_niveles_de_progreso(
    tmp_path: Path,
) -> None:
    actividad = ActividadDescargable(
        10,
        "Control",
        "Cuestionario",
        "https://aula.test/mod/quiz/view.php?id=10",
    )
    intento = IntentoCuestionario(
        52049,
        42,
        "Ana Ejemplo",
        "https://aula.test/mod/quiz/review.php?attempt=52049",
    )
    url_adjunto = (
        "https://aula.test/pluginfile.php/1/question/"
        "response_attachments/2/1/respuesta.txt?forcedownload=1"
    )

    class Respuesta:
        def __init__(self, url: str, texto: str = "", contenido: bytes = b"") -> None:
            self.url = url
            self.text = texto
            self.content = contenido

    class ClientePrueba:
        def obtener_numero_intentos_cuestionario(
            self,
            actividad: ActividadDescargable,
        ) -> int:
            # La portada también cuenta una vista previa del profesor.
            return 2

        def obtener_intentos_cuestionario(
            self,
            actividad_id: int,
        ) -> tuple[IntentoCuestionario, ...]:
            return (intento,)

        def obtener(self, url: str) -> Respuesta:
            if "/review.php" in url:
                return Respuesta(
                    url,
                    f'<a href="{url_adjunto}">respuesta.txt</a>',
                )
            return Respuesta(url, contenido=b"contenido")

    trabajo = GuardarCuestionarios(
        ClientePrueba(),  # type: ignore[arg-type]
        (actividad,),
        tmp_path,
    )
    elementos: list[tuple[int, int]] = []
    intentos: list[tuple[int, int, str]] = []
    errores: list[str] = []
    trabajo.senales.elemento_completado.connect(
        lambda actual, total: elementos.append((actual, total))
    )
    trabajo.senales.intento_guardado.connect(
        lambda actual, total, alumno: intentos.append(
            (actual, total, alumno)
        )
    )
    trabajo.senales.descarga_fallida.connect(errores.append)

    trabajo.run()

    assert elementos == [(1, 1)]
    assert intentos == [(1, 1, "Ana Ejemplo")]
    assert errores == []
    ruta = (
        tmp_path
        / "Ana Ejemplo [usuario-42]"
        / "Control"
        / "intento-52049"
    )
    assert (ruta / "revision.html").is_file()
    assert (ruta / "archivos" / "respuesta.txt").read_bytes() == b"contenido"


def test_omite_informe_de_cuestionario_sin_intentos(tmp_path: Path) -> None:
    actividad = ActividadDescargable(
        10,
        "Control sin realizar",
        "Cuestionario",
        "https://aula.test/mod/quiz/view.php?id=10",
    )

    class ClientePrueba:
        def obtener_numero_intentos_cuestionario(
            self,
            actividad: ActividadDescargable,
        ) -> int:
            return 0

        def obtener_intentos_cuestionario(
            self,
            actividad_id: int,
        ) -> tuple[IntentoCuestionario, ...]:
            raise AssertionError("No debe abrir el informe sin intentos")

    trabajo = GuardarCuestionarios(
        ClientePrueba(),  # type: ignore[arg-type]
        (actividad,),
        tmp_path,
    )
    inventarios: list[tuple[int, int, int]] = []
    elementos: list[tuple[int, int]] = []
    trabajo.senales.inventario.connect(
        lambda *valores: inventarios.append(valores)
    )
    trabajo.senales.elemento_completado.connect(
        lambda actual, total: elementos.append((actual, total))
    )

    trabajo.run()

    assert inventarios == [(1, 0, 0)]
    assert elementos == [(1, 1)]


def test_guarda_tareas_desde_entregas_y_carga_rubrica_si_es_necesario(
    tmp_path: Path,
) -> None:
    actividad = ActividadDescargable(
        15,
        "Práctica UT2",
        "Tarea",
        "https://aula.test/mod/assign/view.php?id=15",
    )
    url_archivo = (
        "https://aula.test/pluginfile.php/1/assignsubmission_file/"
        "submission_files/2/entrega.txt"
    )
    html_entregas = f"""
    <table id="submissions"><tbody>
      <tr class="user42">
        <td class="fullname"><a href="/user/view.php?id=42">Ana García</a></td>
        <td><a href="{url_archivo}">entrega.txt</a></td>
        <td class="grade">9</td>
      </tr>
      <tr class="user43">
        <td class="fullname"><a href="/user/view.php?id=43">Luis Pérez</a></td>
        <td class="grade">-</td>
      </tr>
    </tbody></table>
    """

    class Respuesta:
        def __init__(self, url: str, text: str = "", content: bytes = b"") -> None:
            self.url = url
            self.text = text
            self.content = content

    class ClientePrueba:
        def obtener_paginas_entregas_tarea(
            self,
            actividad_id: int,
        ) -> tuple[tuple[str, str], ...]:
            return ((html_entregas, actividad.url + "&action=grading"),)

        def obtener(self, url: str) -> Respuesta:
            if "action=grade" in url:
                return Respuesta(
                    url,
                    '<div class="gradingform_rubric">Rúbrica y comentarios</div>',
                )
            return Respuesta(url, content=b"contenido entregado")

    trabajo = GuardarCuestionarios(
        ClientePrueba(),  # type: ignore[arg-type]
        (actividad,),
        tmp_path,
    )
    progresos: list[tuple[int, int, str]] = []
    trabajo.senales.entrega_guardada.connect(
        lambda actual, total, alumno: progresos.append(
            (actual, total, alumno)
        )
    )

    trabajo.run()

    assert progresos == [
        (1, 2, "Ana García"),
        (2, 2, "Luis Pérez"),
    ]
    carpeta_ana = tmp_path / "Ana García [usuario-42]" / "Práctica UT2"
    carpeta_luis = tmp_path / "Luis Pérez [usuario-43]" / "Práctica UT2"
    assert (carpeta_ana / "archivos" / "entrega.txt").read_bytes() == (
        b"contenido entregado"
    )
    assert "Rúbrica" in (carpeta_ana / "calificacion.html").read_text()
    assert "Rúbrica" in (carpeta_luis / "calificacion.html").read_text()
