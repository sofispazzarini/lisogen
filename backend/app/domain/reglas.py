"""Reglas de negocio puras (sin FastAPI ni SQLAlchemy)."""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Final
from zoneinfo import ZoneInfo

from app.domain.enums import ClasifVariante, EstadoCupon, ModalidadPago, TipoResultado
from app.domain.errores import Conflicto, ErrorNegocio

TZ_AR: Final = ZoneInfo("America/Argentina/Buenos_Aires")

# ---------------------------------------------------------------------------
# Validar Diagnóstico (E2)
# ---------------------------------------------------------------------------


def validar_diagnostico(
    sintomas_paciente: Collection[int], sintoma_cardinal: int, sintomas_secundarios: Collection[int]
) -> bool:
    """El Paciente debe presentar el síntoma cardinal de la Patología o al menos dos secundarios."""
    presentes = set(sintomas_paciente)
    if sintoma_cardinal in presentes:
        return True
    return len(presentes & set(sintomas_secundarios)) >= 2


# ---------------------------------------------------------------------------
# Urgente: Pompe y Paciente menor de 4 meses (SUPUESTO S13: se calcula al dar de alta el Estudio)
# ---------------------------------------------------------------------------


def sumar_meses(d: date, meses: int) -> date:
    mes = d.month - 1 + meses
    anio = d.year + mes // 12
    mes = mes % 12 + 1
    dias_mes = [31, 29 if _bisiesto(anio) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1]
    return date(anio, mes, min(d.day, dias_mes))


def _bisiesto(anio: int) -> bool:
    return anio % 4 == 0 and (anio % 100 != 0 or anio % 400 == 0)


def es_urgente(alguna_patologia_es_pompe: bool, fecha_nacimiento: date, fecha_referencia: date) -> bool:
    return alguna_patologia_es_pompe and fecha_referencia < sumar_meses(fecha_nacimiento, 4)


def es_menor_de_edad(fecha_nacimiento: date, hoy: date) -> bool:
    cumple_18 = sumar_meses(fecha_nacimiento, 18 * 12)
    return hoy < cumple_18


# ---------------------------------------------------------------------------
# Presupuesto (E16)
# ---------------------------------------------------------------------------

PRECIO_BASE_USD: Final = Decimal("500.00")
GENES_INCLUIDOS: Final = 5
PRECIO_GEN_ADICIONAL_USD: Final = Decimal("30.00")
CENTAVO: Final = Decimal("0.01")
CIEN: Final = Decimal(100)


def _redondear(monto: Decimal) -> Decimal:
    return monto.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def monto_base(cantidad_genes: int) -> Decimal:
    """USD 500 hasta 5 genes + USD 30 por gen adicional. No incluye hallazgos secundarios (SUPUESTO S17)."""
    if cantidad_genes < 1:
        raise ErrorNegocio("ESTUDIO_SIN_GENES", "El Estudio no tiene genes para presupuestar.")
    adicionales = max(0, cantidad_genes - GENES_INCLUIDOS)
    return _redondear(PRECIO_BASE_USD + PRECIO_GEN_ADICIONAL_USD * adicionales)


@dataclass(frozen=True)
class CalculoPresupuesto:
    cantidad_genes: int
    monto_base_usd: Decimal
    modalidad: ModalidadPago
    cobertura_pct: Decimal
    monto_paciente_sin_cupon_usd: Decimal
    descuento_cupon_usd: Decimal
    monto_a_pagar_usd: Decimal

    @property
    def monto_obra_social_usd(self) -> Decimal:
        return self.monto_base_usd - self.monto_paciente_sin_cupon_usd


def calcular_presupuesto(
    cantidad_genes: int,
    tiene_obra_social: bool,
    cobertura_pct: Decimal = Decimal(0),
    descuento_cupon_pct: int | None = None,
) -> CalculoPresupuesto:
    """Calcula el Presupuesto. La cobertura viene de la API de obras sociales; el Cupón aplica un %
    sobre lo que paga el Paciente. SUPUESTO S18: cobertura 0% equivale a pago particular."""
    if not Decimal(0) <= cobertura_pct <= CIEN:
        raise ErrorNegocio("COBERTURA_INVALIDA", "La cobertura de la Obra Social debe estar entre 0 y 100%.")
    base = monto_base(cantidad_genes)
    if not tiene_obra_social or cobertura_pct == 0:
        modalidad, cobertura = ModalidadPago.PARTICULAR, Decimal(0)
    elif cobertura_pct == CIEN:
        modalidad, cobertura = ModalidadPago.OBRA_SOCIAL, CIEN
    else:
        modalidad, cobertura = ModalidadPago.MIXTA, cobertura_pct
    paciente = _redondear(base * (CIEN - cobertura) / CIEN)
    descuento = Decimal("0.00")
    if descuento_cupon_pct is not None:
        if not 1 <= descuento_cupon_pct <= 100:
            raise ErrorNegocio("CUPON_INVALIDO", "El descuento del Cupón debe estar entre 1 y 100%.")
        descuento = _redondear(paciente * descuento_cupon_pct / CIEN)
    return CalculoPresupuesto(
        cantidad_genes=cantidad_genes,
        monto_base_usd=base,
        modalidad=modalidad,
        cobertura_pct=cobertura.quantize(CENTAVO),
        monto_paciente_sin_cupon_usd=paciente,
        descuento_cupon_usd=descuento,
        monto_a_pagar_usd=paciente - descuento,
    )


# ---------------------------------------------------------------------------
# Agenda de Turnos (E11): bloques de 15', L–V 9 a 18 hora Argentina, sin feriados
# ---------------------------------------------------------------------------

DURACION_TURNO: Final = timedelta(minutes=15)
APERTURA: Final = time(9, 0)
CIERRE: Final = time(18, 0)
VENTANA_RESERVA_DIAS: Final = 30  # SUPUESTO S19


def es_dia_habil(dia: date, feriados: Collection[date]) -> bool:
    return dia.weekday() < 5 and dia not in feriados


def slots_del_dia(dia: date, feriados: Collection[date]) -> list[datetime]:
    """Inicios de Turno (aware, UTC) de un día. Vacío si es fin de semana o feriado."""
    if not es_dia_habil(dia, feriados):
        return []
    inicio = datetime.combine(dia, APERTURA, tzinfo=TZ_AR)
    fin = datetime.combine(dia, CIERRE, tzinfo=TZ_AR)
    slots: list[datetime] = []
    while inicio + DURACION_TURNO <= fin:
        slots.append(inicio.astimezone(UTC))
        inicio += DURACION_TURNO
    return slots


def validar_slot(inicio: datetime, feriados: Collection[date], ahora: datetime) -> None:
    if inicio.tzinfo is None:
        raise ErrorNegocio("TURNO_INVALIDO", "El horario del Turno debe incluir zona horaria.")
    local = inicio.astimezone(TZ_AR)
    if inicio.astimezone(UTC) not in slots_del_dia(local.date(), feriados):
        raise ErrorNegocio(
            "TURNO_FUERA_DE_AGENDA",
            "Los Turnos son de 15 minutos, de lunes a viernes de 9 a 18, sin feriados.",
        )
    if inicio <= ahora:
        raise ErrorNegocio("TURNO_EN_EL_PASADO", "El Turno elegido ya pasó.")
    if local.date() > ahora.astimezone(TZ_AR).date() + timedelta(days=VENTANA_RESERVA_DIAS):
        raise ErrorNegocio(
            "TURNO_FUERA_DE_VENTANA",
            f"Sólo podés reservar Turnos en los próximos {VENTANA_RESERVA_DIAS} días.",
        )


def momento_recordatorio(inicio: datetime) -> datetime:
    """SUPUESTO S16: el recordatorio sale el día anterior al Turno a las 9:00 hora Argentina."""
    dia_anterior = inicio.astimezone(TZ_AR).date() - timedelta(days=1)
    return datetime.combine(dia_anterior, APERTURA, tzinfo=TZ_AR).astimezone(UTC)


def validar_horario_retiro(momento: datetime, feriados: Collection[date], ahora: datetime) -> None:
    """E20 / SUPUESTO S15: el retiro de FedEx es L–V de 9 a 18, en día hábil y a futuro."""
    if momento.tzinfo is None:
        raise ErrorNegocio("RETIRO_INVALIDO", "El horario del retiro debe incluir zona horaria.")
    local = momento.astimezone(TZ_AR)
    if not es_dia_habil(local.date(), feriados) or not APERTURA <= local.time() <= CIERRE:
        raise ErrorNegocio(
            "RETIRO_FUERA_DE_HORARIO", "FedEx retira de lunes a viernes de 9 a 18, sin feriados."
        )
    if momento <= ahora:
        raise ErrorNegocio("RETIRO_EN_EL_PASADO", "El horario del retiro ya pasó.")


# ---------------------------------------------------------------------------
# Inasistencias (E11)
# ---------------------------------------------------------------------------

MAX_INASISTENCIAS: Final = 5


def pierde_pago(inasistencias_previas: int) -> bool:
    """Con la quinta inasistencia el Paciente pierde el pago y el Estudio vuelve a Por Pagar."""
    return inasistencias_previas + 1 >= MAX_INASISTENCIAS


# ---------------------------------------------------------------------------
# Lotes (E25)
# ---------------------------------------------------------------------------

CAPACIDAD_LOTE: Final = 10
VOLUMEN_MINIMO_ML: Final = Decimal("2")


def volumen_suficiente(volumen_ml: Decimal) -> bool:
    return volumen_ml >= VOLUMEN_MINIMO_ML


@dataclass(frozen=True)
class MuestraParaLote:
    id: int
    urgente: bool


@dataclass(frozen=True)
class GrupoLote:
    """Muestras que entran a un Lote. `continua_actual` = se suman al Lote EN_FORMACION existente."""

    muestras: tuple[int, ...]
    sellar: bool
    incluye_urgente: bool
    continua_actual: bool


def armar_lotes(
    cantidad_actual: int, actual_incluye_urgente: bool, nuevas: Sequence[MuestraParaLote]
) -> list[GrupoLote]:
    """Reparte las Muestras que llegan entre el Lote en formación y los siguientes.

    Un Lote se sella al llegar a 10 Muestras o al incluir un Urgente (SUPUESTO S14). Las Muestras que no
    entran pasan al Lote siguiente. Las no urgentes se ubican primero para que el Lote del Urgente salga
    lo más completo posible.
    """
    if cantidad_actual >= CAPACIDAD_LOTE:
        raise Conflicto("LOTE_COMPLETO", "El Lote en formación ya tiene 10 Muestras.")
    ordenadas = sorted(nuevas, key=lambda m: m.urgente)
    grupos: list[GrupoLote] = []
    actual: list[int] = []
    cantidad, urgente, continua = cantidad_actual, actual_incluye_urgente, True
    for m in ordenadas:
        actual.append(m.id)
        cantidad += 1
        urgente = urgente or m.urgente
        if cantidad >= CAPACIDAD_LOTE or urgente:
            grupos.append(GrupoLote(tuple(actual), True, urgente, continua))
            actual, cantidad, urgente, continua = [], 0, False, False
    if actual:
        grupos.append(GrupoLote(tuple(actual), False, urgente, continua))
    return grupos


def debe_sellar(cantidad: int, incluye_urgente: bool) -> bool:
    return cantidad >= CAPACIDAD_LOTE or (incluye_urgente and cantidad > 0)


# ---------------------------------------------------------------------------
# Resultado (E28) — SUPUESTO S5
# ---------------------------------------------------------------------------


def tipo_resultado(clasificaciones: Iterable[ClasifVariante]) -> TipoResultado:
    """Sin Variantes → NEGATIVO; alguna PATOGENICA → POSITIVO; sólo inciertas → NO_CONCLUYENTE."""
    c = set(clasificaciones)
    if ClasifVariante.PATOGENICA in c:
        return TipoResultado.POSITIVO
    if ClasifVariante.SIGNIFICADO_INCIERTO in c:
        return TipoResultado.NO_CONCLUYENTE
    return TipoResultado.NEGATIVO


# ---------------------------------------------------------------------------
# Cupón: DISPONIBLE → ASIGNADO_MEDICO → ASIGNADO_PACIENTE → USADO (uso único)
# ---------------------------------------------------------------------------

_TRANSICIONES_CUPON: Final = {
    EstadoCupon.DISPONIBLE: EstadoCupon.ASIGNADO_MEDICO,
    EstadoCupon.ASIGNADO_MEDICO: EstadoCupon.ASIGNADO_PACIENTE,
    EstadoCupon.ASIGNADO_PACIENTE: EstadoCupon.USADO,
}


def cupon_vencido(vence_at: datetime | None, ahora: datetime) -> bool:
    return vence_at is not None and vence_at <= ahora


def avanzar_cupon(
    estado: EstadoCupon, destino: EstadoCupon, vence_at: datetime | None, ahora: datetime
) -> None:
    if cupon_vencido(vence_at, ahora):
        raise Conflicto("CUPON_VENCIDO", "El Cupón está vencido.")
    if _TRANSICIONES_CUPON.get(estado) != destino:
        if estado == EstadoCupon.USADO:
            raise Conflicto("CUPON_USADO", "El Cupón ya fue usado.")
        raise Conflicto("CUPON_ESTADO_INVALIDO", "El Cupón no está disponible para esta operación.")
