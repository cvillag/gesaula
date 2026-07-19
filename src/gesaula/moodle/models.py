"""Modelos de datos procedentes de Moodle."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CursoMoodle:
    """Curso encontrado en la página Mis cursos."""

    id: int
    nombre: str
    url: str
    imagen_url: str | None = None


@dataclass(frozen=True)
class AlumnoLevelUp:
    """Alumno mostrado en el informe del bloque Level up."""

    id: int
    nombre: str
    nivel: int
    px: int
    context_id: int | None = None


@dataclass(frozen=True)
class ActividadDescargable:
    """Actividad del curso que podrá almacenarse localmente."""

    id: int
    nombre: str
    tipo: str
    url: str


@dataclass(frozen=True)
class IntentoCuestionario:
    """Intento de un alumno disponible para revisión."""

    id: int
    alumno_id: int | None
    alumno: str
    url_revision: str


@dataclass(frozen=True)
class AdjuntoRevision:
    """Archivo adjunto enlazado desde la revisión de un cuestionario."""

    url: str
    nombre: str


@dataclass(frozen=True)
class EntregaTarea:
    """Fila de un alumno encontrada en la pestaña Entregas."""

    alumno_id: int
    alumno: str
    html_resumen: str
    url_calificacion: str
    archivos: tuple[AdjuntoRevision, ...]
    url_texto_completo: str | None
    requiere_calificacion: bool


@dataclass(frozen=True)
class FormularioLogin:
    """Datos necesarios para reproducir el formulario de acceso."""

    action: str
    campos_ocultos: dict[str, str]


@dataclass(frozen=True)
class ComprobacionesLogin:
    """Señales observadas después de enviar las credenciales."""

    formulario_desaparecido: bool
    identidad_usuario_visible: bool
    sin_error_credenciales: bool
    pagina_cursos_accesible: bool

    @property
    def aceptado(self) -> bool:
        """Acepta el login únicamente si se cumplen todas las señales."""
        return all(
            (
                self.formulario_desaparecido,
                self.identidad_usuario_visible,
                self.sin_error_credenciales,
                self.pagina_cursos_accesible,
            )
        )


@dataclass(frozen=True)
class ResultadoLogin:
    """Resultado diagnóstico del intento de autenticación."""

    comprobaciones: ComprobacionesLogin
    html_cursos: str
    url_cursos: str
    cursos: tuple[CursoMoodle, ...]
