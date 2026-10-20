# DECISIONES

Registro de decisiones de diseño, contradicciones entre fuentes y `SUPUESTO`s.
Regla de precedencia: **Escenarios + `schema.sql`** > Glosario LEL > prototipo. Todo `SUPUESTO` está marcado así en el código con su número (`SUPUESTO S<n>`).

## 1. Cambios al contrato `schema.sql`

### D1 · Migración `0002_pago_anulable` (aprobado)
- **Problema:** E11 dice que con 5 inasistencias el Paciente pierde el pago y el Estudio vuelve a Por Pagar, así que tiene que poder pagar otra vez. `pago.presupuesto_id` es `UNIQUE` y `presupuesto.estudio_id` también, entonces no se puede registrar un segundo pago.
- **Cambio:** `ALTER TABLE pago ADD COLUMN anulado_at timestamptz`; se elimina el `UNIQUE (presupuesto_id)` y se reemplaza por `CREATE UNIQUE INDEX ux_pago_vigente ON pago (presupuesto_id) WHERE anulado_at IS NULL`.
- La migración `0001_initial` sigue siendo `schema.sql` 1:1 (hay un test que lo compara con `pg_dump`).

## 2. Contradicciones entre fuentes

| # | LEL / prototipo | Escenarios / schema | Se adopta |
|---|---|---|---|
| C1 | Familiograma es "requisito previo a Sacar Turno" | E2/E3: es opcional (si el Paciente no brinda información, la sección queda vacía) | Opcional |
| C2 | "Cargar Resultado" lo ejecuta el Administrativo | E28: el Bioinformático confirma el Resultado | Bioinformático |
| C3 | Desnaturalizada se detecta "durante Analizar" | E21/E22: el Administrativo la detecta al recibir los datos de Corea | E21/E22 |
| C4 | Estados de Muestra: tomada, lista, recolectada, enviada, desnaturalizada | `estado_muestra` del schema | schema |
| C5 | Estados de Lote: en formación, sellado, enviado, recibido | `estado_lote`: EN_FORMACION, EN_ESPERA_RETIRO, EN_VIAJE_COREA, RECIBIDO | schema |
| C6 | "Tomar Muestra" la hace el Extraccionista | Ningún Escenario la cubre y el Extraccionista no es rol | Servicio `extracciones.registrar_extraccion` **sin endpoint**: el endpoint se implementa más adelante (indicación del PO). Seed y tests e2e llaman al servicio |

## 3. SUPUESTOs

- **S1 · Cobertura parcial (modalidad MIXTA).** Al registrar la Autorización: si `monto_a_pagar_usd > 0`, el Estudio pasa de PENDIENTE_AUTORIZACION a POR_PAGAR y el Paciente paga la diferencia (→ PAGADO). Con cobertura del 100% el Estudio pasa a AUTORIZADO. En los dos casos se registra el movimiento `PAGO_OBRA_SOCIAL` por la parte cubierta.
- **S2 · Reautorización (E10).** Cuando el Paciente sube el PDF judicial, el Estudio pasa de RECHAZADO a PENDIENTE_AUTORIZACION y queda una `solicitud_reautorizacion` PENDIENTE. El Administrativo vuelve a registrar Autorización o Rechazo (E17/E18) y eso resuelve la solicitud (AUTORIZADA/RECHAZADA).
- **S3 · Reanálisis (E6).** Sólo se puede pedir sobre un Estudio EXOMA en estado FINALIZADO. El nuevo Estudio tipo REANALISIS se crea en CREADO y, en la misma transacción, pasa a EN_ANALISIS_BIOINFORMATICA reutilizando los `datos_crudos` del Estudio origen. No genera Presupuesto, Turno ni Lote, porque los Escenarios no mencionan cobro.
- **S4 · Registro de profesionales (E1/E15/E26/E29).** Es autorregistro con acceso inmediato, como indican los Escenarios. Médico Tratante y Gerente Médico cargan además matrícula y especialidades. *Riesgo:* cualquiera puede registrarse como Administrativo o Gerente. Queda documentado para que el PO decida si se agrega la aprobación del administrador general (E29, excepción).
- **S5 · Resultado.** Sin Variantes → NEGATIVO. Al menos una PATOGENICA → POSITIVO. Sólo SIGNIFICADO_INCIERTO (con o sin benignas) → NO_CONCLUYENTE. Sólo benignas → NEGATIVO. Las Variantes de hallazgos secundarios no definen el tipo de Resultado.
- **S6 · Cupón inválido (E9).** Se rechaza con 422 `CUPON_INVALIDO` y el Presupuesto mantiene el precio original. El pago sigue habilitado.
- **S7 · Paciente menor de edad (E2).** `email_contacto` es el mail del padre o la madre, y la cuenta (`usuario`) se crea con ese mail. *Limitación:* `usuario.email` es UNIQUE, así que un padre o una madre con dos hijos en el sistema necesita un mail distinto por hijo.
- **S8 · Transportista.** Hay uno por provincia (`transportista.provincia_id` UNIQUE). La Orden del Día se genera una vez por día y no se modifica.
- **S9 · Pérdida por inasistencias.** Al llegar a 5 inasistencias: el pago vigente se anula (`anulado_at`), se registra `PERDIDA_POR_INASISTENCIAS` por el monto perdido, `inasistencias` vuelve a 0 y el Estudio pasa a POR_PAGAR. El Paciente debe volver a pagar `monto_a_pagar_usd`. Si ese monto es 0 (cobertura total), el "pago" de 0 USD reactiva el Estudio.
- **S10 · Desnaturalizada (E22).** El Administrativo la registra sobre un Estudio en EN_VIAJE_COREA, antes de cargar los datos crudos. La Muestra queda DESNATURALIZADA y el Estudio vuelve a PAGADO/AUTORIZADO sin costo.
- **S11 · Estado al que se vuelve.** Al cancelar un Turno o pedir una re-extracción, el Estudio vuelve al último estado PAGADO o AUTORIZADO registrado en `estudio_estado_historial`.
- **S12 · Inasistencia.** Al cierre de jornada (18:30 hora Argentina), los Turnos RESERVADO cuyo inicio ya pasó y que no tienen Muestra pasan a AUSENTE. El Estudio vuelve a PAGADO/AUTORIZADO para que el Paciente pueda sacar otro Turno (E11, excepción).
- **S13 · Urgente.** Se calcula al dar de alta el Estudio: alguna Patología `es_pompe` y edad del Paciente < 4 meses en esa fecha. No se recalcula después.
- **S14 · Sello del Lote.** Se evalúa al confirmar cada llegada (E25): si el Lote EN_FORMACION llega a 10 Muestras o incluye un Urgente, se sella. Si en una misma llegada hay más Muestras de las que entran, el excedente abre el Lote siguiente.
- **S15 · Retiro de FedEx (E20).** El día y hora del retiro tienen que caer L–V entre 9 y 18 (hora Argentina) y no ser feriado. Al confirmar FedEx (webhook mock), el Lote y sus Muestras pasan a EN_VIAJE_COREA.
- **S16 · Recordatorio de Turno.** `turno.recordatorio_at` = día hábil anterior a las 09:00. Un job horario envía los recordatorios vencidos que todavía no se mandaron.

## 4. Decisiones técnicas

- **T1 · Refresh tokens sin estado.** El schema no tiene tabla de sesiones, así que el refresh es un JWT firmado con `typ=refresh` y no se puede revocar antes de que expire (7 días). El access dura 15 minutos.
- **T2 · Rate limit en memoria** (ventana deslizante por IP + email) para `/auth/login` y `/auth/verificar`. Con más de una réplica de la API haría falta Redis.
- **T3 · Huella de dispositivo.** `sha256(user-agent + X-Device-Id)`; el front genera y persiste el `X-Device-Id`. El cambio de red no se detecta: la IP se guarda en `ultima_ip` pero no dispara el código, para no molestar a usuarios con IP dinámica.
- **T4 · Un único punto que escribe `estudio.estado`:** `app/services/transiciones.py::transicionar`. Un test recorre el código buscando otras asignaciones.
- **T5 · Montos** con `Decimal` y redondeo `ROUND_HALF_UP` a 2 decimales.
- **T6 · Integraciones:** `INTEGRACIONES_MODO=mock` (por defecto). El `integracion_log` guarda request y response sin datos personales: sólo ids, códigos de gen y montos.
- **T7 · Log de integraciones en la misma transacción.** `integracion_log` se escribe en la sesión del caso de uso: si la operación de negocio falla y se revierte, también se revierte el log de esa llamada.
- **T8 · Imagen de MinIO.** MinIO dejó de publicar imágenes oficiales (`minio/minio` ya no está en Docker Hub ni en Quay). `docker-compose.yml` usa `pgsty/minio:RELEASE.2026-08-04T00-00-00Z`, un build comunitario del mismo código con el mismo entrypoint y las mismas variables (`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`). El bucket privado lo crea la API en el primer uso.
- **T9 · Seed por etapas.** En la etapa 1 el seed carga los catálogos (24 provincias, 12 especialidades, 3 Obras Sociales, 34 conceptos SNOMED verificados, 5 Patologías con sus genes, 10 genes, 16 feriados 2026, 10 Centros), un usuario por rol y el Paciente demo. Los 6 Estudios de ejemplo se suman en la etapa 4 recorriendo los servicios reales, para que su historial de Estados sea consistente.
- **T10 · Feriados 2026.** Sólo feriados nacionales (Ley 27.399), con los trasladables movidos al lunes. No se incluyen días no laborables ni "puentes" turísticos.
- **T11 · `downgrade` de 0001.** Borra tablas, tipos ENUM y la extensión `citext` creados por `schema.sql`, sin tocar `alembic_version`.
- **T12 · Transacción por request antes de responder.** La sesión se inyecta con `Depends(get_session, scope="function")`: el commit ocurre antes de enviar la respuesta, así un fallo de commit llega al cliente como error. Los mails con secretos (credenciales, código de verificación) se envían después del commit y su `integracion_log` se confirma en una segunda transacción.
- **T13 · Errores HTTP.** Todo error de negocio responde `{code, message}` en español: 401 sin sesión o sesión vencida, 403 rol no habilitado, 404, 409 conflicto de estado, 422 datos o regla inválidos y 429 demasiados intentos. Los errores de validación de Pydantic responden 422 `DATOS_INVALIDOS` y suman `campos`.
- **T14 · Integraciones en la etapa 2.** El ingreso necesita el puerto de mail, así que el paquete `integrations/` (puertos, mocks, log) entra en la etapa 2. La etapa 5 agrega los jobs y los tests de cada adaptador mock.
