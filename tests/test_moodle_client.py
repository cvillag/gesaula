"""Pruebas del cliente Moodle."""

from types import SimpleNamespace
from urllib.parse import parse_qs

from gesaula.moodle.client import ClienteMoodle


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
