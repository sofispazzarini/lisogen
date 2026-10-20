from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    ClasifVariante,
    EstadoEstudio,
    EstadoTurno,
    ModalidadPago,
    TipoEstudio,
    TipoResultado,
)


class Esquema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Error(Esquema):
    code: str = Field(examples=["TRANSICION_INVALIDA"])
    message: str = Field(examples=["El Estudio no puede pasar de Creado a Pagado."])


class Ok(Esquema):
    ok: bool = True


class Opcion(Esquema):
    id: int
    nombre: str


class Concepto(Esquema):
    concept_id: int
    termino: str


class PersonaResumen(Esquema):
    id: int
    nombre_completo: str


class EstudioResumen(Esquema):
    id: int
    codigo: str
    tipo: TipoEstudio
    estado: EstadoEstudio
    estado_etiqueta: str
    urgente: bool
    created_at: datetime
    paciente: PersonaResumen
    medico_tratante: PersonaResumen
    patologias: list[str]
    version: int


class HistorialItem(Esquema):
    estado_anterior: EstadoEstudio | None
    estado_nuevo: EstadoEstudio
    estado_etiqueta: str
    motivo: str | None
    actor: str
    created_at: datetime


class GenEstudio(Esquema):
    simbolo: str
    origen: str
    patologia: str | None


class PresupuestoSalida(Esquema):
    id: int
    cantidad_genes: int
    monto_base_usd: Decimal
    modalidad: ModalidadPago
    obra_social: str | None
    cobertura_pct: Decimal
    descuento_cupon_usd: Decimal
    cupon_codigo: str | None
    monto_a_pagar_usd: Decimal
    monto_obra_social_usd: Decimal
    pagado: bool
    emitido_at: datetime


class TurnoSalida(Esquema):
    id: int
    estado: EstadoTurno
    inicio: datetime
    centro_id: int
    centro_nombre: str
    centro_direccion: str
    orden_extraccion_url: str | None
    consentimiento_url: str | None


class VarianteResultado(Esquema):
    gen: str
    nomenclatura: str
    clasificacion: ClasifVariante
    hallazgo_secundario: bool


class ResultadoSalida(Esquema):
    tipo: TipoResultado
    confirmado_at: datetime
    variantes: list[VarianteResultado]
    pdf_url: str | None


class EstudioDetalle(EstudioResumen):
    evalua_hallazgos_secundarios: bool
    estudio_origen_codigo: str | None
    inasistencias: int
    genes: list[GenEstudio]
    historial: list[HistorialItem]
    presupuesto: PresupuestoSalida | None
    turno: TurnoSalida | None
    tiene_resultado: bool
    rechazo_motivo: str | None
    reautorizacion_pendiente: bool


class Aviso(Esquema):
    id: int
    asunto: str
    cuerpo: str
    estudio_id: int | None
    leida: bool
    created_at: datetime


class CentroSalida(Esquema):
    id: int
    nombre: str
    direccion: str
    provincia: str
    latitud: Decimal
    longitud: Decimal
