from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.enums import ClasifVariante as C
from app.domain.enums import EstadoCupon as EC
from app.domain.enums import ModalidadPago as M
from app.domain.enums import TipoResultado as TR
from app.domain.errores import Conflicto, ErrorNegocio
from app.domain.reglas import (
    TZ_AR,
    MuestraParaLote,
    armar_lotes,
    avanzar_cupon,
    calcular_presupuesto,
    debe_sellar,
    es_menor_de_edad,
    es_urgente,
    momento_recordatorio,
    monto_base,
    pierde_pago,
    slots_del_dia,
    sumar_meses,
    tipo_resultado,
    validar_diagnostico,
    validar_horario_retiro,
    validar_slot,
    volumen_suficiente,
)

# --- Validar Diagnóstico (E2) ---------------------------------------------------------------

CARDINAL, S1, S2, S3 = 79256006, 254788004, 45004005, 29738008


@pytest.mark.parametrize(
    ("sintomas", "esperado"),
    [
        ({CARDINAL}, True),
        ({S1, S2}, True),
        ({S1, S2, S3}, True),
        ({CARDINAL, S1}, True),
        ({S1}, False),
        (set(), False),
        ({S1, 999}, False),
    ],
)
def test_validar_diagnostico(sintomas: set[int], esperado: bool) -> None:
    assert validar_diagnostico(sintomas, CARDINAL, {S1, S2, S3}) is esperado


# --- Urgente ------------------------------------------------------------------------------


def test_urgente_pompe_menor_de_4_meses() -> None:
    nac = date(2026, 6, 30)
    assert es_urgente(True, nac, date(2026, 10, 29))
    assert not es_urgente(True, nac, date(2026, 10, 30))  # cumple 4 meses
    assert not es_urgente(False, nac, date(2026, 7, 1))


def test_sumar_meses_fin_de_mes() -> None:
    assert sumar_meses(date(2026, 10, 31), 4) == date(2027, 2, 28)
    assert sumar_meses(date(2027, 10, 31), 4) == date(2028, 2, 29)


def test_menor_de_edad() -> None:
    assert es_menor_de_edad(date(2010, 1, 1), date(2027, 12, 31))
    assert not es_menor_de_edad(date(2008, 10, 19), date(2026, 10, 19))


# --- Presupuesto (E16) --------------------------------------------------------------------


@pytest.mark.parametrize(("genes", "monto"), [(1, "500.00"), (5, "500.00"), (6, "530.00"), (10, "650.00")])
def test_monto_base(genes: int, monto: str) -> None:
    assert monto_base(genes) == Decimal(monto)


def test_monto_base_sin_genes() -> None:
    with pytest.raises(ErrorNegocio):
        monto_base(0)


def test_presupuesto_particular() -> None:
    p = calcular_presupuesto(7, tiene_obra_social=False)
    assert p.modalidad == M.PARTICULAR
    assert p.monto_base_usd == Decimal("560.00")
    assert p.monto_a_pagar_usd == Decimal("560.00")
    assert p.monto_obra_social_usd == 0


def test_presupuesto_obra_social_total() -> None:
    p = calcular_presupuesto(3, tiene_obra_social=True, cobertura_pct=Decimal(100))
    assert p.modalidad == M.OBRA_SOCIAL
    assert p.monto_a_pagar_usd == 0
    assert p.monto_obra_social_usd == Decimal("500.00")


def test_presupuesto_mixto_con_cupon() -> None:
    p = calcular_presupuesto(6, tiene_obra_social=True, cobertura_pct=Decimal("70"), descuento_cupon_pct=10)
    assert p.modalidad == M.MIXTA
    assert p.monto_paciente_sin_cupon_usd == Decimal("159.00")  # 30% de 530
    assert p.descuento_cupon_usd == Decimal("15.90")
    assert p.monto_a_pagar_usd == Decimal("143.10")
    assert p.monto_obra_social_usd == Decimal("371.00")


def test_presupuesto_cobertura_cero_es_particular() -> None:
    p = calcular_presupuesto(2, tiene_obra_social=True, cobertura_pct=Decimal(0))
    assert p.modalidad == M.PARTICULAR


def test_presupuesto_redondeo_con_decimal() -> None:
    p = calcular_presupuesto(5, tiene_obra_social=True, cobertura_pct=Decimal("33.33"), descuento_cupon_pct=7)
    assert p.monto_paciente_sin_cupon_usd == Decimal("333.35")
    assert p.descuento_cupon_usd == Decimal("23.33")
    assert p.monto_a_pagar_usd == Decimal("310.02")
    assert all(isinstance(v, Decimal) for v in (p.monto_base_usd, p.monto_a_pagar_usd))


def test_presupuesto_cupon_100_deja_en_cero() -> None:
    assert calcular_presupuesto(1, False, descuento_cupon_pct=100).monto_a_pagar_usd == 0


@pytest.mark.parametrize("cob", [Decimal(-1), Decimal("100.01")])
def test_presupuesto_cobertura_invalida(cob: Decimal) -> None:
    with pytest.raises(ErrorNegocio):
        calcular_presupuesto(1, True, cob)


# --- Agenda (E11) -------------------------------------------------------------------------

LUNES = date(2026, 10, 26)
FERIADO = date(2026, 10, 12)


def test_slots_dia_habil() -> None:
    slots = slots_del_dia(LUNES, set())
    assert len(slots) == 36
    assert slots[0].astimezone(TZ_AR).strftime("%H:%M") == "09:00"
    assert slots[-1].astimezone(TZ_AR).strftime("%H:%M") == "17:45"


def test_sin_slots_fin_de_semana_ni_feriado() -> None:
    assert slots_del_dia(date(2026, 10, 24), set()) == []
    assert slots_del_dia(FERIADO, {FERIADO}) == []


AHORA = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def _ar(d: date, h: int, m: int) -> datetime:
    return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ_AR)


def test_validar_slot_ok() -> None:
    validar_slot(_ar(LUNES, 9, 15), set(), AHORA)


@pytest.mark.parametrize(
    ("inicio", "codigo"),
    [
        (_ar(LUNES, 9, 10), "TURNO_FUERA_DE_AGENDA"),
        (_ar(LUNES, 8, 45), "TURNO_FUERA_DE_AGENDA"),
        (_ar(LUNES, 18, 0), "TURNO_FUERA_DE_AGENDA"),
        (_ar(date(2026, 10, 25), 10, 0), "TURNO_FUERA_DE_AGENDA"),
        (_ar(date(2026, 10, 19), 9, 0), "TURNO_EN_EL_PASADO"),
        (_ar(date(2026, 12, 21), 10, 0), "TURNO_FUERA_DE_VENTANA"),
    ],
)
def test_validar_slot_errores(inicio: datetime, codigo: str) -> None:
    with pytest.raises(ErrorNegocio) as e:
        validar_slot(inicio, set(), AHORA)
    assert e.value.code == codigo


def test_validar_slot_feriado() -> None:
    with pytest.raises(ErrorNegocio):
        validar_slot(_ar(date(2026, 11, 23), 10, 0), {date(2026, 11, 23)}, AHORA)


def test_validar_slot_sin_tz() -> None:
    with pytest.raises(ErrorNegocio):
        validar_slot(datetime(2026, 10, 26, 12, 0), set(), AHORA)


def test_recordatorio_dia_anterior() -> None:
    r = momento_recordatorio(_ar(LUNES, 10, 0))
    assert r.astimezone(TZ_AR) == _ar(date(2026, 10, 25), 9, 0)


def test_retiro_fedex() -> None:
    validar_horario_retiro(_ar(LUNES, 18, 0), set(), AHORA)
    for mal in (_ar(LUNES, 18, 1), _ar(date(2026, 10, 24), 10, 0), _ar(date(2026, 10, 19), 9, 0)):
        with pytest.raises(ErrorNegocio):
            validar_horario_retiro(mal, set(), AHORA)


def test_inasistencias() -> None:
    assert not pierde_pago(3)
    assert pierde_pago(4)


# --- Lotes (E25) --------------------------------------------------------------------------


def test_volumen() -> None:
    assert volumen_suficiente(Decimal("2"))
    assert not volumen_suficiente(Decimal("1.5"))


def _m(n: int, urg: bool = False) -> MuestraParaLote:
    return MuestraParaLote(n, urg)


def test_lote_queda_abierto_si_no_llega_a_10() -> None:
    grupos = armar_lotes(3, False, [_m(1), _m(2)])
    assert len(grupos) == 1
    assert grupos[0].muestras == (1, 2)
    assert not grupos[0].sellar
    assert grupos[0].continua_actual


def test_lote_sella_al_llegar_a_10_y_el_resto_pasa_al_siguiente() -> None:
    grupos = armar_lotes(8, False, [_m(i) for i in range(1, 6)])
    assert [g.muestras for g in grupos] == [(1, 2), (3, 4, 5)]
    assert [g.sellar for g in grupos] == [True, False]
    assert [g.continua_actual for g in grupos] == [True, False]


def test_urgente_sella_sin_esperar_10() -> None:
    grupos = armar_lotes(0, False, [_m(1, urg=True)])
    assert grupos == [grupos[0]]
    assert grupos[0].sellar and grupos[0].incluye_urgente and grupos[0].muestras == (1,)


def test_urgente_va_al_final_del_grupo() -> None:
    grupos = armar_lotes(2, False, [_m(1, urg=True), _m(2), _m(3)])
    assert grupos[0].muestras == (2, 3, 1)
    assert grupos[0].sellar


def test_mas_de_un_lote_lleno() -> None:
    grupos = armar_lotes(0, False, [_m(i) for i in range(25)])
    assert [len(g.muestras) for g in grupos] == [10, 10, 5]
    assert [g.sellar for g in grupos] == [True, True, False]


def test_lote_actual_lleno_es_conflicto() -> None:
    with pytest.raises(Conflicto):
        armar_lotes(10, False, [_m(1)])


def test_debe_sellar() -> None:
    assert debe_sellar(10, False)
    assert debe_sellar(1, True)
    assert not debe_sellar(9, False)
    assert not debe_sellar(0, True)


# --- Resultado (E28) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("clasif", "esperado"),
    [
        ([], TR.NEGATIVO),
        ([C.BENIGNA], TR.NEGATIVO),
        ([C.PATOGENICA], TR.POSITIVO),
        ([C.SIGNIFICADO_INCIERTO, C.PATOGENICA, C.BENIGNA], TR.POSITIVO),
        ([C.SIGNIFICADO_INCIERTO], TR.NO_CONCLUYENTE),
        ([C.SIGNIFICADO_INCIERTO, C.BENIGNA], TR.NO_CONCLUYENTE),
    ],
)
def test_tipo_resultado(clasif: list[C], esperado: TR) -> None:
    assert tipo_resultado(clasif) == esperado


# --- Cupón --------------------------------------------------------------------------------


def test_cupon_camino_completo() -> None:
    avanzar_cupon(EC.DISPONIBLE, EC.ASIGNADO_MEDICO, None, AHORA)
    avanzar_cupon(EC.ASIGNADO_MEDICO, EC.ASIGNADO_PACIENTE, None, AHORA)
    avanzar_cupon(EC.ASIGNADO_PACIENTE, EC.USADO, None, AHORA)


def test_cupon_uso_unico() -> None:
    with pytest.raises(Conflicto) as e:
        avanzar_cupon(EC.USADO, EC.USADO, None, AHORA)
    assert e.value.code == "CUPON_USADO"


@pytest.mark.parametrize(
    ("estado", "destino"),
    [
        (EC.DISPONIBLE, EC.ASIGNADO_PACIENTE),
        (EC.DISPONIBLE, EC.USADO),
        (EC.ASIGNADO_MEDICO, EC.USADO),
        (EC.VENCIDO, EC.USADO),
    ],
)
def test_cupon_saltos_invalidos(estado: EC, destino: EC) -> None:
    with pytest.raises(Conflicto):
        avanzar_cupon(estado, destino, None, AHORA)


def test_cupon_vencido() -> None:
    with pytest.raises(Conflicto) as e:
        avanzar_cupon(EC.ASIGNADO_PACIENTE, EC.USADO, AHORA - timedelta(seconds=1), AHORA)
    assert e.value.code == "CUPON_VENCIDO"
