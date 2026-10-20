-- =====================================================================
-- LisoGen · Sistema de Estudios Genéticos (exoma clínico, patologías lisosomales)
-- Esquema de referencia PostgreSQL 16
-- Fuente: Transcripción PO + Glosario LEL + Escenarios E1–E33 + Prototipo
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS citext;

-- ---------------------------------------------------------------------
-- 0. ENUMS (dominios cerrados que salen del LEL / Escenarios)
-- ---------------------------------------------------------------------
CREATE TYPE rol_usuario AS ENUM (
  'MEDICO_TRATANTE', 'PACIENTE', 'ADMINISTRATIVO', 'BIOINFORMATICO',
  'GERENTE_MEDICO', 'TRANSPORTISTA'
);

CREATE TYPE estado_estudio AS ENUM (
  'CREADO',                       -- E4
  'POR_PAGAR',                    -- E16 (particular o diferencia)
  'PENDIENTE_AUTORIZACION',       -- E16 (con Obra Social)
  'RECHAZADO',                    -- E18
  'PAGADO',                       -- E8
  'AUTORIZADO',                   -- E17 (equivale a pagado)
  'TURNO_SACADO',                 -- E11
  'LISTO_PARA_RETIRAR',           -- Tomar Muestra (Centro de Extracción)
  'EN_CAMINO_LAB_CENTRAL',        -- E24
  'EN_LAB_CENTRAL',               -- E25
  'EN_ESPERA_RETIRO',             -- Lote sellado
  'EN_VIAJE_COREA',               -- E20
  'EN_ANALISIS_BIOINFORMATICA',   -- E21: datos crudos cargados, sin tomar
  'EN_ANALISIS',                  -- E27: tomado por un Bioinformático
  'FINALIZADO'                    -- E28
);

CREATE TYPE tipo_estudio      AS ENUM ('EXOMA', 'REANALISIS');
CREATE TYPE tipo_sospecha     AS ENUM ('CLINICA', 'FAMILIAR');
CREATE TYPE origen_gen        AS ENUM ('API_PATOLOGIA', 'MANUAL', 'HALLAZGO_SECUNDARIO');
CREATE TYPE modalidad_pago    AS ENUM ('PARTICULAR', 'OBRA_SOCIAL', 'MIXTA');
CREATE TYPE resultado_os      AS ENUM ('AUTORIZADO', 'RECHAZADO');
CREATE TYPE estado_reaut      AS ENUM ('PENDIENTE', 'AUTORIZADA', 'RECHAZADA');
CREATE TYPE concepto_mov      AS ENUM ('PAGO_PACIENTE', 'PAGO_OBRA_SOCIAL', 'PERDIDA_POR_INASISTENCIAS');
CREATE TYPE estado_cupon      AS ENUM ('DISPONIBLE', 'ASIGNADO_MEDICO', 'ASIGNADO_PACIENTE', 'USADO', 'VENCIDO');
CREATE TYPE estado_turno      AS ENUM ('RESERVADO', 'CANCELADO', 'REALIZADO', 'AUSENTE');
CREATE TYPE estado_muestra    AS ENUM (
  'LISTO_PARA_RETIRAR', 'EN_CAMINO_LAB_CENTRAL', 'EN_LAB_CENTRAL',
  'EN_LOTE', 'EN_VIAJE_COREA', 'PROCESADA', 'DESNATURALIZADA', 'VOLUMEN_INSUFICIENTE'
);
CREATE TYPE motivo_reextraccion AS ENUM ('DESNATURALIZADA', 'VOLUMEN_INSUFICIENTE');
CREATE TYPE estado_lote       AS ENUM ('EN_FORMACION', 'EN_ESPERA_RETIRO', 'EN_VIAJE_COREA', 'RECIBIDO');
CREATE TYPE estado_parada     AS ENUM ('PENDIENTE', 'RECOGIDO');
CREATE TYPE clasif_variante   AS ENUM ('PATOGENICA', 'BENIGNA', 'SIGNIFICADO_INCIERTO');
CREATE TYPE tipo_resultado    AS ENUM ('POSITIVO', 'NEGATIVO', 'NO_CONCLUYENTE');
CREATE TYPE parentesco        AS ENUM ('PADRE', 'MADRE', 'HERMANO', 'HERMANA', 'HIJO', 'HIJA',
                                       'ABUELO', 'ABUELA', 'TIO', 'TIA', 'PRIMO', 'PRIMA', 'OTRO');
CREATE TYPE tipo_archivo      AS ENUM (
  'FAMILIOGRAMA_PDF', 'DECISION_JUDICIAL_PDF', 'ORDEN_EXTRACCION_PDF', 'CONSENTIMIENTO_PDF',
  'CSV_MINISTERIO', 'AUTORIZACION_MINISTERIO_PDF', 'DATOS_CRUDOS', 'RESULTADO_PDF', 'CUPON_PDF'
);
CREATE TYPE canal_notif       AS ENUM ('APP', 'MAIL');
CREATE TYPE servicio_externo  AS ENUM (
  'BIOINFORMATICA', 'OBRAS_SOCIALES', 'FAMILIOGRAMA', 'SNOMED', 'CUPONES', 'FEDEX',
  'MINISTERIO_SALUD', 'OPTIMIZACION_RUTAS', 'CHATBOT', 'MAIL'
);

-- ---------------------------------------------------------------------
-- 1. CATÁLOGOS
-- ---------------------------------------------------------------------
CREATE TABLE provincia (
  id      smallserial PRIMARY KEY,
  nombre  text NOT NULL UNIQUE
);

CREATE TABLE especialidad (                 -- lista estandarizada (E1)
  id      serial PRIMARY KEY,
  nombre  text NOT NULL UNIQUE
);

CREATE TABLE obra_social (
  id               serial PRIMARY KEY,
  nombre           text NOT NULL UNIQUE,
  codigo_externo   text UNIQUE             -- id en la API de obras sociales
);

CREATE TABLE snomed_concepto (              -- caché local de términos SNOMED CT
  concept_id  bigint PRIMARY KEY,
  termino     text NOT NULL
);
CREATE INDEX ix_snomed_termino ON snomed_concepto USING gin (to_tsvector('spanish', termino));

CREATE TABLE gen (
  id       serial PRIMARY KEY,
  simbolo  text NOT NULL UNIQUE             -- HGNC: GLA, GAA, IDUA, GBA1, SMPD1, BRCA1...
);

CREATE TABLE variante (                     -- caché de variantes devueltas por la API de bioinformática
  id            serial PRIMARY KEY,
  gen_id        int  NOT NULL REFERENCES gen(id),
  nomenclatura  text NOT NULL,              -- HGVS, p.ej. c.644A>G
  id_externo    text,
  UNIQUE (gen_id, nomenclatura)
);

CREATE TABLE feriado (
  fecha        date PRIMARY KEY,
  descripcion  text NOT NULL
);

-- ---------------------------------------------------------------------
-- 2. PATOLOGÍAS (E30, E31) — Fabry, Pompe, MPS 1, Gaucher, ASMD
-- ---------------------------------------------------------------------
CREATE TABLE patologia (
  id                  serial PRIMARY KEY,
  nombre              text   NOT NULL UNIQUE,
  sintoma_cardinal_id bigint NOT NULL REFERENCES snomed_concepto(concept_id),
  es_pompe            boolean NOT NULL DEFAULT false,   -- dispara la regla de Urgente
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE patologia_sintoma_secundario (
  patologia_id  int    NOT NULL REFERENCES patologia(id) ON DELETE CASCADE,
  concept_id    bigint NOT NULL REFERENCES snomed_concepto(concept_id),
  PRIMARY KEY (patologia_id, concept_id)
);

CREATE TABLE patologia_gen (                -- caché de la API de bioinformática
  patologia_id  int NOT NULL REFERENCES patologia(id) ON DELETE CASCADE,
  gen_id        int NOT NULL REFERENCES gen(id),
  PRIMARY KEY (patologia_id, gen_id)
);

-- ---------------------------------------------------------------------
-- 3. USUARIOS Y ROLES (E1, E7, E15, E26, E29)
-- ---------------------------------------------------------------------
CREATE TABLE usuario (
  id                     bigserial PRIMARY KEY,
  email                  citext      NOT NULL UNIQUE,
  password_hash          text        NOT NULL,
  rol                    rol_usuario NOT NULL,
  nombre                 text        NOT NULL,
  apellido               text        NOT NULL,
  telefono               text        NOT NULL,
  debe_cambiar_password  boolean     NOT NULL DEFAULT false,  -- Paciente: credenciales provisorias (E7)
  activo                 boolean     NOT NULL DEFAULT true,
  created_at             timestamptz NOT NULL DEFAULT now()
);

-- Médico Tratante y Gerente Médico comparten datos profesionales (E29)
CREATE TABLE profesional_medico (
  usuario_id  bigint PRIMARY KEY REFERENCES usuario(id) ON DELETE CASCADE,
  matricula   text   NOT NULL UNIQUE
);

CREATE TABLE profesional_especialidad (
  usuario_id      bigint NOT NULL REFERENCES profesional_medico(usuario_id) ON DELETE CASCADE,
  especialidad_id int    NOT NULL REFERENCES especialidad(id),
  PRIMARY KEY (usuario_id, especialidad_id)
);

CREATE TABLE transportista (                -- uno por provincia
  usuario_id    bigint   PRIMARY KEY REFERENCES usuario(id) ON DELETE CASCADE,
  provincia_id  smallint NOT NULL UNIQUE REFERENCES provincia(id)
);

CREATE TABLE dispositivo_confiable (        -- E7 excepción: equipo/red nueva → código
  id           bigserial PRIMARY KEY,
  usuario_id   bigint NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  huella       text   NOT NULL,             -- hash(user-agent + device id)
  ultima_ip    inet,
  ultimo_uso   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (usuario_id, huella)
);

CREATE TABLE codigo_verificacion (
  id           bigserial PRIMARY KEY,
  usuario_id   bigint NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  codigo_hash  text   NOT NULL,
  expira_at    timestamptz NOT NULL,
  usado_at     timestamptz,
  intentos     smallint NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------
-- 4. ARCHIVOS (todos los PDFs, CSV y datos crudos)
-- ---------------------------------------------------------------------
CREATE TABLE archivo (
  id            bigserial PRIMARY KEY,
  tipo          tipo_archivo NOT NULL,
  nombre        text   NOT NULL,
  mime          text   NOT NULL,
  tamano_bytes  bigint NOT NULL,
  storage_key   text   NOT NULL UNIQUE,     -- clave en S3/MinIO, nunca la ruta pública
  sha256        char(64) NOT NULL,
  subido_por    bigint REFERENCES usuario(id),
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 5. PACIENTE, DIAGNÓSTICO Y FAMILIOGRAMA (E2, E3)
-- ---------------------------------------------------------------------
CREATE TABLE paciente (
  id                         bigserial PRIMARY KEY,
  usuario_id                 bigint UNIQUE REFERENCES usuario(id),  -- si es menor, la cuenta es del padre
  dni                        text   NOT NULL UNIQUE,
  nombre                     text   NOT NULL,
  apellido                   text   NOT NULL,
  fecha_nacimiento           date   NOT NULL,
  telefono                   text   NOT NULL,
  email_contacto             citext NOT NULL,                       -- propio o del padre si es menor
  es_menor_al_alta           boolean NOT NULL,
  obra_social_id             int    REFERENCES obra_social(id),     -- NULL = particular
  nro_afiliado               text,
  resumen_historia_clinica   text   NOT NULL,
  familiograma_archivo_id    bigint REFERENCES archivo(id),         -- PDF de la API (opcional)
  medico_alta_id             bigint NOT NULL REFERENCES profesional_medico(usuario_id),
  created_at                 timestamptz NOT NULL DEFAULT now(),
  CHECK (obra_social_id IS NOT NULL OR nro_afiliado IS NULL)
);
CREATE INDEX ix_paciente_apellido ON paciente (lower(apellido));

CREATE TABLE paciente_sintoma (
  paciente_id  bigint NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
  concept_id   bigint NOT NULL REFERENCES snomed_concepto(concept_id),
  PRIMARY KEY (paciente_id, concept_id)
);

-- Diagnóstico presuntivo: validado contra la Patología (cardinal o 2 secundarios)
CREATE TABLE diagnostico_presuntivo (
  id            bigserial PRIMARY KEY,
  paciente_id   bigint NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
  patologia_id  int    NOT NULL REFERENCES patologia(id),
  tipo_sospecha tipo_sospecha NOT NULL,
  medico_id     bigint NOT NULL REFERENCES profesional_medico(usuario_id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (paciente_id, patologia_id)
);

CREATE TABLE familiar (
  id                      bigserial PRIMARY KEY,
  paciente_id             bigint NOT NULL REFERENCES paciente(id) ON DELETE CASCADE,
  parentesco              parentesco NOT NULL,
  nombre                  text NOT NULL,
  sintomas                text,
  patologia_diagnosticada int REFERENCES patologia(id)
);

-- ---------------------------------------------------------------------
-- 6. CUPONES (E5, E9, E32, E33)
-- ---------------------------------------------------------------------
CREATE TABLE cupon (
  id                   bigserial PRIMARY KEY,
  codigo               text     NOT NULL UNIQUE,
  qr_archivo_id        bigint   REFERENCES archivo(id),   -- NULL si el módulo sólo dio código
  descuento_pct        smallint NOT NULL CHECK (descuento_pct BETWEEN 1 AND 100),
  estado               estado_cupon NOT NULL DEFAULT 'DISPONIBLE',
  generado_por         bigint   NOT NULL REFERENCES profesional_medico(usuario_id),
  medico_asignado_id   bigint   REFERENCES profesional_medico(usuario_id),
  paciente_asignado_id bigint   REFERENCES paciente(id),
  vence_at             timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now(),
  asignado_medico_at   timestamptz,
  asignado_paciente_at timestamptz,
  usado_at             timestamptz,
  CHECK (estado <> 'ASIGNADO_MEDICO'   OR medico_asignado_id IS NOT NULL),
  CHECK (estado <> 'ASIGNADO_PACIENTE' OR paciente_asignado_id IS NOT NULL)
);

-- ---------------------------------------------------------------------
-- 7. ESTUDIO (E4, E6) — núcleo del sistema
-- ---------------------------------------------------------------------
CREATE TABLE estudio (
  id                          bigserial PRIMARY KEY,
  codigo                      text   NOT NULL UNIQUE,     -- EST-2026-000123
  paciente_id                 bigint NOT NULL REFERENCES paciente(id),
  medico_tratante_id          bigint NOT NULL REFERENCES profesional_medico(usuario_id),
  tipo                        tipo_estudio   NOT NULL DEFAULT 'EXOMA',
  estudio_origen_id           bigint REFERENCES estudio(id),  -- reanálisis: mismo exoma
  estado                      estado_estudio NOT NULL DEFAULT 'CREADO',
  evalua_hallazgos_secundarios boolean NOT NULL DEFAULT false,
  urgente                     boolean NOT NULL DEFAULT false, -- Pompe y Paciente < 4 meses
  inasistencias               smallint NOT NULL DEFAULT 0 CHECK (inasistencias BETWEEN 0 AND 5),
  bioinformatico_id           bigint REFERENCES usuario(id),  -- E27: quien lo tomó
  tomado_at                   timestamptz,
  version                     int NOT NULL DEFAULT 1,         -- lock optimista (E27)
  created_at                  timestamptz NOT NULL DEFAULT now(),
  finalizado_at               timestamptz,
  CHECK ((tipo = 'REANALISIS') = (estudio_origen_id IS NOT NULL)),
  CHECK (estado NOT IN ('EN_ANALISIS','FINALIZADO') OR bioinformatico_id IS NOT NULL)
);
CREATE INDEX ix_estudio_estado   ON estudio (estado);
CREATE INDEX ix_estudio_paciente ON estudio (paciente_id);
CREATE INDEX ix_estudio_urgente_pend ON estudio (urgente DESC, created_at)
  WHERE estado = 'EN_ANALISIS_BIOINFORMATICA';

CREATE TABLE estudio_patologia (            -- E4 excepción: más de una Patología sospechada
  estudio_id    bigint NOT NULL REFERENCES estudio(id) ON DELETE CASCADE,
  patologia_id  int    NOT NULL REFERENCES patologia(id),
  PRIMARY KEY (estudio_id, patologia_id)
);

CREATE TABLE estudio_gen (
  estudio_id    bigint NOT NULL REFERENCES estudio(id) ON DELETE CASCADE,
  gen_id        int    NOT NULL REFERENCES gen(id),
  origen        origen_gen NOT NULL,
  patologia_id  int REFERENCES patologia(id),   -- de qué Patología vino (si API)
  PRIMARY KEY (estudio_id, gen_id)
);

CREATE TABLE estudio_estado_historial (     -- trazabilidad completa del Estudio
  id              bigserial PRIMARY KEY,
  estudio_id      bigint NOT NULL REFERENCES estudio(id) ON DELETE CASCADE,
  estado_anterior estado_estudio,
  estado_nuevo    estado_estudio NOT NULL,
  usuario_id      bigint REFERENCES usuario(id),   -- NULL = proceso automático
  motivo          text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_hist_estudio ON estudio_estado_historial (estudio_id, created_at);

-- ---------------------------------------------------------------------
-- 8. PRESUPUESTO, PAGO, OBRA SOCIAL (E8, E10, E16, E17, E18)
-- ---------------------------------------------------------------------
CREATE TABLE presupuesto (
  id                    bigserial PRIMARY KEY,
  estudio_id            bigint  NOT NULL UNIQUE REFERENCES estudio(id),
  cantidad_genes        smallint NOT NULL,          -- sin hallazgos secundarios (SUPUESTO S17)
  monto_base_usd        numeric(10,2) NOT NULL,     -- 500 hasta 5 genes + 30 por gen extra
  modalidad             modalidad_pago NOT NULL,
  obra_social_id        int REFERENCES obra_social(id),
  cobertura_pct         numeric(5,2) NOT NULL DEFAULT 0 CHECK (cobertura_pct BETWEEN 0 AND 100),
  cupon_id              bigint UNIQUE REFERENCES cupon(id),
  descuento_cupon_usd   numeric(10,2) NOT NULL DEFAULT 0,
  monto_a_pagar_usd     numeric(10,2) NOT NULL,     -- a cargo del Paciente
  emitido_por           bigint NOT NULL REFERENCES usuario(id),
  emitido_at            timestamptz NOT NULL DEFAULT now(),
  CHECK (monto_a_pagar_usd >= 0),
  CHECK ((modalidad = 'PARTICULAR') = (obra_social_id IS NULL))
);

CREATE TABLE pago (                         -- simulado, un solo pago
  id               bigserial PRIMARY KEY,
  presupuesto_id   bigint NOT NULL UNIQUE REFERENCES presupuesto(id),
  monto_usd        numeric(10,2) NOT NULL CHECK (monto_usd >= 0),
  referencia_sim   text NOT NULL,
  pagado_por       bigint NOT NULL REFERENCES usuario(id),
  created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE movimiento_financiero (        -- "Registro financiero" del Administrativo
  id              bigserial PRIMARY KEY,
  estudio_id      bigint NOT NULL REFERENCES estudio(id),
  concepto        concepto_mov NOT NULL,
  monto_usd       numeric(10,2) NOT NULL,
  obra_social_id  int REFERENCES obra_social(id),
  pago_id         bigint REFERENCES pago(id),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE autorizacion_obra_social (
  id              bigserial PRIMARY KEY,
  estudio_id      bigint NOT NULL REFERENCES estudio(id),
  obra_social_id  int    NOT NULL REFERENCES obra_social(id),
  resultado       resultado_os NOT NULL,
  motivo          text,
  registrado_por  bigint NOT NULL REFERENCES usuario(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (resultado = 'AUTORIZADO' OR motivo IS NOT NULL)
);

CREATE TABLE solicitud_reautorizacion (     -- E10
  id                bigserial PRIMARY KEY,
  estudio_id        bigint NOT NULL REFERENCES estudio(id),
  rechazo_id        bigint NOT NULL REFERENCES autorizacion_obra_social(id),
  decision_judicial bigint NOT NULL REFERENCES archivo(id),
  estado            estado_reaut NOT NULL DEFAULT 'PENDIENTE',
  solicitado_por    bigint NOT NULL REFERENCES usuario(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  resuelto_at       timestamptz
);
CREATE UNIQUE INDEX ux_reaut_pendiente ON solicitud_reautorizacion (estudio_id) WHERE estado = 'PENDIENTE';

-- ---------------------------------------------------------------------
-- 9. CENTROS Y TURNOS (E11, E12)
-- ---------------------------------------------------------------------
CREATE TABLE centro_extraccion (            -- ~100 sedes tercerizadas
  id            serial PRIMARY KEY,
  nombre        text NOT NULL,
  direccion     text NOT NULL,
  provincia_id  smallint NOT NULL REFERENCES provincia(id),
  latitud       numeric(9,6) NOT NULL,
  longitud      numeric(9,6) NOT NULL,
  activo        boolean NOT NULL DEFAULT true
);

CREATE TABLE turno (
  id                  bigserial PRIMARY KEY,
  estudio_id          bigint NOT NULL REFERENCES estudio(id),
  centro_id           int    NOT NULL REFERENCES centro_extraccion(id),
  inicio              timestamptz NOT NULL,     -- bloques de 15', L–V 9 a 18, sin feriados
  estado              estado_turno NOT NULL DEFAULT 'RESERVADO',
  orden_archivo_id    bigint REFERENCES archivo(id),
  consentimiento_id   bigint REFERENCES archivo(id),
  recordatorio_at     timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  cancelado_at        timestamptz,
  CHECK (extract(minute FROM inicio AT TIME ZONE 'America/Argentina/Buenos_Aires')::int % 15 = 0)
);
-- Un Paciente por Turno en cada Centro
CREATE UNIQUE INDEX ux_turno_slot ON turno (centro_id, inicio) WHERE estado IN ('RESERVADO','REALIZADO');
-- Un único Turno activo por Estudio
CREATE UNIQUE INDEX ux_turno_activo ON turno (estudio_id) WHERE estado = 'RESERVADO';

-- ---------------------------------------------------------------------
-- 10. LOGÍSTICA: ORDEN DEL DÍA, MUESTRAS, LOTES (E19, E20, E22–E25)
-- ---------------------------------------------------------------------
CREATE TABLE orden_del_dia (
  id               bigserial PRIMARY KEY,
  transportista_id bigint NOT NULL REFERENCES transportista(usuario_id),
  fecha            date   NOT NULL,
  generada_at      timestamptz NOT NULL DEFAULT now(),
  llegada_lab_at   timestamptz,               -- E25
  UNIQUE (transportista_id, fecha)
);

CREATE TABLE orden_del_dia_parada (
  id          bigserial PRIMARY KEY,
  orden_id    bigint   NOT NULL REFERENCES orden_del_dia(id) ON DELETE CASCADE,
  centro_id   int      NOT NULL REFERENCES centro_extraccion(id),
  posicion    smallint NOT NULL,              -- devuelto por el módulo de optimización
  estado      estado_parada NOT NULL DEFAULT 'PENDIENTE',
  recogido_at timestamptz,
  UNIQUE (orden_id, posicion),
  UNIQUE (orden_id, centro_id)
);

CREATE TABLE lote (                         -- "sample set"
  id                          bigserial PRIMARY KEY,
  codigo                      text NOT NULL UNIQUE,
  estado                      estado_lote NOT NULL DEFAULT 'EN_FORMACION',
  incluye_urgente             boolean NOT NULL DEFAULT false,
  csv_ministerio_id           bigint REFERENCES archivo(id),
  autorizacion_ministerio_id  bigint REFERENCES archivo(id),
  sellado_at                  timestamptz,
  retiro_programado_at        timestamptz,
  fedex_url                   text,
  fedex_confirmado_at         timestamptz,
  recibido_at                 timestamptz,
  created_at                  timestamptz NOT NULL DEFAULT now(),
  CHECK (estado = 'EN_FORMACION' OR (sellado_at IS NOT NULL AND autorizacion_ministerio_id IS NOT NULL))
);
-- Un solo Lote en formación a la vez
CREATE UNIQUE INDEX ux_lote_en_formacion ON lote ((true)) WHERE estado = 'EN_FORMACION';

CREATE TABLE muestra (
  id               bigserial PRIMARY KEY,
  estudio_id       bigint NOT NULL REFERENCES estudio(id),
  turno_id         bigint NOT NULL UNIQUE REFERENCES turno(id),
  nro_extraccion   smallint NOT NULL DEFAULT 1,   -- >1 si hubo nueva extracción
  volumen_ml       numeric(4,2) NOT NULL CHECK (volumen_ml > 0),
  estado           estado_muestra NOT NULL DEFAULT 'LISTO_PARA_RETIRAR',
  tomada_at        timestamptz NOT NULL DEFAULT now(),
  parada_id        bigint REFERENCES orden_del_dia_parada(id),
  recolectada_at   timestamptz,
  llegada_lab_at   timestamptz,
  lote_id          bigint REFERENCES lote(id),
  UNIQUE (estudio_id, nro_extraccion)
);
CREATE INDEX ix_muestra_lote ON muestra (lote_id);

CREATE TABLE posicion_transportista (       -- tracking para "Seguir Muestra en mapa"
  id               bigserial PRIMARY KEY,
  transportista_id bigint NOT NULL REFERENCES transportista(usuario_id),
  latitud          numeric(9,6) NOT NULL,
  longitud         numeric(9,6) NOT NULL,
  registrada_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_pos_transp ON posicion_transportista (transportista_id, registrada_at DESC);

CREATE TABLE solicitud_reextraccion (       -- E22, sin costo, mismo Estudio
  id           bigserial PRIMARY KEY,
  estudio_id   bigint NOT NULL REFERENCES estudio(id),
  muestra_id   bigint NOT NULL REFERENCES muestra(id),
  motivo       motivo_reextraccion NOT NULL,
  solicitado_por bigint REFERENCES usuario(id),   -- NULL = automática (< 2 ml en E25)
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 11. BIOINFORMÁTICA Y RESULTADO (E21, E27, E28)
-- ---------------------------------------------------------------------
CREATE TABLE datos_crudos (                 -- llegan de Corea por mail, uno por Estudio
  id          bigserial PRIMARY KEY,
  estudio_id  bigint NOT NULL UNIQUE REFERENCES estudio(id),  -- el exoma original
  muestra_id  bigint NOT NULL REFERENCES muestra(id),
  archivo_id  bigint NOT NULL REFERENCES archivo(id),
  cargado_por bigint NOT NULL REFERENCES usuario(id),
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE resultado (
  id            bigserial PRIMARY KEY,
  estudio_id    bigint NOT NULL UNIQUE REFERENCES estudio(id),
  tipo          tipo_resultado NOT NULL,
  pdf_id        bigint REFERENCES archivo(id),
  confirmado_por bigint NOT NULL REFERENCES usuario(id),
  confirmado_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE resultado_variante (
  resultado_id       bigint NOT NULL REFERENCES resultado(id) ON DELETE CASCADE,
  variante_id        int    NOT NULL REFERENCES variante(id),
  clasificacion      clasif_variante NOT NULL,
  hallazgo_secundario boolean NOT NULL DEFAULT false,
  PRIMARY KEY (resultado_id, variante_id)
);

-- ---------------------------------------------------------------------
-- 12. NOTIFICACIONES, CHATBOT, AUDITORÍA DE INTEGRACIONES
-- ---------------------------------------------------------------------
CREATE TABLE notificacion (
  id          bigserial PRIMARY KEY,
  usuario_id  bigint NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  estudio_id  bigint REFERENCES estudio(id),
  canal       canal_notif NOT NULL,
  asunto      text NOT NULL,
  cuerpo      text NOT NULL,
  leida_at    timestamptz,
  enviada_at  timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_notif_no_leidas ON notificacion (usuario_id) WHERE leida_at IS NULL AND canal = 'APP';

CREATE TABLE chatbot_mensaje (              -- E14 (no deriva a una persona)
  id           bigserial PRIMARY KEY,
  usuario_id   bigint NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  pregunta     text NOT NULL,
  respuesta    text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE integracion_log (              -- toda llamada a un servicio externo
  id           bigserial PRIMARY KEY,
  servicio     servicio_externo NOT NULL,
  operacion    text NOT NULL,
  estudio_id   bigint REFERENCES estudio(id),
  request      jsonb,
  response     jsonb,
  http_status  smallint,
  ok           boolean NOT NULL,
  duracion_ms  int,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auditoria_acceso (             -- datos genéticos = datos sensibles (Ley 25.326)
  id          bigserial PRIMARY KEY,
  usuario_id  bigint REFERENCES usuario(id),
  accion      text   NOT NULL,              -- VER_RESULTADO, DESCARGAR_PDF, VER_FICHA...
  entidad     text   NOT NULL,
  entidad_id  bigint NOT NULL,
  ip          inet,
  created_at  timestamptz NOT NULL DEFAULT now()
);
