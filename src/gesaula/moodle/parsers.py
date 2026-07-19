"""Parsers de páginas HTML de Moodle."""

import json
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag

from gesaula.moodle.models import (
    ActividadDescargable,
    AdjuntoRevision,
    AlumnoLevelUp,
    CursoMoodle,
    EntregaTarea,
    FormularioLogin,
    IntentoCuestionario,
)

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
TIPOS_ACTIVIDAD_DESCARGABLE = {
    "quiz": "Cuestionario",
    "workshop": "Taller",
    "data": "Base de datos",
    "geogebra": "GeoGebra",
    "glossary": "Glosario",
    "assign": "Tarea",
}
PATRON_ACTIVIDAD_DESCARGABLE = re.compile(
    r"/mod/(?P<modulo>quiz|workshop|data|geogebra|glossary|assign)/view\.php$",
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


def extraer_alumnos_level_up(html: str) -> tuple[AlumnoLevelUp, ...]:
    """Extrae los alumnos del informe sin depender de identificadores YUI."""
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.select_one("table.block_xp-report-table")
    if tabla is None:
        return ()

    alumnos: list[AlumnoLevelUp] = []
    for fila in tabla.select("tbody tr"):
        celda_nombre = fila.select_one("td.c1")
        celda_nivel = fila.select_one("td.c2")
        celda_px = fila.select_one("td.c3")
        if celda_nombre is None or celda_nivel is None or celda_px is None:
            continue

        nombre = " ".join(celda_nombre.get_text(" ", strip=True).split())
        nivel = _extraer_entero(celda_nivel.get_text(" ", strip=True))
        puntos = celda_px.select_one(".pts")
        px = _extraer_entero(
            (puntos or celda_px).get_text(" ", strip=True)
        )
        enlace_usuario = celda_nombre.find("a", href=True)
        if not nombre or nivel is None or px is None or enlace_usuario is None:
            # Moodle incluye una fila vacía que JavaScript utiliza como plantilla.
            continue
        valores_id = parse_qs(urlparse(str(enlace_usuario["href"])).query).get(
            "id", []
        )
        if not valores_id or not valores_id[0].isdigit():
            continue

        enlace_editar = fila.select_one(
            '[data-xp-action="open-form"][data-form-args__contextid]'
        )
        context_id_texto = (
            str(enlace_editar.get("data-form-args__contextid", ""))
            if enlace_editar is not None
            else ""
        )
        alumnos.append(
            AlumnoLevelUp(
                id=int(valores_id[0]),
                nombre=nombre,
                nivel=nivel,
                px=px,
                context_id=(
                    int(context_id_texto) if context_id_texto.isdigit() else None
                ),
            )
        )
    return tuple(alumnos)


def extraer_actividades_descargables(
    html: str,
    url_pagina: str,
) -> tuple[ActividadDescargable, ...]:
    """Extrae actividades almacenables sin depender del tema de Moodle."""
    soup = BeautifulSoup(html, "html.parser")
    actividades: dict[int, ActividadDescargable] = {}
    for enlace in soup.find_all("a", href=True):
        url = urljoin(url_pagina, str(enlace["href"]))
        partes = urlparse(url)
        coincidencia = PATRON_ACTIVIDAD_DESCARGABLE.search(partes.path)
        if coincidencia is None:
            continue
        valores_id = parse_qs(partes.query).get("id", [])
        if not valores_id or not valores_id[0].isdigit():
            continue
        actividad_id = int(valores_id[0])
        if actividad_id in actividades:
            continue

        nombre = _extraer_texto_visible(enlace)
        if not nombre:
            nombre = " ".join(
                str(enlace.get("title") or enlace.get("aria-label") or "").split()
            )
        if not nombre:
            continue
        modulo = coincidencia.group("modulo").casefold()
        actividades[actividad_id] = ActividadDescargable(
            id=actividad_id,
            nombre=nombre,
            tipo=TIPOS_ACTIVIDAD_DESCARGABLE[modulo],
            url=url,
        )
    return tuple(actividades.values())


def extraer_intentos_cuestionario(
    html: str,
    url_pagina: str,
) -> tuple[IntentoCuestionario, ...]:
    """Extrae intentos revisables del informe general del cuestionario."""
    soup = BeautifulSoup(html, "html.parser")
    intentos: dict[int, IntentoCuestionario] = {}
    for enlace_revision in soup.find_all(
        "a",
        href=lambda href: href and "/mod/quiz/review.php" in href,
    ):
        url_revision = urljoin(url_pagina, str(enlace_revision["href"]))
        valores_intento = parse_qs(urlparse(url_revision).query).get("attempt", [])
        if not valores_intento or not valores_intento[0].isdigit():
            continue
        intento_id = int(valores_intento[0])
        if intento_id in intentos:
            continue

        fila = enlace_revision.find_parent("tr")
        if fila is None:
            continue
        enlaces_usuario = fila.find_all(
            "a",
            href=lambda href: href
            and (
                "/user/view.php" in href
                or "/user/profile.php" in href
            ),
        )
        alumno_id: int | None = None
        for enlace_usuario in enlaces_usuario:
            valores_usuario = parse_qs(
                urlparse(str(enlace_usuario.get("href", ""))).query
            ).get("id", [])
            if valores_usuario and valores_usuario[0].isdigit():
                alumno_id = int(valores_usuario[0])
                break
        alumno = _extraer_nombre_completo_alumno(fila, enlaces_usuario)
        if not alumno:
            continue
        intentos[intento_id] = IntentoCuestionario(
            id=intento_id,
            alumno_id=alumno_id,
            alumno=alumno,
            url_revision=url_revision,
        )
    return tuple(intentos.values())


def _extraer_nombre_completo_alumno(
    fila: Tag,
    enlaces_usuario: list[Tag],
) -> str:
    """Prioriza el nombre completo frente al avatar o textos abreviados."""
    celda_nombre = fila.select_one(
        "td.fullname, td[data-field='fullname'], td.userfullname"
    )
    if celda_nombre is not None:
        candidatos_celda = [
            _extraer_texto_visible(enlace)
            for enlace in celda_nombre.find_all("a")
        ]
        candidatos_celda = [
            candidato for candidato in candidatos_celda if candidato
        ]
        if candidatos_celda:
            return max(candidatos_celda, key=lambda texto: (len(texto.split()), len(texto)))

        texto_celda = _extraer_texto_elemento_visible(celda_nombre)
        if texto_celda:
            return texto_celda

    nombre = fila.select_one("td.firstname, td[data-field='firstname']")
    apellidos = fila.select_one("td.lastname, td[data-field='lastname']")
    partes = [
        texto
        for elemento in (nombre, apellidos)
        if elemento is not None
        and (texto := _extraer_texto_elemento_visible(elemento))
    ]
    if partes:
        return " ".join(partes)

    candidatos = [
        _extraer_texto_visible(enlace)
        for enlace in enlaces_usuario
    ]
    candidatos = [candidato for candidato in candidatos if candidato]
    return (
        max(candidatos, key=lambda texto: (len(texto.split()), len(texto)))
        if candidatos
        else ""
    )


def extraer_numero_intentos_cuestionario(html: str) -> int:
    """Obtiene el contador de intentos mostrado en la portada del cuestionario."""
    soup = BeautifulSoup(html, "html.parser")
    contador = soup.select_one(".quizattemptcounts")
    if contador is None:
        # Moodle omite este bloque cuando todavía no hay ningún intento.
        return 0

    enlace_informe = contador.find(
        "a",
        href=lambda href: href
        and "/mod/quiz/report.php" in href
        and "mode=overview" in href,
    )
    texto = (enlace_informe or contador).get_text(" ", strip=True)
    numero = _extraer_entero(texto)
    return numero if numero is not None else 0


def extraer_paginas_informe_cuestionario(
    html: str,
    url_pagina: str,
) -> tuple[str, ...]:
    """Extrae las páginas adicionales del informe de intentos."""
    soup = BeautifulSoup(html, "html.parser")
    paginas: dict[str, None] = {}
    for enlace in soup.select(
        ".paging a[href], .pagination a[href], [data-region='paging'] a[href]"
    ):
        url = urljoin(url_pagina, str(enlace["href"]))
        partes = urlparse(url)
        if (
            "/mod/quiz/report.php" not in partes.path
            or "page" not in parse_qs(partes.query)
        ):
            continue
        paginas.setdefault(url, None)
    return tuple(paginas)


def extraer_entregas_tarea(
    html: str,
    url_pagina: str,
    actividad_id: int,
) -> tuple[EntregaTarea, ...]:
    """Extrae alumnos y datos visibles de la pestaña Entregas."""
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.select_one("table#submissions")
    if tabla is None:
        return ()

    entregas: dict[int, EntregaTarea] = {}
    for fila in tabla.select("tbody tr"):
        alumno_id = _extraer_usuario_id_fila_entrega(fila)
        if alumno_id is None:
            continue
        enlaces_usuario = fila.find_all(
            "a",
            href=lambda href: href
            and ("/user/view.php" in href or "/user/profile.php" in href),
        )
        alumno = _extraer_nombre_completo_alumno(fila, enlaces_usuario)
        if not alumno:
            identificador = fila.select_one(".recordid")
            alumno = (
                _extraer_texto_elemento_visible(identificador)
                if identificador is not None
                else f"Alumno {alumno_id}"
            )

        archivos = extraer_archivos_tarea(fila, url_pagina)
        enlace_texto = fila.find(
            "a",
            href=lambda href: href
            and "action=viewpluginassignsubmission" in href
            and "plugin=onlinetext" in href,
        )
        url_texto = (
            urljoin(url_pagina, str(enlace_texto["href"]))
            if enlace_texto is not None
            else None
        )
        celda_nota = fila.select_one("td.grade, td[data-field='grade']")
        nota = (
            _extraer_texto_elemento_visible(celda_nota)
            if celda_nota is not None
            else ""
        )
        tiene_nota = bool(nota and nota not in {"-", "Sin calificar"})
        calificacion_avanzada = fila.select_one(
            ".gradingform_rubric, .advancedgrading, [data-gradingmethod]"
        ) is not None
        url_calificacion = urljoin(
            url_pagina,
            "view.php?"
            f"id={actividad_id}&action=grade&userid={alumno_id}",
        )
        entregas[alumno_id] = EntregaTarea(
            alumno_id=alumno_id,
            alumno=alumno,
            html_resumen=str(fila),
            url_calificacion=url_calificacion,
            archivos=archivos,
            url_texto_completo=url_texto,
            requiere_calificacion=(
                calificacion_avanzada or not (archivos and tiene_nota)
            ),
        )
    return tuple(entregas.values())


def extraer_paginas_entregas_tarea(
    html: str,
    url_pagina: str,
) -> tuple[str, ...]:
    """Extrae páginas adicionales de la tabla de entregas."""
    soup = BeautifulSoup(html, "html.parser")
    paginas: dict[str, None] = {}
    for enlace in soup.select(
        ".paging a[href], .pagination a[href], [data-region='paging'] a[href]"
    ):
        url = urljoin(url_pagina, str(enlace["href"]))
        partes = urlparse(url)
        parametros = parse_qs(partes.query)
        if (
            "/mod/assign/view.php" not in partes.path
            or parametros.get("action", [""])[0] != "grading"
            or "page" not in parametros
        ):
            continue
        paginas.setdefault(url, None)
    return tuple(paginas)


def extraer_archivos_tarea(
    html_o_elemento: str | Tag,
    url_pagina: str,
) -> tuple[AdjuntoRevision, ...]:
    """Localiza ficheros de entrega y retroalimentación de una tarea."""
    soup = (
        BeautifulSoup(html_o_elemento, "html.parser")
        if isinstance(html_o_elemento, str)
        else html_o_elemento
    )
    archivos: dict[str, AdjuntoRevision] = {}
    areas = (
        "/assignsubmission_file/submission_files/",
        "/assignsubmission_onlinetext/onlinetext/",
        "/assignfeedback_file/feedback_files/",
    )
    for elemento in soup.select("[href], [src]"):
        atributo = "href" if elemento.has_attr("href") else "src"
        url = urljoin(url_pagina, str(elemento.get(atributo, "")))
        partes = urlparse(url)
        if "/pluginfile.php/" not in partes.path or not any(
            area in partes.path for area in areas
        ):
            continue
        nombre = unquote(partes.path.rstrip("/").rsplit("/", 1)[-1])
        if nombre:
            archivos.setdefault(url, AdjuntoRevision(url, nombre))
    return tuple(archivos.values())


def contiene_rubrica_tarea(html: str) -> bool:
    """Detecta una rúbrica renderizada en la calificación individual."""
    soup = BeautifulSoup(html, "html.parser")
    return soup.select_one(
        ".gradingform_rubric, .gradingform_rubric_editform, "
        "[data-gradingmethod='rubric']"
    ) is not None


def _extraer_usuario_id_fila_entrega(fila: Tag) -> int | None:
    for clase in fila.get("class", []):
        coincidencia = re.fullmatch(r"user(\d+)", str(clase))
        if coincidencia is not None:
            return int(coincidencia.group(1))
    for enlace in fila.find_all("a", href=True):
        partes = urlparse(str(enlace["href"]))
        if "/user/view.php" not in partes.path and "/user/profile.php" not in partes.path:
            continue
        valor = parse_qs(partes.query).get("id", [""])[0]
        if valor.isdigit():
            return int(valor)
    seleccion = fila.select_one(
        "input[name='selectedusers'][value], input[name='selectedusers[]'][value]"
    )
    valor = str(seleccion.get("value", "")) if seleccion is not None else ""
    return int(valor) if valor.isdigit() else None


def extraer_adjuntos_revision(
    html: str,
    url_pagina: str,
) -> tuple[AdjuntoRevision, ...]:
    """Localiza adjuntos de respuestas de ensayo en una revisión."""
    soup = BeautifulSoup(html, "html.parser")
    adjuntos: dict[str, AdjuntoRevision] = {}
    for elemento in soup.select("[href], [src]"):
        atributo = "href" if elemento.has_attr("href") else "src"
        url = urljoin(url_pagina, str(elemento.get(atributo, "")))
        partes = urlparse(url)
        if (
            "/pluginfile.php/" not in partes.path
            or "/question/response_attachments/" not in partes.path
        ):
            continue
        nombre = unquote(partes.path.rstrip("/").rsplit("/", 1)[-1])
        if not nombre:
            continue
        adjuntos.setdefault(
            url,
            AdjuntoRevision(url=url, nombre=nombre),
        )
    return tuple(adjuntos.values())


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


def _extraer_texto_visible(enlace: Tag) -> str:
    """Obtiene el título del enlace omitiendo etiquetas accesibles auxiliares."""
    fragmento = BeautifulSoup(str(enlace), "html.parser")
    copia = fragmento.find("a")
    if copia is None:
        return ""
    for oculto in copia.select(".accesshide, .sr-only, .visually-hidden"):
        oculto.decompose()
    return " ".join(copia.get_text(" ", strip=True).split())


def _extraer_texto_elemento_visible(elemento: Tag) -> str:
    """Obtiene el texto visible de una celda omitiendo ayudas accesibles."""
    fragmento = BeautifulSoup(str(elemento), "html.parser")
    copia = fragmento.find()
    if copia is None:
        return ""
    for oculto in copia.select(".accesshide, .sr-only, .visually-hidden"):
        oculto.decompose()
    return " ".join(copia.get_text(" ", strip=True).split())


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


def _extraer_entero(texto: str) -> int | None:
    """Convierte cantidades Moodle aunque incluyan separadores de millares."""
    digitos = "".join(caracter for caracter in texto if caracter.isdigit())
    return int(digitos) if digitos else None
