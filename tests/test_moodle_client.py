"""Pruebas del cliente Moodle."""

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
