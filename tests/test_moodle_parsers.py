"""Pruebas de parsers de Moodle."""

from gesaula.moodle.parsers import (
    contiene_rubrica_tarea,
    extraer_actividades_descargables,
    extraer_adjuntos_revision,
    extraer_alumnos_level_up,
    extraer_cursos,
    extraer_cursos_ajax,
    extraer_entregas_tarea,
    extraer_intentos_cuestionario,
    extraer_numero_intentos_cuestionario,
    extraer_paginas_entregas_tarea,
    extraer_paginas_informe_cuestionario,
    extraer_sesskey,
    extraer_url_level_up,
    extraer_usuario_id,
    tiene_rol_profesor,
)


def test_extrae_imagen_de_background_image_antes_que_img_generica() -> None:
    """Las tarjetas Moodle suelen llevar la imagen real en CSS."""
    html = """
    <div class="course-card">
        <div
            class="courseimage"
            style='background-image: url("https://aula.test/pluginfile.php/110221/course/overviewfiles/curso.png");'
        >
            <img src="https://aula.test/theme/image.php/boost/core/1/f/bocadillo">
        </div>
        <a href="https://aula.test/course/view.php?id=42">Lengua 2º ESO</a>
    </div>
    """

    (curso,) = extraer_cursos(html, "https://aula.test/my/courses.php")

    assert curso.id == 42
    assert curso.nombre == "Lengua 2º ESO"
    assert (
        curso.imagen_url
        == "https://aula.test/pluginfile.php/110221/course/overviewfiles/curso.png"
    )


def test_extrae_imagen_de_card_img_top_hermano_del_enlace() -> None:
    """La imagen puede estar fuera del enlace, pero dentro de la misma tarjeta."""
    html = """
    <div class="card dashboard-card">
        <div
            class="card-img-top"
            style="background-image: url(&quot;https://aula.test/pluginfile.php/110221/course/overviewfiles/curso.png&quot;);"
        >
            <span class="sr-only">FPS_ASIRA1-Fundamentos de Programación</span>
        </div>
        <div class="card-body">
            <a href="https://aula.test/course/view.php?id=110221">
                FPS_ASIRA1-Fundamentos de Programación
            </a>
        </div>
    </div>
    """

    (curso,) = extraer_cursos(html, "https://aula.test/my/courses.php")

    assert curso.id == 110221
    assert curso.nombre == "FPS_ASIRA1-Fundamentos de Programación"
    assert (
        curso.imagen_url
        == "https://aula.test/pluginfile.php/110221/course/overviewfiles/curso.png"
    )


def test_extrae_curso_desde_course_card_con_data_course_id() -> None:
    """El dashboard de Moodle identifica cada tarjeta con data-course-id."""
    html = """
    <div class="card course-card mx-1" role="listitem"
         data-region="course-content" data-course-id="1501">
        <a href="https://aula.test/course/view.php?id=1501" tabindex="-1">
            <div class="card-img-top"
                 style="background-image: url(&quot;https://aula.test/pluginfile.php/110221/course/overviewfiles/curso.png&quot;);">
                <span class="sr-only">FPS_ASIRA1-Fundamentos de Programación</span>
            </div>
        </a>
        <div class="card-body pe-1 course-info-container">
            <a href="https://aula.test/course/view.php?id=1501"
               class="aalink coursename me-2 mb-1">
                <span class="sr-only">Nombre del curso</span>
                <span class="multiline"
                      title="FPS_ASIRA1-Fundamentos de Programación">
                    <span class="sr-only">FPS_ASIRA1-Fundamentos de Programación</span>
                    <span aria-hidden="true">
                        FPS_ASIRA1-Fundamentos de Programación
                    </span>
                </span>
            </a>
        </div>
    </div>
    """

    (curso,) = extraer_cursos(html, "https://aula.test/my/courses.php")

    assert curso.id == 1501
    assert curso.nombre == "FPS_ASIRA1-Fundamentos de Programación"
    assert curso.url == "https://aula.test/course/view.php?id=1501"
    assert (
        curso.imagen_url
        == "https://aula.test/pluginfile.php/110221/course/overviewfiles/curso.png"
    )


def test_tarjeta_sustituye_al_enlace_previo_de_navegacion() -> None:
    """La navegación aparece antes, pero la tarjeta contiene los datos completos."""
    html = """
    <nav>
        <a title="Nombre completo" href="/course/view.php?id=42">Nombre corto</a>
    </nav>
    <div class="card course-card" data-course-id="42">
        <a href="/course/view.php?id=42" tabindex="-1">
            <div class="card-img-top"
                 style="background-image: url('data:image/svg+xml;base64,PHN2Zy8+');">
            </div>
        </a>
        <a href="/course/view.php?id=42" class="coursename">
            <span class="sr-only">Nombre del curso</span>
            <span class="multiline" title="Nombre completo del curso">
                <span aria-hidden="true">Nombre completo del curso</span>
            </span>
        </a>
    </div>
    """

    (curso,) = extraer_cursos(html, "https://aula.test/my/courses.php")

    assert curso.nombre == "Nombre completo del curso"
    assert curso.imagen_url == "data:image/svg+xml;base64,PHN2Zy8+"


def test_respeta_el_orden_de_las_tarjetas_y_no_el_de_navegacion() -> None:
    """La lista lateral puede tener un orden distinto al mosaico de Moodle."""
    html = """
    <nav>
        <a href="/course/view.php?id=2">Dos</a>
        <a href="/course/view.php?id=1">Uno</a>
    </nav>
    <div data-region="course-content" data-course-id="1">
        <a class="coursename" href="/course/view.php?id=1">Uno</a>
    </div>
    <div data-region="course-content" data-course-id="2">
        <a class="coursename" href="/course/view.php?id=2">Dos</a>
    </div>
    """

    cursos = extraer_cursos(html, "https://aula.test/my/courses.php")

    assert [curso.id for curso in cursos] == [1, 2]


def test_extrae_sesskey_de_configuracion_moodle() -> None:
    html = '<script>M.cfg = {"wwwroot":"https:\\/\\/aula.test","sesskey":"abc123"};</script>'

    assert extraer_sesskey(html) == "abc123"


def test_extrae_cursos_de_respuesta_ajax() -> None:
    datos = {
        "courses": [
            {
                "id": 1599,
                "fullname": "FPS_ASIRB1_DAM1-(PENDIENTES)-Bases de Datos",
                "shortname": "FPS_PEND-BBDD",
                "viewurl": "https://aula.test/course/view.php?id=1599",
                "courseimage": "https://aula.test/pluginfile.php/115478/course/overviewfiles/bd3.png",
            },
            {
                "id": 906,
                "fullname": "Aula virtual para alumnos",
                "courseimage": "data:image/svg+xml;base64,PHN2Zy8+",
            },
        ]
    }

    cursos = extraer_cursos_ajax(datos, "https://aula.test/")

    assert [curso.id for curso in cursos] == [1599, 906]
    assert cursos[0].nombre == "FPS_ASIRB1_DAM1-(PENDIENTES)-Bases de Datos"
    assert cursos[0].imagen_url.endswith("/bd3.png")
    assert cursos[1].url == "https://aula.test/course/view.php?id=906"
    assert cursos[1].imagen_url == "data:image/svg+xml;base64,PHN2Zy8+"


def test_extrae_usuario_id_de_configuracion_moodle() -> None:
    html = '<script>M.cfg = {"sesskey":"abc123","userId":3876};</script>'

    assert extraer_usuario_id(html) == 3876


def test_detecta_exclusivamente_rol_profesor() -> None:
    html_profesor = """
    <dl><dt>Roles de curso</dt><dd><a>Profesor</a></dd></dl>
    """
    html_sin_edicion = """
    <dl><dt>Roles de curso</dt><dd><a>Profesor sin permiso de edición</a></dd></dl>
    """

    assert tiene_rol_profesor(html_profesor)
    assert not tiene_rol_profesor(html_sin_edicion)


def test_extrae_level_up_sin_depender_del_idioma_del_bloque() -> None:
    html = """
    <aside class="block_xp">
        <h5>Sube de nivel</h5>
        <a href="/blocks/xp/index.php/report/1203">Informe</a>
    </aside>
    """

    assert extraer_url_level_up(
        html,
        "https://aula.test/course/view.php?id=1203",
        1203,
    ) == "https://aula.test/blocks/xp/index.php/report/1203"


def test_no_ofrece_level_up_de_otro_curso() -> None:
    html = '<a href="/blocks/xp/index.php/report/999">Level up</a>'

    assert (
        extraer_url_level_up(
            html,
            "https://aula.test/course/view.php?id=1203",
            1203,
        )
        is None
    )


def test_extrae_alumnos_del_informe_level_up_y_descarta_fila_plantilla() -> None:
    html = """
    <table class="flexible block_xp-report-table" id="yui_id_variable">
      <thead><tr><th></th><th>Nombre</th><th>Nivel</th><th>Total</th></tr></thead>
      <tbody>
        <tr id="block_xp_report_r0">
          <td class="c0"></td>
          <td class="c1"><a href="/user/view.php?id=42&amp;course=1203">Ana Ejemplo</a></td>
          <td class="c2">3</td>
          <td class="c3"><span class="block_xp-xp"><span class="pts">1.250</span> xp</span></td>
          <td class="c5"><a data-xp-action="open-form"
            data-form-args__contextid="85744">Editar</a></td>
        </tr>
        <tr><td class="c0"></td><td class="c1"></td><td class="c2"></td><td class="c3"></td></tr>
      </tbody>
    </table>
    """

    (alumno,) = extraer_alumnos_level_up(html)

    assert alumno.id == 42
    assert alumno.nombre == "Ana Ejemplo"
    assert alumno.nivel == 3
    assert alumno.px == 1250
    assert alumno.context_id == 85744


def test_no_confunde_otra_tabla_con_el_informe_level_up() -> None:
    html = """
    <table><tbody><tr>
      <td class="c1"><a href="/user/view.php?id=42">Otro dato</a></td>
      <td class="c2">3</td><td class="c3">100</td>
    </tr></tbody></table>
    """

    assert extraer_alumnos_level_up(html) == ()


def test_extrae_actividades_descargables_unicas_del_curso() -> None:
    html = """
    <nav>
      <a class="courseindex-link" href="/mod/quiz/view.php?id=10">
        Control de la unidad 1
      </a>
    </nav>
    <main>
      <a href="/mod/quiz/view.php?id=10">
        <span class="instancename">Control de la unidad 1
          <span class="accesshide">Cuestionario</span>
        </span>
      </a>
      <a href="/mod/workshop/view.php?id=11">Taller de repaso</a>
      <a href="/mod/data/view.php?id=12">Base de datos del proyecto</a>
      <a href="/mod/geogebra/view.php?id=13">Construcción geométrica</a>
      <a href="/mod/glossary/view.php?id=14">Glosario de conceptos</a>
      <a href="/mod/assign/view.php?id=15">Entrega final</a>
      <a href="/mod/forum/view.php?id=16">Foro no descargable</a>
    </main>
    """

    actividades = extraer_actividades_descargables(
        html,
        "https://aula.test/course/view.php?id=1203",
    )

    assert [actividad.id for actividad in actividades] == [10, 11, 12, 13, 14, 15]
    assert [actividad.tipo for actividad in actividades] == [
        "Cuestionario",
        "Taller",
        "Base de datos",
        "GeoGebra",
        "Glosario",
        "Tarea",
    ]
    assert actividades[0].nombre == "Control de la unidad 1"
    assert actividades[0].url == "https://aula.test/mod/quiz/view.php?id=10"


def test_extrae_intentos_y_alumnos_del_informe_del_cuestionario() -> None:
    html = """
    <table id="attempts">
      <tbody>
        <tr>
          <td class="fullname">
            <a href="/user/view.php?id=42&amp;course=1203">Ana Ejemplo</a>
          </td>
          <td><a href="/mod/quiz/review.php?attempt=52049">Revisar</a></td>
          <td><a href="/mod/quiz/review.php?attempt=52049">Nota</a></td>
        </tr>
        <tr>
          <td class="fullname">
            <a href="/user/view.php?id=43&amp;course=1203">Luis Prueba</a>
          </td>
          <td><a href="/mod/quiz/review.php?attempt=52050">Revisar</a></td>
        </tr>
      </tbody>
    </table>
    """

    intentos = extraer_intentos_cuestionario(
        html,
        "https://aula.test/mod/quiz/report.php?id=10&mode=overview",
    )

    assert [intento.id for intento in intentos] == [52049, 52050]
    assert [intento.alumno_id for intento in intentos] == [42, 43]
    assert [intento.alumno for intento in intentos] == [
        "Ana Ejemplo",
        "Luis Prueba",
    ]
    assert intentos[0].url_revision == (
        "https://aula.test/mod/quiz/review.php?attempt=52049"
    )


def test_prioriza_nombre_completo_sobre_enlace_abreviado() -> None:
    html = """
    <table><tr>
      <td class="fullname">
        <a href="/user/view.php?id=42">Ana</a>
        <a href="/user/view.php?id=42">Ana García López</a>
      </td>
      <td><a href="/mod/quiz/review.php?attempt=100">Revisar</a></td>
    </tr></table>
    """

    intentos = extraer_intentos_cuestionario(
        html,
        "https://aula.test/mod/quiz/report.php?id=10&mode=overview",
    )

    assert intentos[0].alumno == "Ana García López"


def test_compone_nombre_y_apellidos_separados_por_moodle() -> None:
    html = """
    <table><tr>
      <td><a href="/user/view.php?id=42"><img alt="Perfil"></a></td>
      <td data-field="firstname">Ana María</td>
      <td data-field="lastname">García López</td>
      <td><a href="/mod/quiz/review.php?attempt=100">Revisar</a></td>
    </tr></table>
    """

    intentos = extraer_intentos_cuestionario(
        html,
        "https://aula.test/mod/quiz/report.php?id=10&mode=overview",
    )

    assert intentos[0].alumno == "Ana María García López"


def test_extrae_numero_intentos_de_la_portada_del_cuestionario() -> None:
    html = """
    <div class="box py-3 quizinfo">
      <p>Intentos permitidos: 1</p>
    </div>
    <div class="quizattemptcounts">
      <a href="/mod/quiz/report.php?id=82001&amp;mode=overview">
        Intentos: 2
      </a>
    </div>
    """

    assert extraer_numero_intentos_cuestionario(html) == 2
    assert extraer_numero_intentos_cuestionario("<main>Sin intentos</main>") == 0


def test_extrae_paginas_adicionales_del_informe() -> None:
    html = """
    <nav class="pagination">
      <a href="/mod/quiz/report.php?id=10&amp;mode=overview&amp;page=0">1</a>
      <a href="/mod/quiz/report.php?id=10&amp;mode=overview&amp;page=1">2</a>
      <a href="/course/view.php?id=1203">Curso</a>
    </nav>
    """

    paginas = extraer_paginas_informe_cuestionario(
        html,
        "https://aula.test/mod/quiz/report.php?id=10&mode=overview",
    )

    assert paginas == (
        "https://aula.test/mod/quiz/report.php?id=10&mode=overview&page=0",
        "https://aula.test/mod/quiz/report.php?id=10&mode=overview&page=1",
    )


def test_extrae_solo_adjuntos_de_respuestas_de_ensayo() -> None:
    html = """
    <div class="attachments">
      <a href="/pluginfile.php/100/question/response_attachments/200/1/informe.pdf?forcedownload=1">
        informe.pdf
      </a>
      <img src="/pluginfile.php/100/question/response_attachments/200/1/imagen.png">
      <a href="/pluginfile.php/100/question/response_answer/200/1/inline.png">
        Otro archivo
      </a>
    </div>
    """

    adjuntos = extraer_adjuntos_revision(
        html,
        "https://aula.test/mod/quiz/review.php?attempt=52049",
    )

    assert [adjunto.nombre for adjunto in adjuntos] == [
        "informe.pdf",
        "imagen.png",
    ]
    assert adjuntos[0].url.endswith(
        "/question/response_attachments/200/1/informe.pdf?forcedownload=1"
    )


def test_extrae_entregas_con_y_sin_contenido() -> None:
    html = """
    <table id="submissions"><tbody>
      <tr class="user42">
        <td class="fullname"><a href="/user/view.php?id=42">Ana García</a></td>
        <td>
          <a href="/pluginfile.php/1/assignsubmission_file/submission_files/7/tarea.pdf">
            tarea.pdf
          </a>
        </td>
        <td class="grade">8,50</td>
      </tr>
      <tr class="user43">
        <td class="fullname"><a href="/user/view.php?id=43">Luis Pérez</a></td>
        <td>
          <a
            href="/mod/assign/view.php?id=15&amp;action=viewpluginassignsubmission&amp;plugin=onlinetext"
          >
            Ver texto completo
          </a>
        </td>
        <td class="grade">-</td>
      </tr>
    </tbody></table>
    """

    entregas = extraer_entregas_tarea(
        html,
        "https://aula.test/mod/assign/view.php?id=15&action=grading",
        15,
    )

    assert [entrega.alumno for entrega in entregas] == [
        "Ana García",
        "Luis Pérez",
    ]
    assert entregas[0].archivos[0].nombre == "tarea.pdf"
    assert entregas[0].requiere_calificacion is False
    assert entregas[1].requiere_calificacion is True
    assert entregas[1].url_texto_completo is not None
    assert entregas[1].url_calificacion.endswith(
        "view.php?id=15&action=grade&userid=43"
    )


def test_extrae_paginacion_de_entregas_y_detecta_rubrica() -> None:
    html = """
    <nav class="pagination">
      <a href="/mod/assign/view.php?id=15&amp;action=grading&amp;page=1">2</a>
      <a href="/course/view.php?id=1&amp;page=1">Otro</a>
    </nav>
    """

    assert extraer_paginas_entregas_tarea(
        html,
        "https://aula.test/mod/assign/view.php?id=15&action=grading",
    ) == (
        "https://aula.test/mod/assign/view.php?id=15&action=grading&page=1",
    )
    assert contiene_rubrica_tarea(
        '<div class="gradingform_rubric">Criterios</div>'
    )
