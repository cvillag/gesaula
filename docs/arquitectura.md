# Arquitectura inicial

## Contexto

`gesaula` será una aplicación local de escritorio para profesores. No tendrá usuarios propios ni expondrá un servicio web. Usará las credenciales normales de Moodle para iniciar sesión en el Aula Virtual y realizar acciones que el profesor ya podría hacer manualmente desde el navegador.

Servidor inicial:

`https://aulavirtual33.educa.madrid.org/ies.quevedo.madrid/`

## Decisiones

- Aplicación local y monolítica.
- Python como lenguaje principal.
- Interfaz gráfica con PySide6.
- Comunicación con Moodle mediante sesión web HTTP.
- Sin API oficial de Moodle en la primera versión.
- Sin base de datos local.
- La contraseña se pedirá en cada sesión y no se guardará.
- La URL, el usuario y los ids de cursos seleccionados sí podrán guardarse localmente.
- Las acciones futuras se modelarán como componentes ampliables.

## Capas

```text
Interfaz gráfica
  -> Acciones / casos de uso
    -> Cliente Moodle
      -> HTTP + parsers HTML
```

## Entidades iniciales

### PerfilConexion

- URL de Moodle.
- Usuario.
- Ids de cursos fijados.

### CursoMoodle

- Id.
- Nombre.
- URL.
- Estado de acceso.

### SesionMoodle

- Usuario.
- Cookies de sesión.
- `sesskey`, si Moodle lo proporciona.
- Estado de autenticación.

### Accion

- Nombre.
- Descripción.
- Requisitos.
- Ejecución con progreso.

## Riesgos

- Cambios en el HTML o tema de Moodle.
- Diferencias entre la versión documentada y la versión real de Moodle.
- Caducidad de sesión en operaciones largas.
- Mantenimiento programado del servidor.
- Cursos donde el profesor aparece como alumno, claustro o departamento.
- Formularios complejos en acciones futuras.

## Estrategia de pruebas

- Tests automáticos para configuración, parsers y acciones sin conexión.
- Pruebas manuales para login real.
- Muestras HTML controladas para evitar depender siempre del servidor.

