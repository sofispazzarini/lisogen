Sos un ingeniero de software senior especializado en sistemas para laboratorios de genética clínica. Vas a construir la **base funcional** de LisoGen, un sistema de gestión de estudios de exoma clínico para cinco patologías lisosomales (Fabry, Pompe, MPS 1, Gaucher, ASMD).

## Fuentes de verdad (leelas antes de escribir código)

1. `schema.sql` — modelo de datos de referencia, ya probado en PostgreSQL 16. Es el contrato: no lo cambies sin justificarlo en `docs/DECISIONES.md`.
2. `docs/Escenarios.pdf` — 33 escenarios (E1–E33) con episodios y excepciones. Cada endpoint y cada pantalla se trazan a un escenario.
3. `docs/Glosario_LEL.pdf` — vocabulario del dominio. Usá exactamente esos términos (Estudio, Muestra, Lote, Turno, Presupuesto, Cupón, Orden del Día, Variante…) en código de dominio, API y UI. Identificadores en español sin tildes (`estudio`, `orden_del_dia`).

Si dos fuentes se contradicen, prevalecen los Escenarios y `schema.sql`. Ante un hueco, decidí lo mínimo razonable, marcalo `SUPUESTO` en el código y registralo en `docs/DECISIONES.md`. No inventes funcionalidades fuera de los escenarios.

## Stack obligatorio

- **DB**: PostgreSQL 16. Migraciones con **Alembic**; la migración inicial reproduce `schema.sql` 1:1 (enums, índices parciales, CHECKs incluidos).
- **Backend**: Python 3.12, **FastAPI**, **SQLAlchemy 2.0** (estilo `Mapped[]`, sesión async con `asyncpg`), **Pydantic v2**, `uv` como gestor. Auth con JWT (access + refresh) y `argon2` para hashes. Jobs programados con **APScheduler**.
- **Frontend**: **Vue 3** + **Vite** + **TypeScript** + **Pinia** + **Vue Router**. Cliente HTTP tipado generado desde el OpenAPI (`openapi-typescript`). Mapas con **Leaflet**. Sin librerías de UI pesadas: componentes propios con CSS variables.
- **Infra local**: `docker-compose` con `postgres`, `api`, `web`, **Mailpit** (mail) y **MinIO** (archivos).
- **Calidad**: `ruff` + `mypy` en backend, `eslint` + `vue-tsc` en front, **pytest** con base Postgres real (testcontainers o el servicio de compose), **Vitest** en front.

## Estructura

```
lisogen/
  docker-compose.yml  .env.example  Makefile  README.md
  docs/DECISIONES.md  docs/TRAZABILIDAD.md
  backend/
    pyproject.toml  alembic/
    app/
      main.py  config.py  db.py  security.py
      domain/            # enums, reglas puras, máquina de estados (sin FastAPI ni SQLAlchemy)
      models/            # ORM, un archivo por agregado
      schemas/           # Pydantic de entrada/salida
      services/          # casos de uso = escenarios (transaccionales)
      api/routers/       # un router por rol + auth
      integrations/      # puertos (Protocol) + adaptadores mock + log
      jobs/              # tareas programadas
      seed/              # datos de ejemplo
    tests/
  frontend/
    src/ api/ stores/ router/ layouts/ components/ views/<rol>/
```

## Reglas de negocio que tienen que estar en `domain/` y con tests

1. **Máquina de estados del Estudio** (`estado_estudio`): una sola función `transicionar(estudio, destino, actor, motivo)` que valida el par origen→destino y el rol habilitado, escribe `estudio_estado_historial` y dispara notificaciones (APP + MAIL) al Paciente y al Médico Tratante. Ningún otro código cambia `estudio.estado`. Camino principal: CREADO → POR_PAGAR | PENDIENTE_AUTORIZACION → PAGADO | AUTORIZADO → TURNO_SACADO → LISTO_PARA_RETIRAR → EN_CAMINO_LAB_CENTRAL → EN_LAB_CENTRAL → EN_ESPERA_RETIRO → EN_VIAJE_COREA → EN_ANALISIS_BIOINFORMATICA → EN_ANALISIS → FINALIZADO. Desvíos: rechazo de Obra Social y reautorización; cancelar Turno vuelve a PAGADO/AUTORIZADO; 5 inasistencias vuelve a POR_PAGAR y registra `PERDIDA_POR_INASISTENCIAS`; re-extracción vuelve a PAGADO/AUTORIZADO sin costo.
2. **Validar Diagnóstico** (E2): alta de Paciente sólo si sus síntomas SNOMED incluyen el síntoma cardinal de la Patología o al menos dos secundarios.
3. **Urgente**: alguna Patología del Estudio es Pompe y el Paciente tiene menos de 4 meses. Efectos: el Lote se sella sin esperar 10 Muestras y el Estudio aparece primero para Bioinformática. No saltea el pago ni el retiro programado de FedEx.
4. **Presupuesto** (E16): USD 500 hasta 5 genes + USD 30 por gen adicional; los hallazgos secundarios no suman. Cobertura % desde la API de obras sociales; Cupón aplica % sobre lo que paga el Paciente. Montos con `Decimal`, nunca float. Particular → POR_PAGAR; con Obra Social → PENDIENTE_AUTORIZACION; cobertura parcial → autorización + pago de la diferencia.
5. **Agenda** (E11): Turnos de 15', lunes a viernes 9–18 hora Argentina, sin `feriado`, un Paciente por slot y un Turno activo por Estudio. Sólo si el Estudio está PAGADO o AUTORIZADO. Al reservar: genera PDFs de orden de extracción y consentimiento informado y programa recordatorio.
6. **Lotes** (E25): un único Lote EN_FORMACION. Al confirmar llegada, cada Muestra < 2 ml queda VOLUMEN_INSUFICIENTE y genera `solicitud_reextraccion` automática; el resto entra al Lote. Con 10 Muestras o un Urgente: envía CSV al Ministerio, asocia el PDF de autorización, sella y pasa a EN_ESPERA_RETIRO. Muestras que llegan después del sellado van al Lote siguiente.
7. **Tomar Estudio** (E27): lock optimista con `estudio.version`; si otro Bioinformático lo tomó, responder 409.
8. **Resultado** (E28): sin Variantes → NEGATIVO; al menos una PATOGENICA → POSITIVO; sólo inciertas → NO_CONCLUYENTE (SUPUESTO). Genera PDF, notifica a Médico Tratante y Paciente.
9. **Reanálisis** (E6): nuevo Estudio tipo REANALISIS con `estudio_origen_id`; reutiliza datos crudos del original, no pasa por Turno ni logística.
10. **Cupón**: DISPONIBLE → ASIGNADO_MEDICO → ASIGNADO_PACIENTE → USADO; uso único.

## Integraciones externas

Cada una es un `Protocol` en `integrations/ports.py` con un adaptador **mock determinístico** (seleccionable por `.env`) y todas las llamadas quedan en `integracion_log`:
API de bioinformática (genes por Patología, variantes por gen), API de obras sociales (cobertura %), API de familiograma (devuelve PDF), SNOMED (búsqueda de términos, desde caché local), módulo de cupones (código + QR), FedEx (programar retiro, webhook de confirmación), Ministerio de Salud (recibe CSV, devuelve PDF), optimización de recorridos (ordena paradas), chatbot (responde sobre las 5 Patologías, no deriva a humanos), mail (SMTP a Mailpit).

## Jobs (APScheduler)

- 06:00 L–V hábiles: generar `orden_del_dia` por Transportista con Centros que tienen Muestras LISTO_PARA_RETIRAR (no se genera en feriados).
- Recordatorio de Turno el día anterior.
- Cierre de jornada: los Turnos RESERVADO vencidos pasan a AUSENTE y suman inasistencia.

## API por rol (prefijos)

`/auth` (login, cambio de contraseña obligatorio, código de verificación por dispositivo nuevo, registro de profesionales) · `/medico` (E2–E6) · `/paciente` (E7–E14) · `/administrativo` (E16–E22 + registro financiero) · `/transportista` (E23–E25 + envío de posición) · `/bioinformatico` (E27, E28) · `/gerente` (E30–E33). Autorización por rol con dependencia de FastAPI; un Paciente sólo ve sus Estudios y un Médico sólo sus Pacientes. Errores de negocio como `409/422` con `{code, message}` en español.

## Frontend

Un layout por rol con la navegación del prototipo: bandeja de Avisos, tabla de Estudios con badge de Estado y Urgente, y estas vistas mínimas: Login / cambio de contraseña / verificación · Registro profesional · Médico: Alta Paciente (con buscador SNOMED y familiograma), Alta Estudio (genes de la API + manuales + hallazgos secundarios), Ficha con historial y Reanálisis, Mis Cupones · Paciente: Mis Estudios con línea de pasos, Pagar con Cupón, Reautorización (subir PDF), Sacar Turno (mapa Leaflet de Centros + grilla de slots), Mi Turno, Resultado, Chatbot · Administrativo: tablero, Emitir Presupuesto, Autorizaciones, Seguir Muestra en mapa, Lotes y retiro FedEx, Cargar datos crudos, Nueva extracción, Registro financiero · Transportista (mobile-first): Orden del Día, Recolectar, Confirmar llegada · Bioinformático: Pendientes (Urgentes primero), Cargar Variantes · Gerente: Patologías, Cupones.
Textos en español rioplatense (vos), términos del LEL con mayúscula inicial como en los documentos.

## Seguridad y datos sensibles

Datos genéticos y de salud son datos sensibles (Ley 25.326): archivos sólo en MinIO privado con URLs firmadas de corta duración, `auditoria_acceso` en cada lectura de Resultado o ficha, nada de datos personales en logs ni en URLs, CORS cerrado al front, rate limit en login y código de verificación.

## Seed

Las 5 Patologías con síntomas SNOMED reales (p. ej. Fabry: acroparestesia cardinal, angioqueratomas, hipohidrosis…) y sus genes (GLA, GAA, IDUA, GBA1, SMPD1), genes de hallazgos secundarios (BRCA1, BRCA2, MLH1, LDLR, MYBPC3), 24 provincias, 10 Centros de Extracción con coordenadas reales de Argentina, feriados nacionales 2026, 3 Obras Sociales con cobertura, un usuario por rol (contraseña `Demo-2026!`) y 6 Estudios distribuidos en distintos Estados, uno Urgente. `make seed` lo recarga.

## Cómo trabajar

1. Leé las fuentes y escribí `docs/TRAZABILIDAD.md`: tabla Escenario → servicio → endpoint → vista. Mostrámela y esperá mi OK antes de codear.
2. Implementá por etapas, cada una con tests verdes antes de pasar a la siguiente: (a) infra + migración + seed, (b) auth y roles, (c) dominio + máquina de estados con tests unitarios exhaustivos, (d) servicios y API por rol, (e) integraciones mock y jobs, (f) frontend por rol.
3. Test de punta a punta obligatorio: un Estudio particular recorre todos los estados hasta FINALIZADO; otro con Obra Social rechazada y reautorizada; otro Urgente que sella un Lote con menos de 10 Muestras; una Muestra de 1,5 ml que genera re-extracción.
4. Al terminar: `make up && make seed` debe dejar el sistema navegable en `http://localhost:5173`. Actualizá `README.md` con cómo levantarlo, usuarios demo y el mapa de escenarios cubiertos.

No generes código de pasarela de pago real: el pago es simulado. No implementes el tablero de control de gerencia ni WhatsApp: el Product Owner los dejó fuera.
