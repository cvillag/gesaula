"""Pruebas del archivo local de tareas."""

from gesaula.actions.guardar_cuestionarios import preparar_carpetas_cuestionario
from gesaula.actions.guardar_tareas import (
    guardar_entrega_tarea,
    preparar_carpetas_tarea,
)
from gesaula.moodle.models import (
    ActividadDescargable,
    AdjuntoRevision,
    EntregaTarea,
    IntentoCuestionario,
)


def test_guarda_tarea_aunque_no_haya_texto_ni_archivos(tmp_path) -> None:
    actividad = ActividadDescargable(
        15,
        "Práctica UT2",
        "Tarea",
        "https://aula.test/mod/assign/view.php?id=15",
    )
    entrega = EntregaTarea(
        42,
        "Ana García López",
        '<tr class="user42"><td class="grade">Sin calificar</td></tr>',
        "https://aula.test/mod/assign/view.php?id=15&action=grade&userid=42",
        (),
        None,
        True,
    )

    carpetas = preparar_carpetas_tarea(tmp_path, actividad, (entrega,))
    carpeta = guardar_entrega_tarea(
        tmp_path,
        actividad,
        entrega,
        None,
        ("<html><body>Comentario y rúbrica</body></html>", entrega.url_calificacion),
        (),
    )

    assert carpetas == (carpeta,)
    assert (carpeta / "entrega.html").is_file()
    assert "Sin calificar" in (carpeta / "entrega.html").read_text()
    assert "Comentario y rúbrica" in (carpeta / "calificacion.html").read_text()
    assert not (carpeta / "texto-entrega.html").exists()


def test_descarga_archivo_y_reescribe_enlace_de_entrega(tmp_path) -> None:
    actividad = ActividadDescargable(15, "Tarea", "Tarea", "https://a/assign")
    archivo = AdjuntoRevision(
        "https://a/pluginfile.php/1/assignsubmission_file/submission_files/2/a.txt",
        "a.txt",
    )
    entrega = EntregaTarea(
        42,
        "Ana",
        f'<tr><td><a href="{archivo.url}">a.txt</a></td></tr>',
        "https://a/mod/assign/view.php?id=15&action=grade&userid=42",
        (archivo,),
        None,
        False,
    )

    carpeta = guardar_entrega_tarea(
        tmp_path,
        actividad,
        entrega,
        None,
        None,
        ((archivo, b"datos"),),
    )

    assert (carpeta / "archivos" / "a.txt").read_bytes() == b"datos"
    assert 'href="archivos/a.txt"' in (carpeta / "entrega.html").read_text()


def test_tarea_reutiliza_carpeta_creada_por_cuestionario(tmp_path) -> None:
    cuestionario = ActividadDescargable(10, "Examen", "Cuestionario", "https://a/q")
    intento = IntentoCuestionario(
        100,
        42,
        "Ana García",
        "https://a/review?attempt=100",
    )
    tarea = ActividadDescargable(15, "Práctica", "Tarea", "https://a/t")
    entrega = EntregaTarea(
        42,
        "Ana María García López",
        "<tr></tr>",
        "https://a/grade",
        (),
        None,
        True,
    )

    preparar_carpetas_cuestionario(tmp_path, cuestionario, (intento,))
    (carpeta_tarea,) = preparar_carpetas_tarea(tmp_path, tarea, (entrega,))

    assert carpeta_tarea == (
        tmp_path / "Ana García [usuario-42]" / "Práctica"
    )
