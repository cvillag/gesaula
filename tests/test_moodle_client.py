"""Pruebas del cliente Moodle."""

from types import SimpleNamespace
from urllib.parse import parse_qs

import pytest

from gesaula.moodle.client import ClienteMoodle
from gesaula.moodle.errors import ErrorConexionMoodle, SesionMoodleExpirada


def _fila_level_up(alumno_id: int, puntos: int) -> str:
    return f"""
    <tr>
      <td class="c1"><a href="/user/view.php?id={alumno_id}">Alumno {alumno_id}</a></td>
      <td class="c2">1</td><td class="c3"><span class="pts">{puntos}</span></td>
      <td><a data-xp-action="open-form" data-form-args__contextid="123">Editar</a></td>
    </tr>
    """


def test_level_up_recorre_paginas_sin_repetir_alumnos_ni_peticiones() -> None:
    cliente = ClienteMoodle("https://aula.test/")
    url = "https://aula.test/blocks/xp/index.php/report/1203"
    paginas = {}
    for numero, filas in enumerate((
        _fila_level_up(42, 100),
        _fila_level_up(42, 100) + _fila_level_up(43, 50),
        _fila_level_up(44, 0),
    )):
        actual = url if numero == 0 else f"{url}?page={numero}"
        siguiente = f'<a href="?page={numero + 1}">Siguiente</a>' if numero < 2 else ""
        paginas[actual] = SimpleNamespace(
            url=actual,
            text=(
                f'<table class="block_xp-report-table"><tbody>{filas}</tbody></table>'
                f'<nav class="pagination"><a href="{url}">Primera</a>'
                f'{siguiente}{siguiente}<a href="#">Actual</a></nav>'
            ),
        )
    llamadas = []

    def obtener(pagina: str) -> SimpleNamespace:
        llamadas.append(pagina)
        assert len(llamadas) <= 3
        return paginas[pagina]

    cliente.obtener = obtener
    try:
        alumnos = cliente.obtener_alumnos_level_up(url)
        assert [(alumno.id, alumno.px) for alumno in alumnos] == [(42, 100), (43, 50), (44, 0)]
        assert llamadas == [url, f"{url}?page=1", f"{url}?page=2"]
    finally:
        cliente.cerrar()


@pytest.mark.parametrize("error", [ErrorConexionMoodle, SesionMoodleExpirada])
def test_level_up_no_devuelve_informe_parcial_si_falla_otra_pagina(error) -> None:
    cliente = ClienteMoodle("https://aula.test/")
    url = "https://aula.test/blocks/xp/index.php/report/1203"

    def obtener(pagina: str) -> SimpleNamespace:
        if pagina != url:
            raise error("Fallo en la segunda página")
        return SimpleNamespace(
            url=url,
            text=(
                '<table class="block_xp-report-table"><tbody>'
                f'{_fila_level_up(42, 100)}</tbody></table>'
                '<nav class="pagination"><a href="?page=1">2</a></nav>'
            ),
        )

    cliente.obtener = obtener
    try:
        with pytest.raises(error, match="segunda página"):
            cliente.obtener_alumnos_level_up(url)
    finally:
        cliente.cerrar()


class RespuestaAjax:
    """Respuesta mínima para inspeccionar una llamada AJAX."""

    def json(self) -> object:
        return [{"error": False, "data": {"submitted": True, "data": "{}"}}]


def test_actualiza_px_sin_cargar_el_formulario_dinamico() -> None:
    cliente = ClienteMoodle("https://aula.test/centro/")
    cliente._autenticado = True
    cliente._sesskey = "clave123"
    solicitud: dict[str, object] = {}

    def enviar_json(url: str, datos: object) -> RespuestaAjax:
        solicitud["url"] = url
        solicitud["datos"] = datos
        return RespuestaAjax()

    cliente._post_json = enviar_json  # type: ignore[method-assign]

    cliente.actualizar_px_level_up(
        alumno_id=5257,
        context_id=85744,
        nuevo_total=80,
    )

    assert solicitud["url"] == (
        "https://aula.test/centro/lib/ajax/service.php"
        "?sesskey=clave123&info=core_form_dynamic_form"
    )
    mensajes = solicitud["datos"]
    assert isinstance(mensajes, list)
    mensaje = mensajes[0]
    assert mensaje["methodname"] == "core_form_dynamic_form"
    assert mensaje["args"]["form"] == r"block_xp\form\user_xp"
    formulario = parse_qs(mensaje["args"]["formdata"])
    assert formulario == {
        "contextid": ["85744"],
        "userid": ["5257"],
        "sesskey": ["clave123"],
        "_qf__block_xp_form_user_xp": ["1"],
        "xp": ["80"],
    }
    cliente.cerrar()


def test_obtiene_intentos_de_todas_las_paginas_del_informe() -> None:
    cliente = ClienteMoodle("https://aula.test/")
    paginas = {
        "mod/quiz/report.php?id=10&mode=overview&pagesize=5000": SimpleNamespace(
            url="https://aula.test/mod/quiz/report.php?id=10&mode=overview",
            text="""
              <table><tr>
                <td class="fullname"><a href="/user/view.php?id=42">Ana</a></td>
                <td><a href="/mod/quiz/review.php?attempt=100">Revisar</a></td>
              </tr></table>
              <nav class="pagination">
                <a href="/mod/quiz/report.php?id=10&amp;mode=overview&amp;page=1">2</a>
              </nav>
            """,
        ),
        "https://aula.test/mod/quiz/report.php?id=10&mode=overview&page=1": (
            SimpleNamespace(
                url=(
                    "https://aula.test/mod/quiz/report.php"
                    "?id=10&mode=overview&page=1"
                ),
                text="""
                  <table><tr>
                    <td class="fullname">
                      <a href="/user/view.php?id=43">Luis</a>
                    </td>
                    <td>
                      <a href="/mod/quiz/review.php?attempt=101">Revisar</a>
                    </td>
                  </tr></table>
                """,
            )
        ),
    }
    cliente.obtener = lambda url: paginas[url]  # type: ignore[method-assign]

    intentos = cliente.obtener_intentos_cuestionario(10)

    assert [intento.id for intento in intentos] == [100, 101]
    assert [intento.alumno for intento in intentos] == ["Ana", "Luis"]
    cliente.cerrar()


def test_obtiene_todas_las_paginas_de_entregas() -> None:
    cliente = ClienteMoodle("https://aula.test/")
    paginas = {
        "mod/assign/view.php?id=15&action=grading&perpage=100": SimpleNamespace(
            url="https://aula.test/mod/assign/view.php?id=15&action=grading",
            text="""
              <table id="submissions"></table>
              <nav class="pagination">
                <a href="/mod/assign/view.php?id=15&amp;action=grading&amp;page=1">2</a>
              </nav>
            """,
        ),
        "https://aula.test/mod/assign/view.php?id=15&action=grading&page=1": (
            SimpleNamespace(
                url=(
                    "https://aula.test/mod/assign/view.php"
                    "?id=15&action=grading&page=1"
                ),
                text='<table id="submissions"></table>',
            )
        ),
    }
    cliente.obtener = lambda url: paginas[url]  # type: ignore[method-assign]

    resultado = cliente.obtener_paginas_entregas_tarea(15)

    assert len(resultado) == 2
    assert resultado[1][1].endswith("action=grading&page=1")
    cliente.cerrar()
