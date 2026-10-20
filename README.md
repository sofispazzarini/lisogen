# LisoGen · Sistema de Estudios Genéticos

Sistema de gestión de Estudios de exoma clínico para cinco Patologías lisosomales: Fabry, Pompe, MPS 1, Gaucher y ASMD.

**Stack:** PostgreSQL 16 · FastAPI · Vue 3

Base funcional completa: backend (etapas 1 a 5) y frontend por rol (etapa 6).

## Levantarlo

Requisitos: Docker (con Compose v2). Para correr tests fuera de Docker: [uv](https://docs.astral.sh/uv/) y Node 22.

```bash
cp .env.example .env
make up      # postgres 16, minio, mailpit, la API (aplica las migraciones) y el front
make seed    # vacía la base y carga los datos de ejemplo
```

Abrí **http://localhost:5173** e ingresá con un usuario demo.

```bash
make test        # backend: pytest contra el Postgres de compose
make test-front  # frontend: Vitest
make lint lint-front
```

| Servicio | URL |
|---|---|
| **Frontend** | http://localhost:5173 |
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

## Mapa de escenarios cubiertos

Cada escenario tiene servicio, endpoint, vista y test (detalle en [`docs/TRAZABILIDAD.md`](docs/TRAZABILIDAD.md)).

| Rol | Escenarios | Dónde, en el front |
|---|---|---|
| Médico Tratante | E1 registro · E2 Alta Paciente · E3 Familiograma · E4 Alta Estudio · E5 Cupones · E6 Reanálisis | `/registro`, `/medico/pacientes/nuevo`, `/medico/estudios/nuevo`, `/medico/cupones`, ficha del Paciente |
| Paciente | E7 primer ingreso · E8 Pagar · E9 Cupón · E10 Reautorización · E11 Sacar Turno · E12 Cancelar · E13 Resultado · E14 Chatbot | `/ingresar`, `/paciente` y el detalle de cada Estudio, `/paciente/chatbot` |
| Administrativo | E15 registro · E16 Presupuesto · E17/E18 Autorización y Rechazo · E19 Seguir Muestra · E20 Lotes y FedEx · E21 Datos crudos · E22 Nueva extracción | `/administrativo/…` |
| Transportista | E23 Orden del Día · E24 Recolectar · E25 Confirmar llegada | `/transportista` (pensado para el celular) |
| Bioinformático | E26 registro · E27 Tomar Estudio · E28 Cargar Variantes | `/bioinformatico` |
| Gerente Médico | E29 registro · E30/E31 Patologías · E32/E33 Cupones | `/gerente` |

Procesos automáticos (Orden del Día, inasistencias, recordatorios, mails, FedEx simulado): ver "Tareas programadas". Fuera de alcance por decisión del PO: tablero de control de gerencia, WhatsApp y pasarela de pago real.

## Estructura

```
backend/   FastAPI · SQLAlchemy 2 (async) · Alembic · APScheduler · pytest
frontend/  Vue 3 · Vite · TypeScript · Pinia · Vue Router · Leaflet · Vitest
docs/      Escenarios, LEL, TRAZABILIDAD, DECISIONES
```

## Documentación

- [`schema.sql`](schema.sql): modelo de datos de referencia (PostgreSQL 16).
- [`docs/Escenarios.pdf`](docs/Escenarios.pdf): Escenarios E1–E33.
- [`docs/Glosario_LEL.pdf`](docs/Glosario_LEL.pdf): vocabulario del dominio (LEL).
- [`docs/TRAZABILIDAD.md`](docs/TRAZABILIDAD.md): Escenario → servicio → endpoint → vista.
- [`docs/DECISIONES.md`](docs/DECISIONES.md): decisiones de diseño y SUPUESTOs a validar con el PO.
- [`docs/PROMPT_CLAUDE_CODE.md`](docs/PROMPT_CLAUDE_CODE.md): pedido original de construcción.
