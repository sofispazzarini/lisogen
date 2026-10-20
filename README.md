# LisoGen · Sistema de Estudios Genéticos

Sistema de gestión de Estudios de exoma clínico para cinco Patologías lisosomales: Fabry, Pompe, MPS 1, Gaucher y ASMD.

**Stack:** PostgreSQL 16 · FastAPI · Vue 3

> 🚧 En construcción. Etapa actual: **3 · Dominio y máquina de estados**.

## Levantarlo

Requisitos: Docker (con Compose v2) y [uv](https://docs.astral.sh/uv/) para correr los tests fuera de Docker.

```bash
cp .env.example .env
make up      # postgres 16, minio, mailpit y la API (aplica las migraciones al iniciar)
make seed    # vacía la base y carga los datos de ejemplo
make test    # tests del backend contra el Postgres de compose
```

| Servicio | URL |
|---|---|
| API (OpenAPI) | http://localhost:8000/docs |
| Chequeo de salud | http://localhost:8000/salud |
| Mailpit (mails enviados) | http://localhost:8025 |
| Consola de MinIO | http://localhost:9001 |

`make help` lista todos los comandos.

### Usuarios demo

Contraseña de todos: `Demo-2026!`. La primera vez que ingresás desde un navegador o equipo nuevo, LisoGen manda un código de verificación por mail: lo ves en Mailpit (http://localhost:8025).

| Rol | Mail |
|---|---|
| Médico Tratante | medico@lisogen-demo.com.ar |
| Paciente | paciente@lisogen-demo.com.ar |
| Administrativo del Laboratorio | administrativo@lisogen-demo.com.ar |
| Transportista (CABA) | transportista@lisogen-demo.com.ar |
| Bioinformático | bioinformatico@lisogen-demo.com.ar |
| Gerente Médico | gerente@lisogen-demo.com.ar |

## Documentación

- [`schema.sql`](schema.sql): modelo de datos de referencia (PostgreSQL 16).
- [`docs/Escenarios.pdf`](docs/Escenarios.pdf): Escenarios E1–E33.
- [`docs/Glosario_LEL.pdf`](docs/Glosario_LEL.pdf): vocabulario del dominio (LEL).
- [`docs/TRAZABILIDAD.md`](docs/TRAZABILIDAD.md): Escenario → servicio → endpoint → vista.
- [`docs/DECISIONES.md`](docs/DECISIONES.md): decisiones de diseño y SUPUESTOs a validar con el PO.
- [`docs/PROMPT_CLAUDE_CODE.md`](docs/PROMPT_CLAUDE_CODE.md): pedido original de construcción.
