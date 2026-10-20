"""Schemas de entrada/salida de los casos de uso por rol."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import EmailStr, Field, StringConstraints

from app.domain.enums import (
    ClasifVariante,
    ConceptoMov,
    EstadoCupon,
    EstadoLote,
    EstadoMuestra,
    EstadoParada,
    EstadoReaut,
    ModalidadPago,
    Parentesco,
    TipoSospecha,
)
from app.schemas.comun import CentroSalida, Concepto, Esquema, EstudioResumen, GenEstudio

SimboloGen = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9-]{2,15}$")
]
TextoCorto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

# --- Médico Tratante (E2–E6) ------------------------------------------------------------------


class FamiliarEntrada(Esquema):
    parentesco: Parentesco
    nombre: TextoCorto
    sintomas: str | None = Field(default=None, max_length=500)
    patologia_diagnosticada_id: int | None = None


class DiagnosticoEntrada(Esquema):
    patologia_id: int
    tipo_sospecha: TipoSospecha


class PacienteAlta(Esquema):
    dni: Annotated[str, StringConstraints(pattern=r"^\d{7,8}$")]
    nombre: TextoCorto
    apellido: TextoCorto
    fecha_nacimiento: date
    telefono: str = Field(min_length=6, max_length=30, pattern=r"^[0-9 +()-]+$")
    email: EmailStr = Field(description="Mail del Paciente, o de un padre o madre si es menor de edad.")
    obra_social_id: int | None = None
    nro_afiliado: str | None = Field(default=None, max_length=40)
    resumen_historia_clinica: str = Field(min_length=1, max_length=4000)
    sintomas: list[int] = Field(min_length=1, description="concept_id SNOMED CT")
    diagnosticos: list[DiagnosticoEntrada] = Field(min_length=1)
    familiares: list[FamiliarEntrada] = Field(default_factory=list)


class FamiliogramaEntrada(Esquema):
    familiares: list[FamiliarEntrada] = Field(min_length=1)


class BuscarEntrada(Esquema):
    texto: str = Field(default="", max_length=100)


class PacienteResumen(Esquema):
    id: int
    dni: str
    nombre_completo: str
    fecha_nacimiento: date
    obra_social: str | None
    cantidad_estudios: int


class DiagnosticoSalida(Esquema):
    patologia_id: int
    patologia: str
    tipo_sospecha: TipoSospecha


class FamiliarSalida(Esquema):
    parentesco: Parentesco
    nombre: str
    sintomas: str | None
    patologia_diagnosticada: str | None


class PacienteFicha(Esquema):
    id: int
    dni: str
    nombre: str
    apellido: str
    fecha_nacimiento: date
    telefono: str
    email_contacto: str
    es_menor_al_alta: bool
    obra_social: str | None
    nro_afiliado: str | None
    resumen_historia_clinica: str
    sintomas: list[Concepto]
    diagnosticos: list[DiagnosticoSalida]
    familiares: list[FamiliarSalida]
    familiograma_url: str | None
    estudios: list[EstudioResumen]


class EstudioAlta(Esquema):
    paciente_id: int
    patologia_ids: list[int] = Field(min_length=1)
    genes_manuales: list[SimboloGen] = Field(default_factory=list, max_length=50)
    evalua_hallazgos_secundarios: bool = False


class ReanalisisEntrada(Esquema):
    patologia_ids: list[int] = Field(default_factory=list)
    genes_manuales: list[SimboloGen] = Field(default_factory=list, max_length=50)


class GenesSugeridos(Esquema):
    patologia_id: int
    patologia: str
    genes: list[str]
    hallazgos_secundarios: list[str]


class PatologiaSalida(Esquema):
    id: int
    nombre: str
    es_pompe: bool
    sintoma_cardinal: Concepto
    secundarios: list[Concepto]
    genes: list[str]


class CuponSalida(Esquema):
    id: int
    codigo: str
    descuento_pct: int
    estado: EstadoCupon
    medico: str | None
    paciente: str | None
    vence_at: datetime | None
    qr_url: str | None


class AsignarCuponEntrada(Esquema):
    paciente_id: int


# --- Paciente (E7–E14) ------------------------------------------------------------------------


class PagoSalida(Esquema):
    referencia: str
    monto_usd: Decimal


class TurnoEntrada(Esquema):
    estudio_id: int
    centro_id: int
    inicio: datetime


class Slot(Esquema):
    inicio: datetime
    libre: bool


class AgendaDia(Esquema):
    fecha: date
    habil: bool
    slots: list[Slot]


class ChatEntrada(Esquema):
    pregunta: str = Field(min_length=1, max_length=500)


class ChatMensajeSalida(Esquema):
    id: int
    pregunta: str
    respuesta: str | None
    created_at: datetime


# --- Administrativo (E16–E22) -----------------------------------------------------------------


class PresupuestoPrevio(Esquema):
    cantidad_genes: int
    monto_base_usd: Decimal
    modalidad: ModalidadPago
    obra_social: str | None
    cobertura_pct: Decimal
    monto_obra_social_usd: Decimal
    monto_a_pagar_usd: Decimal


class RechazoEntrada(Esquema):
    motivo: str = Field(min_length=3, max_length=500)


class ReautorizacionSalida(Esquema):
    id: int
    estudio_id: int
    estudio_codigo: str
    paciente: str
    estado: EstadoReaut
    created_at: datetime
    decision_judicial_url: str | None


class MuestraSalida(Esquema):
    id: int
    estudio_id: int
    estudio_codigo: str
    paciente: str
    nro_extraccion: int
    volumen_ml: Decimal
    estado: EstadoMuestra
    centro: str
    tomada_at: datetime
    lote_codigo: str | None


class UbicacionMuestra(Esquema):
    muestra_id: int
    estado: EstadoMuestra
    latitud: Decimal
    longitud: Decimal
    descripcion: str
    transportista: str | None
    actualizada_at: datetime | None


class LoteSalida(Esquema):
    id: int
    codigo: str
    estado: EstadoLote
    incluye_urgente: bool
    cantidad_muestras: int
    estudios: list[str]
    sellado_at: datetime | None
    retiro_programado_at: datetime | None
    fedex_confirmado_at: datetime | None
    csv_url: str | None
    autorizacion_url: str | None


class RetiroEntrada(Esquema):
    fecha_hora: datetime


class ReextraccionEntrada(Esquema):
    motivo: Literal["DESNATURALIZADA"] = "DESNATURALIZADA"
    detalle: str | None = Field(default=None, max_length=500)


class MovimientoSalida(Esquema):
    id: int
    created_at: datetime
    concepto: ConceptoMov
    monto_usd: Decimal
    estudio_codigo: str
    obra_social: str | None


class RegistroFinanciero(Esquema):
    movimientos: list[MovimientoSalida]
    total_pacientes_usd: Decimal
    total_obras_sociales_usd: Decimal
    total_perdidas_usd: Decimal


# --- Transportista (E23–E25) ------------------------------------------------------------------


class ParadaSalida(Esquema):
    id: int
    posicion: int
    estado: EstadoParada
    centro: CentroSalida
    muestras_listas: int
    recogido_at: datetime | None


class OrdenDelDiaSalida(Esquema):
    id: int
    fecha: date
    provincia: str
    paradas: list[ParadaSalida]
    muestras_en_camino: int
    llegada_lab_at: datetime | None


class PosicionEntrada(Esquema):
    latitud: Decimal = Field(ge=-90, le=90)
    longitud: Decimal = Field(ge=-180, le=180)


class LlegadaSalida(Esquema):
    recibidas: int
    volumen_insuficiente: list[str]
    lotes_sellados: list[str]
    lote_en_formacion: str | None


# --- Bioinformático (E27, E28) ----------------------------------------------------------------


class TomarEntrada(Esquema):
    version: int


class VarianteCatalogo(Esquema):
    nomenclatura: str
    id_externo: str | None


class VarianteEntrada(Esquema):
    gen: SimboloGen
    nomenclatura: str = Field(min_length=3, max_length=120)
    clasificacion: ClasifVariante


class ResultadoEntrada(Esquema):
    variantes: list[VarianteEntrada] = Field(default_factory=list, max_length=100)


class EstudioAnalisis(EstudioResumen):
    genes: list[GenEstudio]
    estudio_origen_codigo: str | None
    datos_crudos_url: str | None
    tomado_por_mi: bool


# --- Gerente Médico (E30–E33) -----------------------------------------------------------------


class PatologiaEntrada(Esquema):
    nombre: TextoCorto
    sintoma_cardinal_id: int
    secundarios_ids: list[int] = Field(min_length=2)
    es_pompe: bool = False


class GenerarCuponesEntrada(Esquema):
    descuento_pct: int = Field(ge=1, le=100)
    cantidad: int = Field(ge=1, le=100)
    vence_at: datetime | None = None


class AsignarCuponesEntrada(Esquema):
    cupon_ids: list[int] = Field(min_length=1)
    medico_id: int


class MedicoSalida(Esquema):
    id: int
    nombre_completo: str
    matricula: str
    cupones_disponibles: int
