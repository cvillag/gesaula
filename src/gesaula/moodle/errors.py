"""Errores propios de comunicación y operación con Moodle."""


class ErrorConexionMoodle(Exception):
    """No se pudo acceder a la dirección indicada."""


class MoodleEnMantenimiento(ErrorConexionMoodle):
    """El servidor responde, pero Moodle está en mantenimiento."""


class FormularioLoginNoEncontrado(ErrorConexionMoodle):
    """La página no contiene el formulario de acceso esperado."""


class SesionMoodleExpirada(ErrorConexionMoodle):
    """La sesión dejó de ser válida o fue reemplazada por otra."""
