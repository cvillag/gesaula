# gesaula

Herramienta local de escritorio para realizar acciones controladas sobre un Aula Virtual Moodle usando las credenciales del profesor.

## Objetivo inicial

La primera versión se centrará en:

- Configurar la URL del Aula Virtual.
- Guardar localmente la URL y el usuario.
- Pedir la contraseña en cada conexión.
- Iniciar sesión contra Moodle mediante la sesión web normal.
- Verificar que el acceso es correcto.
- Validar cursos por id.
- Buscar cursos disponibles para el usuario.
- Mostrar el estado de conexión, cursos accesibles y errores relevantes.

## Fuera de alcance inicial

- API oficial de Moodle, porque el servidor de EducaMadrid la tiene restringida para este uso.
- Automatización de LevelUp.
- Gestión de entregas o cuestionarios.
- Descarga o almacenamiento interno de datos de alumnado.
- Servicio web, multiusuario o app móvil.
- Base de datos local.

## Enfoque técnico

La aplicación será monolítica y local, escrita en Python. La comunicación con Moodle se hará inicialmente mediante HTTP, manteniendo cookies de sesión y analizando el HTML devuelto por Moodle.

Si el flujo web de Moodle requiere JavaScript o interacciones difíciles de reproducir con HTTP, se evaluará Playwright como alternativa para la capa de comunicación.

