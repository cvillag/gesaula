"""Pruebas de parsers de Moodle."""

from gesaula.moodle.parsers import extraer_cursos, extraer_cursos_ajax, extraer_sesskey


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
