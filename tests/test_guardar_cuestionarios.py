"""Pruebas del almacenamiento local de revisiones de cuestionarios."""

from pathlib import Path

from gesaula.actions.guardar_cuestionarios import (
    CuestionarioConIntentos,
    crear_inventario_cuestionarios,
    guardar_revision_cuestionario,
    preparar_carpetas_cuestionario,
)
from gesaula.moodle.models import (
    ActividadDescargable,
    AdjuntoRevision,
    IntentoCuestionario,
)


def test_inventario_cuenta_alumnos_unicos_e_intentos_repetidos() -> None:
    actividad = ActividadDescargable(
        10,
        "Control",
        "Cuestionario",
        "https://aula.test/mod/quiz/view.php?id=10",
    )
    cuestionarios = (
        CuestionarioConIntentos(
            actividad,
            (
                IntentoCuestionario(100, 42, "Ana Ejemplo", "https://a/review?attempt=100"),
                IntentoCuestionario(101, 42, "Ana Ejemplo", "https://a/review?attempt=101"),
                IntentoCuestionario(102, 43, "Luis Prueba", "https://a/review?attempt=102"),
            ),
        ),
        CuestionarioConIntentos(
            actividad,
            (IntentoCuestionario(103, 42, "Ana Ejemplo", "https://a/review?attempt=103"),),
        ),
    )

    inventario = crear_inventario_cuestionarios(cuestionarios)

    assert inventario.total_alumnos == 2
    assert inventario.total_intentos == 4


def test_guarda_html_adjuntos_y_reescribe_sus_enlaces(tmp_path: Path) -> None:
    actividad = ActividadDescargable(
        10,
        "Control: UT/1",
        "Cuestionario",
        "https://aula.test/mod/quiz/view.php?id=10",
    )
    intento = IntentoCuestionario(
        52049,
        42,
        "Ana / Ejemplo",
        "https://aula.test/mod/quiz/review.php?attempt=52049",
    )
    adjunto_uno = AdjuntoRevision(
        "https://aula.test/pluginfile.php/1/question/response_attachments/2/1/datos.txt",
        "datos.txt",
    )
    adjunto_dos = AdjuntoRevision(
        "https://aula.test/pluginfile.php/1/question/response_attachments/3/1/datos.txt",
        "datos.txt",
    )
    html = f"""
    <html><body>
      <a href="{adjunto_uno.url}">Primero</a>
      <a href="{adjunto_dos.url}">Segundo</a>
    </body></html>
    """

    ruta_html = guardar_revision_cuestionario(
        tmp_path,
        actividad,
        intento,
        html,
        (
            (adjunto_uno, b"uno"),
            (adjunto_dos, b"dos"),
        ),
    )

    assert ruta_html.relative_to(tmp_path).parts == (
        "Ana _ Ejemplo [usuario-42]",
        "Control_ UT_1",
        "intento-52049",
        "revision.html",
    )
    carpeta_adjuntos = ruta_html.parent / "archivos"
    assert (carpeta_adjuntos / "datos.txt").read_bytes() == b"uno"
    assert (carpeta_adjuntos / "datos-2.txt").read_bytes() == b"dos"
    html_guardado = ruta_html.read_text(encoding="utf-8")
    assert 'href="archivos/datos.txt"' in html_guardado
    assert 'href="archivos/datos-2.txt"' in html_guardado


def test_prepara_carpetas_antes_de_descargar_revisiones(tmp_path: Path) -> None:
    actividad = ActividadDescargable(
        10,
        "Control",
        "Cuestionario",
        "https://aula.test/mod/quiz/view.php?id=10",
    )
    intentos = (
        IntentoCuestionario(100, 42, "Ana", "https://a/review?attempt=100"),
        IntentoCuestionario(101, 42, "Ana", "https://a/review?attempt=101"),
    )

    carpetas = preparar_carpetas_cuestionario(
        tmp_path,
        actividad,
        intentos,
    )

    assert carpetas == (tmp_path / "Ana [usuario-42]" / "Control",)
    assert carpetas[0].is_dir()
