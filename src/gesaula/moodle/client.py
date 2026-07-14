"""Cliente Moodle basado en una sesión web persistente."""

from urllib.parse import urljoin, urlparse

import httpx

from gesaula.moodle.errors import (
    ErrorConexionMoodle,
    FormularioLoginNoEncontrado,
    MoodleEnMantenimiento,
    SesionMoodleExpirada,
)
from gesaula.moodle.models import ComprobacionesLogin, CursoMoodle, ResultadoLogin
from gesaula.moodle.parsers import (
    MENSAJE_MANTENIMIENTO,
    contiene_error_credenciales,
    contiene_error_sesion,
    contiene_formulario_login,
    contiene_identidad_usuario,
    esta_en_mantenimiento,
    extraer_cursos,
    extraer_cursos_ajax,
    extraer_formulario_login,
    extraer_sesskey,
    extraer_url_level_up,
    extraer_usuario_id,
    tiene_rol_profesor,
)

TIEMPO_ESPERA = 10.0


class ClienteMoodle:
    """Mantiene las cookies de una sesión web de Moodle."""

    def __init__(self, url_base: str) -> None:
        self.url_base = f"{url_base.rstrip('/')}/"
        self._http = httpx.Client(follow_redirects=True, timeout=TIEMPO_ESPERA)
        self._autenticado = False
        self._cerrado = False
        self._usuario_id: int | None = None

    def iniciar_sesion(self, usuario: str, contrasena: str) -> ResultadoLogin:
        """Envía el formulario real y evalúa cuatro señales de autenticación."""
        url_login = urljoin(self.url_base, "login/index.php")
        pagina_login = self._get(url_login)
        formulario = extraer_formulario_login(
            pagina_login.text, str(pagina_login.url)
        )
        if formulario is None:
            raise FormularioLoginNoEncontrado(
                "No se encontró el formulario de acceso de Moodle."
            )

        datos = {
            **formulario.campos_ocultos,
            "username": usuario,
            "password": contrasena,
        }
        pagina_posterior = self._post(formulario.action, datos)

        url_cursos_solicitada = urljoin(self.url_base, "my/courses.php")
        pagina_cursos = self._get(url_cursos_solicitada, aceptar_error_http=True)
        self._usuario_id = extraer_usuario_id(pagina_cursos.text)

        comprobaciones = ComprobacionesLogin(
            formulario_desaparecido=not contiene_formulario_login(
                pagina_posterior.text
            ),
            identidad_usuario_visible=(
                contiene_identidad_usuario(pagina_posterior.text)
                or contiene_identidad_usuario(pagina_cursos.text)
            ),
            sin_error_credenciales=not contiene_error_credenciales(
                pagina_posterior.text
            ),
            pagina_cursos_accesible=self._pagina_cursos_accesible(pagina_cursos),
        )
        cursos_html = extraer_cursos(pagina_cursos.text, str(pagina_cursos.url))
        cursos_ajax = self._obtener_cursos_ajax(pagina_cursos.text)
        resultado = ResultadoLogin(
            comprobaciones=comprobaciones,
            html_cursos=pagina_cursos.text,
            url_cursos=str(pagina_cursos.url),
            # El servicio AJAX es la fuente principal. El HTML se conserva como
            # respaldo para instalaciones que desactiven o cambien el servicio.
            cursos=cursos_ajax or cursos_html,
        )
        self._autenticado = comprobaciones.aceptado
        return resultado

    def obtener(self, ruta: str) -> httpx.Response:
        """Realiza un GET autenticado y comprueba que la sesión siga activa."""
        self._comprobar_sesion_iniciada()
        return self._get(urljoin(self.url_base, ruta), requiere_sesion=True)

    def enviar(self, ruta: str, datos: dict[str, str]) -> httpx.Response:
        """Realiza un POST autenticado y comprueba que la sesión siga activa."""
        self._comprobar_sesion_iniciada()
        return self._post(
            urljoin(self.url_base, ruta),
            datos,
            requiere_sesion=True,
        )

    def usuario_es_profesor(self, curso_id: int) -> bool:
        """Comprueba el rol del usuario en el perfil contextual del curso."""
        self._comprobar_sesion_iniciada()
        if self._usuario_id is None:
            raise ErrorConexionMoodle(
                "No se pudo identificar al usuario autenticado para comprobar su rol."
            )
        respuesta = self.obtener(
            f"user/view.php?id={self._usuario_id}&course={curso_id}"
        )
        return tiene_rol_profesor(respuesta.text)

    def obtener_url_level_up(self, curso_id: int) -> str | None:
        """Busca en la página del curso el enlace aportado por Level up."""
        respuesta = self.obtener(f"course/view.php?id={curso_id}")
        return extraer_url_level_up(
            respuesta.text,
            str(respuesta.url),
            curso_id,
        )

    def cerrar(self) -> None:
        """Cierra conexiones y libera la sesión."""
        self._autenticado = False
        self._usuario_id = None
        if self._cerrado:
            return
        self._cerrado = True
        self._http.close()

    def _get(
        self,
        url: str,
        *,
        aceptar_error_http: bool = False,
        requiere_sesion: bool = False,
    ) -> httpx.Response:
        try:
            respuesta = self._http.get(url)
        except RuntimeError as error:
            raise SesionMoodleExpirada(
                "La sesión de Moodle se ha cerrado."
            ) from error
        except httpx.TimeoutException as error:
            raise ErrorConexionMoodle(
                f"El servidor no respondió en {TIEMPO_ESPERA:g} segundos."
            ) from error
        except httpx.RequestError as error:
            raise ErrorConexionMoodle(f"No se pudo conectar: {error}") from error
        self._validar_respuesta(
            respuesta,
            aceptar_error_http=aceptar_error_http,
            requiere_sesion=requiere_sesion,
        )
        return respuesta

    def _post_json(self, url: str, datos: object) -> httpx.Response:
        """Realiza un POST JSON reutilizando cookies y validaciones de la sesión."""
        try:
            respuesta = self._http.post(url, json=datos)
        except RuntimeError as error:
            raise SesionMoodleExpirada("La sesión de Moodle se ha cerrado.") from error
        except httpx.TimeoutException as error:
            raise ErrorConexionMoodle(
                f"El servidor no respondió en {TIEMPO_ESPERA:g} segundos."
            ) from error
        except httpx.RequestError as error:
            raise ErrorConexionMoodle(f"No se pudo conectar: {error}") from error
        self._validar_respuesta(
            respuesta,
            aceptar_error_http=False,
            requiere_sesion=True,
        )
        return respuesta

    def _obtener_cursos_ajax(self, html_cursos: str) -> tuple[CursoMoodle, ...]:
        """Obtiene todos los cursos mediante el servicio usado por el dashboard."""
        sesskey = extraer_sesskey(html_cursos)
        if sesskey is None:
            return ()

        metodo = "core_course_get_enrolled_courses_by_timeline_classification"
        url = urljoin(
            self.url_base,
            f"lib/ajax/service.php?sesskey={sesskey}&info={metodo}",
        )
        solicitud = [
            {
                "index": 0,
                "methodname": metodo,
                "args": {
                    "offset": 0,
                    "limit": 0,
                    "classification": "all",
                    "sort": "fullname",
                    "customfieldname": "",
                    "customfieldvalue": "",
                },
            }
        ]
        try:
            respuesta = self._post_json(url, solicitud)
            mensajes = respuesta.json()
        except (MoodleEnMantenimiento, SesionMoodleExpirada):
            raise
        except (ErrorConexionMoodle, ValueError):
            # El HTML sigue siendo una fuente válida si este servicio interno
            # no está disponible en una versión o configuración de Moodle.
            return ()

        if not isinstance(mensajes, list) or not mensajes:
            return ()
        mensaje = mensajes[0]
        if not isinstance(mensaje, dict) or mensaje.get("error"):
            return ()
        return extraer_cursos_ajax(mensaje.get("data"), self.url_base)

    def _post(
        self,
        url: str,
        datos: dict[str, str],
        *,
        requiere_sesion: bool = False,
    ) -> httpx.Response:
        try:
            respuesta = self._http.post(url, data=datos)
        except RuntimeError as error:
            raise SesionMoodleExpirada(
                "La sesión de Moodle se ha cerrado."
            ) from error
        except httpx.TimeoutException as error:
            raise ErrorConexionMoodle(
                f"El servidor no respondió en {TIEMPO_ESPERA:g} segundos."
            ) from error
        except httpx.RequestError as error:
            raise ErrorConexionMoodle(f"No se pudo conectar: {error}") from error
        self._validar_respuesta(
            respuesta,
            aceptar_error_http=False,
            requiere_sesion=requiere_sesion,
        )
        return respuesta

    def _validar_respuesta(
        self,
        respuesta: httpx.Response,
        *,
        aceptar_error_http: bool,
        requiere_sesion: bool,
    ) -> None:
        if esta_en_mantenimiento(respuesta.text):
            raise MoodleEnMantenimiento(f"{MENSAJE_MANTENIMIENTO}.")
        if requiere_sesion and self._respuesta_sin_sesion(respuesta):
            self._autenticado = False
            raise SesionMoodleExpirada(
                "La sesión de Moodle ya no está activa. Puede haber caducado "
                "o haberse cerrado al iniciar otra sesión."
            )
        if respuesta.is_error and not aceptar_error_http:
            raise ErrorConexionMoodle(
                f"El servidor respondió con el estado HTTP {respuesta.status_code}."
            )

    def _comprobar_sesion_iniciada(self) -> None:
        if not self._autenticado:
            raise SesionMoodleExpirada(
                "No hay una sesión activa de Moodle. Inicia sesión de nuevo."
            )

    @staticmethod
    def _respuesta_sin_sesion(respuesta: httpx.Response) -> bool:
        ruta_final = urlparse(str(respuesta.url)).path.rstrip("/")
        return (
            respuesta.status_code == 401
            or ruta_final.endswith("/login/index.php")
            or contiene_formulario_login(respuesta.text)
            or contiene_error_sesion(respuesta.text)
        )

    @staticmethod
    def _pagina_cursos_accesible(respuesta: httpx.Response) -> bool:
        ruta_final = urlparse(str(respuesta.url)).path.rstrip("/")
        vuelve_al_login = ruta_final.endswith("/login/index.php")
        return (
            not respuesta.is_error
            and not vuelve_al_login
            and not contiene_formulario_login(respuesta.text)
        )
