# LisoGen · Sistema de Estudios Genéticos

Sistema de gestión de Estudios de exoma clínico para cinco Patologías lisosomales: Fabry, Pompe, MPS 1, Gaucher y ASMD.

**Stack:** PostgreSQL 16 · FastAPI · Vue 3

> 🚧 En construcción. Etapa actual: **5 · Integraciones y jobs** (backend completo; el frontend llega en la etapa 6).

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

### Estudios de ejemplo (`make seed`)

| Código | Paciente | Patología | Estado |
|---|---|---|---|
| EST-…-000001 | Martín Ibarra (Paciente demo) | Fabry | Finalizado, Resultado positivo |
| EST-…-000002 | Lucas Ferrari, 2 meses (OSPS) | Pompe · **Urgente** | En análisis por bioinformática |
| EST-…-000003 | Martín Ibarra (Paciente demo) | Gaucher | Por Pagar, con un Cupón del 20% para aplicar |
| EST-…-000004 | Valeria Quiroga (Prepaga Andina) | MPS 1 | Creado (para Emitir Presupuesto) |
| EST-…-000005 | Jorge Medina (Obra Social Federal) | ASMD | Pendiente de Autorización |
| EST-…-000006 | Paula Sosa (particular) | Fabry | Listo para Retirar en Caballito (Orden del Día de hoy, si es hábil) |

### Tareas programadas

Corren dentro de la API con APScheduler (hora Argentina). Para la demo se pueden disparar a mano con `make job TAREA=<nombre>`.

| Tarea | Cuándo | Qué hace |
|---|---|---|
| `orden_del_dia` | L–V 06:00 | Genera la Orden del Día de cada Transportista (no en feriados) |
| `cierre_de_jornada` | L–V 18:30 | Turnos vencidos sin Muestra → Ausente; con 5 inasistencias se pierde el pago |
| `recordatorios` | cada 15' | Recordatorio del Turno el día anterior a las 9 |
| `mails` | cada 15" | Envía los avisos por mail pendientes (Mailpit en local) |
| `fedex` | cada 1' | Sólo con integraciones mock: FedEx confirma los retiros cuya hora ya pasó |

## Documentación

- [`schema.sql`](schema.sql): modelo de datos de referencia (PostgreSQL 16).
- [`docs/Escenarios.pdf`](docs/Escenarios.pdf): Escenarios E1–E33.
- [`docs/Glosario_LEL.pdf`](docs/Glosario_LEL.pdf): vocabulario del dominio (LEL).
- [`docs/TRAZABILIDAD.md`](docs/TRAZABILIDAD.md): Escenario → servicio → endpoint → vista.
- [`docs/DECISIONES.md`](docs/DECISIONES.md): decisiones de diseño y SUPUESTOs a validar con el PO.
- [`docs/PROMPT_CLAUDE_CODE.md`](docs/PROMPT_CLAUDE_CODE.md): pedido original de construcción.
