"""Parsers de páginas HTML de Moodle."""

import json
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from gesaula.moodle.models import CursoMoodle, FormularioLogin

MENSAJE_MANTENIMIENTO = (
    "Este sitio está en fase de mantenimiento y no está disponible en este momento"
)
PATRON_IMAGEN_FONDO = re.compile(
    r"""background-image\s*:\s*url\(\s*(['"]?)(.*?)\1\s*\)""",
    re.IGNORECASE,
)
PATRON_CONFIGURACION_MOODLE = re.compile(r"M\.cfg\s*=\s*(\{.*?\})\s*;", re.DOTALL)
PATRON_INFORME_LEVEL_UP = re.compile(
    r"/blocks/xp/index\.php/report/(?P<curso_id>\d+)/?$",
    re.IGNORECASE,
)


def esta_en_mantenimiento(html: str) -> bool:
    """Indica si el HTML contiene el aviso de mantenimiento de Moodle."""
    texto = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    texto_normalizado = " ".join(texto.split()).casefold()
    return MENSAJE_MANTENIMIENTO.casefold() in texto_normalizado


def extraer_formulario_login(html: str, url_pagina: str) -> FormularioLogin | None:
    """Extrae la acción y los campos ocultos del formulario de acceso."""
    soup = BeautifulSoup(html, "html.parser")
    formulario = next(
        (
            candidato
            for candidato in soup.find_all("form")
            if candidato.find("input", attrs={"name": "username"})
            and candidato.find("input", attrs={"name": "password"})
        ),
        None,
    )
    if formulario is None:
        return None

    campos_ocultos = {
        str(campo["name"]): str(campo.get("value", ""))
        for campo in formulario.find_all("input", attrs={"type": "hidden", "name": True})
    }
    action = urljoin(url_pagina, str(formulario.get("action") or url_pagina))
    return FormularioLogin(action=action, campos_ocultos=campos_ocultos)


def contiene_formulario_login(html: str) -> bool:
    """Indica si sigue presente un formulario de usuario y contraseña."""
    return extraer_formulario_login(html, "") is not None


def contiene_identidad_usuario(html: str) -> bool:
    """Busca controles que Moodle muestra habitualmente al usuario autenticado."""
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one(
        '#user-menu-toggle, [data-region="user-menu"], .usermenu, .userbutton'
    ):
        return True
    return soup.find("a", href=lambda href: href and "/login/logout.php" in href) is not None


def contiene_error_credenciales(html: str) -> bool:
    """Busca mensajes de error dentro del formulario de acceso."""
    soup = BeautifulSoup(html, "html.parser")
    return (
        soup.select_one(
            "#loginerrormessage, .loginerrors, .loginerror, "
            '[data-region="login-form"] .alert-danger, .loginform .alert-danger'
        )
        is not None
    )


def contiene_error_sesion(texto: str) -> bool:
    """Detecta códigos de Moodle que requieren una sesión válida."""
    texto_normalizado = texto.casefold()
    return any(
        codigo in texto_normalizado
        for codigo in (
            '"errorcode":"requireloginerror"',
            '"errorcode": "requireloginerror"',
            '"errorcode":"servicerequireslogin"',
            '"errorcode": "servicerequireslogin"',
        )
    )


def extraer_sesskey(html: str) -> str | None:
    """Extrae la clave de sesión que Moodle publica en ``M.cfg``."""
    coincidencia = PATRON_CONFIGURACION_MOODLE.search(html)
    if coincidencia is not None:
        try:
            configuracion = json.loads(coincidencia.group(1))
        except json.JSONDecodeError:
            pass
        else:
            sesskey = configuracion.get("sesskey")
            if isinstance(sesskey, str) and sesskey:
                return sesskey

    # Algunos temas no imprimen M.cfg, pero sí incluyen la clave en logout.
    soup = BeautifulSoup(html, "html.parser")
    enlace_logout = soup.find(
        "a", href=lambda href: href and "/login/logout.php" in href
    )
    if enlace_logout is None:
        return None
    valores = parse_qs(urlparse(str(enlace_logout.get("href", ""))).query)
    sesskey = valores.get("sesskey", [None])[0]
    return sesskey if isinstance(sesskey, str) and sesskey else None


def extraer_usuario_id(html: str) -> int | None:
    """Extrae el identificador del usuario autenticado publicado en ``M.cfg``."""
    coincidencia = PATRON_CONFIGURACION_MOODLE.search(html)
    if coincidencia is None:
        return None
    try:
        configuracion = json.loads(coincidencia.group(1))
    except json.JSONDecodeError:
        return None
    usuario_id = configuracion.get("userId")
    return usuario_id if isinstance(usuario_id, int) and usuario_id > 0 else None


def tiene_rol_profesor(html: str) -> bool:
    """Comprueba que el perfil del curso muestre exactamente el rol Profesor."""
    soup = BeautifulSoup(html, "html.parser")
    etiquetas = soup.select("dt, th, .label")
    for etiqueta in etiquetas:
        titulo = " ".join(etiqueta.get_text(" ", strip=True).split()).casefold()
        if titulo.rstrip(":") not in {"rol", "roles", "roles de curso"}:
            continue

        valor = etiqueta.find_next_sibling(["dd", "td", "div"])
        if valor is None and etiqueta.parent is not None:
            valor = etiqueta.parent.find_next_sibling()
        if isinstance(valor, Tag) and any(
            " ".join(texto.split()).casefold() == "profesor"
            for texto in valor.stripped_strings
        ):
            return True
    return False


def extraer_url_level_up(
    html: str, url_pagina: str, curso_id: int
) -> str | None:
    """Devuelve el informe de Level up cuando el bloque está en el curso.

    Se identifica el enlace propio del bloque en vez de buscar su título, ya
    que Moodle puede mostrarlo como ``Level up`` o ``Sube de nivel``.
    """
    soup = BeautifulSoup(html, "html.parser")
    for enlace in soup.find_all("a", href=True):
        url = urljoin(url_pagina, str(enlace["href"]))
        coincidencia = PATRON_INFORME_LEVEL_UP.search(urlparse(url).path)
        if coincidencia is None:
            continue
        if int(coincidencia.group("curso_id")) == curso_id:
            return url
    return None


def extraer_cursos_ajax(datos: object, url_base: str) -> tuple[CursoMoodle, ...]:
    """Convierte la respuesta estructurada del servicio AJAX de Moodle."""
    if not isinstance(datos, dict) or not isinstance(datos.get("courses"), list):
        return ()

    cursos: list[CursoMoodle] = []
    for curso in datos["courses"]:
        if not isinstance(curso, dict):
            continue
        curso_id = curso.get("id")
        nombre = curso.get("fullname") or curso.get("shortname")
        if not isinstance(curso_id, int) or not isinstance(nombre, str) or not nombre:
            continue

        viewurl = curso.get("viewurl")
        url = (
            viewurl
            if isinstance(viewurl, str) and viewurl
            else urljoin(url_base, f"course/view.php?id={curso_id}")
        )
        courseimage = curso.get("courseimage")
        imagen_url = courseimage if isinstance(courseimage, str) and courseimage else None
        cursos.append(
            CursoMoodle(
                id=curso_id,
                nombre=" ".join(nombre.split()),
                url=url,
                imagen_url=imagen_url,
            )
        )
    return tuple(cursos)


def extraer_cursos(html: str, url_pagina: str) -> tuple[CursoMoodle, ...]:
    """Extrae cursos únicos desde los enlaces de la página Mis cursos."""
    soup = BeautifulSoup(html, "html.parser")
    cursos: dict[int, CursoMoodle] = {}

    for enlace in soup.find_all("a", href=True):
        url = urljoin(url_pagina, str(enlace["href"]))
        partes = urlparse(url)
        if not partes.path.rstrip("/").endswith("/course/view.php"):
            continue

        valores_id = parse_qs(partes.query).get("id", [])
        if not valores_id or not valores_id[0].isdigit():
            continue

        curso_id = int(valores_id[0])
        nombre = _extraer_nombre_curso(enlace)
        if not nombre:
            continue

        imagen_url = _extraer_imagen_curso(enlace, url_pagina)
        curso_anterior = cursos.get(curso_id)

        # Moodle incluye enlaces a los cursos en la navegación antes que las
        # tarjetas. Conservamos la tarjeta posterior porque aporta el nombre
        # completo y la imagen, incluida la imagen predeterminada de Moodle.
        if curso_anterior is None or imagen_url is not None:
            cursos[curso_id] = CursoMoodle(
                id=curso_id,
                nombre=nombre,
                url=url,
                imagen_url=imagen_url,
            )

    # El diccionario conserva la posición de la primera aparición, que suele
    # estar en la navegación lateral. Reconstruimos el resultado con el orden
    # de las tarjetas para que coincida con el mosaico mostrado por Moodle.
    ids_tarjetas = [
        int(str(tarjeta["data-course-id"]))
        for tarjeta in soup.select("[data-region='course-content'][data-course-id]")
        if str(tarjeta["data-course-id"]).isdigit()
        and int(str(tarjeta["data-course-id"])) in cursos
    ]
    ids_ordenados = list(dict.fromkeys([*ids_tarjetas, *cursos]))
    return tuple(cursos[curso_id] for curso_id in ids_ordenados)

def _extraer_nombre_curso(enlace: Tag) -> str:
    """Obtiene el nombre visible sin los textos auxiliares para lectores de pantalla."""
    titulo = enlace.select_one(".multiline[title]")
    if titulo is not None:
        return " ".join(str(titulo["title"]).split())

    return " ".join(enlace.get_text(" ", strip=True).split())


def _extraer_imagen_curso(enlace: Tag, url_pagina: str) -> str | None:
    """Busca una imagen en la tarjeta que contiene el enlace del curso."""
    clases_tarjeta = {
        "card",
        "dashboard-card",
        "coursebox",
        "course-card",
        "course-summaryitem",
        "course-listitem",
    }
    tarjeta = next(
        (
            elemento
            for elemento in (enlace, *enlace.parents)
            if isinstance(elemento, Tag) and _clases(elemento) & clases_tarjeta
        ),
        None,
    )
    if tarjeta is None:
        # Un enlace de la navegación no es una tarjeta. No ascendemos hasta
        # contenedores genéricos porque capturaríamos iconos ajenos como el foro.
        return None

    for elemento in (tarjeta, *tarjeta.find_all(style=True)):
        url_imagen = _extraer_url_imagen_fondo(str(elemento.get("style", "")))
        if url_imagen is not None:
            return urljoin(url_pagina, url_imagen)

    imagen = tarjeta.find("img", src=True)
    if imagen is not None:
        return urljoin(url_pagina, str(imagen["src"]))
    return None


def _clases(elemento: Tag) -> set[str]:
    clases = elemento.get("class", [])
    if isinstance(clases, str):
        clases = clases.split()
    return {str(clase) for clase in clases}


def _extraer_url_imagen_fondo(style: str) -> str | None:
    """Extrae la URL definida en una propiedad CSS background-image."""
    coincidencia = PATRON_IMAGEN_FONDO.search(style)
    if coincidencia is None:
        return None

    url_imagen = coincidencia.group(2).strip()
    if not url_imagen or url_imagen.casefold() == "none":
        return None
    return url_imagen
