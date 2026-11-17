"""E16 Emitir Presupuesto, E8 Pagar Presupuesto, E9 Aplicar Cupón, E17/E18 Autorización y Rechazo de
Obra Social, E10 reautorización y registro financiero."""

from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ConceptoMov, EstadoCupon, EstadoReaut, RolUsuario, ServicioExterno
from app.integrations.pdf import generar_pdf
from app.integrations.ports import ErrorCupones, ErrorObraSocial
from app.integrations.registro import Adaptadores
from app.models import (
    Cupon,
    IntegracionLog,
    MovimientoFinanciero,
    ObraSocial,
    Paciente,
    Presupuesto,
    SolicitudReautorizacion,
    Usuario,
)
from tests import factories, flujos
from tests.factories import headers
from tests.falsos import CuponesFalla, ObrasSocialesFalla
from tests.flujos import ok


@pytest.fixture
async def demo(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    return await factories.seed(session)


async def _paciente_demo(session: AsyncSession) -> Paciente:
    p = await session.scalar(select(Paciente).where(Paciente.dni == "30111222"))
    assert p is not None
    return p


async def _paciente_con_os(
    session: AsyncSession, medico: Usuario, codigo_os: str
) -> tuple[Paciente, Usuario]:
    os_id = await session.scalar(select(ObraSocial.id).where(ObraSocial.codigo_externo == codigo_os))
    p = await factories.paciente(session, medico, obra_social_id=os_id)
    cuenta = await session.get(Usuario, p.usuario_id)
    assert cuenta is not None
    return p, cuenta


# --- E16 + E8 particular ----------------------------------------------------------------------


async def test_presupuesto_particular_y_pago(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, admin, paciente = (
        demo[RolUsuario.MEDICO_TRATANTE],
        demo[RolUsuario.ADMINISTRATIVO],
        demo[RolUsuario.PACIENTE],
    )
    p = await _paciente_demo(session)
    estudio = await flujos.alta_estudio(
        cliente,
        session,
        medico,
        p.id,
        genes_manuales=["TP53", "MYH7", "TTN", "LMNA", "SCN5A", "KCNQ1"],
        hallazgos=True,
    )
    eid = estudio["id"]

    previo = await ok(
        await cliente.get(f"/administrativo/estudios/{eid}/presupuesto/previo", headers=headers(admin))
    )
    assert previo["cantidad_genes"] == 7  # GLA + 6 manuales; los 5 de hallazgos secundarios no suman
    assert Decimal(previo["monto_base_usd"]) == Decimal("560.00")
    assert previo["modalidad"] == "PARTICULAR" and previo["obra_social"] is None
    assert await flujos.estado(cliente, admin, eid) == "CREADO"

    await flujos.emitir_presupuesto(cliente, admin, eid)
    assert await flujos.estado(cliente, admin, eid) == "POR_PAGAR"
    r = await cliente.post(f"/administrativo/estudios/{eid}/presupuesto", headers=headers(admin))
    assert r.status_code == 409 and r.json()["code"] == "ESTUDIO_NO_CREADO"

    pres = await ok(await cliente.get(f"/paciente/estudios/{eid}/presupuesto", headers=headers(paciente)))
    assert Decimal(pres["monto_a_pagar_usd"]) == Decimal("560.00") and not pres["pagado"]

    pago = await flujos.pagar(cliente, paciente, eid)
    assert pago["referencia"].startswith("SIM-") and Decimal(pago["monto_usd"]) == Decimal("560.00")
    assert await flujos.estado(cliente, admin, eid) == "PAGADO"
    r = await cliente.post(f"/paciente/estudios/{eid}/pagar", headers=headers(paciente))
    assert r.status_code == 409 and r.json()["code"] == "ESTUDIO_NO_POR_PAGAR"

    registro = await ok(await cliente.get("/administrativo/movimientos", headers=headers(admin)))
    assert Decimal(registro["total_pacientes_usd"]) == Decimal("560.00")
    assert [m["concepto"] for m in registro["movimientos"]] == ["PAGO_PACIENTE"]


async def test_paciente_solo_ve_sus_estudios(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    otro, otra_cuenta = await _paciente_con_os(session, medico, "IOMA")
    ajeno = await flujos.alta_estudio(cliente, session, medico, otro.id)
    paciente = demo[RolUsuario.PACIENTE]
    for url in (f"/paciente/estudios/{ajeno['id']}", f"/paciente/estudios/{ajeno['id']}/presupuesto"):
        assert (await cliente.get(url, headers=headers(paciente))).status_code == 404
    r = await cliente.post(f"/paciente/estudios/{ajeno['id']}/pagar", headers=headers(paciente))
    assert r.status_code == 404
    mios = await ok(await cliente.get("/paciente/estudios", headers=headers(otra_cuenta)))
    assert [e["id"] for e in mios] == [ajeno["id"]]


# --- E9 Aplicar Cupón -------------------------------------------------------------------------


async def _cupon_para(
    cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario], paciente_id: int, pct: int
) -> dict:
    gerente, medico = demo[RolUsuario.GERENTE_MEDICO], demo[RolUsuario.MEDICO_TRATANTE]
    cupon = (
        await ok(
            await cliente.post(
                "/gerente/cupones", json={"descuento_pct": pct, "cantidad": 1}, headers=headers(gerente)
            ),
            201,
        )
    )[0]
    await ok(
        await cliente.post(
            "/gerente/cupones/asignar",
            json={"cupon_ids": [cupon["id"]], "medico_id": medico.id},
            headers=headers(gerente),
        )
    )
    await ok(
        await cliente.post(
            f"/medico/cupones/{cupon['id']}/asignar",
            json={"paciente_id": paciente_id},
            headers=headers(medico),
        )
    )
    return dict(cupon)


async def test_aplicar_cupon_por_codigo_y_pagar_con_descuento(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    admin, paciente = demo[RolUsuario.ADMINISTRATIVO], demo[RolUsuario.PACIENTE]
    p = await _paciente_demo(session)
    eid = (await flujos.alta_estudio(cliente, session, demo[RolUsuario.MEDICO_TRATANTE], p.id))["id"]
    await flujos.emitir_presupuesto(cliente, admin, eid)
    cupon = await _cupon_para(cliente, demo, p.id, 20)
    assert [c["id"] for c in await ok(await cliente.get("/paciente/cupones", headers=headers(paciente)))] == [
        cupon["id"]
    ]

    r = await cliente.post(
        f"/paciente/estudios/{eid}/cupon", data={"codigo": "LG20-NOEXISTE"}, headers=headers(paciente)
    )
    assert r.status_code == 422 and r.json()["code"] == "CUPON_INVALIDO"
    pres = await ok(await cliente.get(f"/paciente/estudios/{eid}/presupuesto", headers=headers(paciente)))
    assert Decimal(pres["monto_a_pagar_usd"]) == Decimal("500.00")  # mantiene el precio original

    pres = await ok(
        await cliente.post(
            f"/paciente/estudios/{eid}/cupon",
            data={"codigo": cupon["codigo"].lower()},
            headers=headers(paciente),
        )
    )
    assert Decimal(pres["descuento_cupon_usd"]) == Decimal("100.00")
    assert Decimal(pres["monto_a_pagar_usd"]) == Decimal("400.00")
    assert pres["cupon_codigo"] == cupon["codigo"]
    c = await session.get(Cupon, cupon["id"])
    assert c is not None
    await session.refresh(c)
    assert c.estado == EstadoCupon.USADO and c.usado_at is not None
    assert await session.scalar(
        select(IntegracionLog.id).where(
            IntegracionLog.servicio == ServicioExterno.CUPONES, IntegracionLog.operacion == "canjear"
        )
    )

    r = await cliente.post(
        f"/paciente/estudios/{eid}/cupon", data={"codigo": cupon["codigo"]}, headers=headers(paciente)
    )
    assert r.status_code == 409 and r.json()["code"] == "PRESUPUESTO_CON_CUPON"
    pago = await flujos.pagar(cliente, paciente, eid)
    assert Decimal(pago["monto_usd"]) == Decimal("400.00")


async def test_aplicar_cupon_desde_pdf_con_qr(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    adaptadores: Adaptadores,
) -> None:
    paciente = demo[RolUsuario.PACIENTE]
    p = await _paciente_demo(session)
    eid = (await flujos.alta_estudio(cliente, session, demo[RolUsuario.MEDICO_TRATANTE], p.id))["id"]
    await flujos.emitir_presupuesto(cliente, demo[RolUsuario.ADMINISTRATIVO], eid)
    cupon = await _cupon_para(cliente, demo, p.id, 50)
    pdf = next(
        contenido
        for clave, (contenido, _) in adaptadores.storage.objetos.items()  # type: ignore[attr-defined]
        if clave.startswith("cupon_pdf/") and cupon["codigo"].encode() in contenido
    )
    r = await cliente.post(
        f"/paciente/estudios/{eid}/cupon",
        files={"archivo": ("x.pdf", generar_pdf("Sin QR", ["nada"]), "application/pdf")},
        headers=headers(paciente),
    )
    assert r.json()["code"] == "CUPON_INVALIDO"  # un PDF sin la marca del Cupón no se acepta
    r = await cliente.post(
        f"/paciente/estudios/{eid}/cupon",
        files={"archivo": ("cupon.pdf", pdf, "application/pdf")},
        headers=headers(paciente),
    )
    pres = await ok(r)
    assert Decimal(pres["monto_a_pagar_usd"]) == Decimal("250.00")


@pytest.mark.parametrize(
    ("error", "estado", "codigo"),
    [
        (ErrorCupones("HTTP 409", status=409), 409, "CUPON_CONFLICTO"),
        (ErrorCupones("HTTP 400", status=400), 422, "CUPON_INVALIDO"),
        (ErrorCupones("timeout", incierto=True), 502, "CUPONES_SIN_RESPUESTA"),
    ],
)
async def test_cupon_rechazado_por_la_api_no_cambia_el_precio(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    adaptadores: Adaptadores,
    error: ErrorCupones,
    estado: int,
    codigo: str,
) -> None:
    """Si el canje falla en la API de Cupones, el Presupuesto queda igual y el Cupón sigue disponible."""
    paciente = demo[RolUsuario.PACIENTE]
    p = await _paciente_demo(session)
    eid = (await flujos.alta_estudio(cliente, session, demo[RolUsuario.MEDICO_TRATANTE], p.id))["id"]
    await flujos.emitir_presupuesto(cliente, demo[RolUsuario.ADMINISTRATIVO], eid)
    cupon = await _cupon_para(cliente, demo, p.id, 50)
    adaptadores.cupones = CuponesFalla("canjear", error)
    r = await cliente.post(
        f"/paciente/estudios/{eid}/cupon", data={"codigo": cupon["codigo"]}, headers=headers(paciente)
    )
    assert r.status_code == estado and r.json()["code"] == codigo
    c = await session.get(Cupon, cupon["id"])
    assert c is not None
    await session.refresh(c)
    assert c.estado == EstadoCupon.ASIGNADO_PACIENTE and c.usado_at is None
    pago = await flujos.pagar(cliente, paciente, eid)
    assert Decimal(pago["monto_usd"]) == Decimal("500.00")


async def test_cupon_de_otro_paciente_no_vale(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    p = await _paciente_demo(session)
    otro = await factories.paciente(session, medico)
    cupon_ajeno = await _cupon_para(cliente, demo, otro.id, 30)
    eid = (await flujos.alta_estudio(cliente, session, medico, p.id))["id"]
    await flujos.emitir_presupuesto(cliente, admin, eid)
    r = await cliente.post(
        f"/paciente/estudios/{eid}/cupon",
        data={"codigo": cupon_ajeno["codigo"]},
        headers=headers(demo[RolUsuario.PACIENTE]),
    )
    assert r.status_code == 422 and r.json()["code"] == "CUPON_INVALIDO"


# --- E17 / E18 / E10 Obra Social --------------------------------------------------------------


async def test_obra_social_total_autoriza_y_equivale_a_pagado(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    p, cuenta = await _paciente_con_os(session, medico, "IOMA")
    eid = (await flujos.alta_estudio(cliente, session, medico, p.id))["id"]
    previo = await flujos.emitir_presupuesto(cliente, admin, eid)
    assert previo["modalidad"] == "OBRA_SOCIAL" and Decimal(previo["cobertura_pct"]) == 100
    assert Decimal(previo["monto_a_pagar_usd"]) == 0
    assert await flujos.estado(cliente, admin, eid) == "PENDIENTE_AUTORIZACION"
    assert await session.scalar(
        select(IntegracionLog.id).where(
            IntegracionLog.servicio == ServicioExterno.OBRAS_SOCIALES, IntegracionLog.estudio_id == eid
        )
    )

    r = await cliente.post(f"/paciente/estudios/{eid}/pagar", headers=headers(cuenta))
    assert r.status_code == 409  # con Obra Social no paga: espera la Autorización (E8)

    await ok(await cliente.post(f"/administrativo/estudios/{eid}/autorizacion", headers=headers(admin)))
    assert await flujos.estado(cliente, admin, eid) == "AUTORIZADO"
    mov = await session.scalar(select(MovimientoFinanciero).where(MovimientoFinanciero.estudio_id == eid))
    assert (
        mov is not None
        and mov.concepto == ConceptoMov.PAGO_OBRA_SOCIAL
        and mov.monto_usd == Decimal("500.00")
    )
    r = await cliente.post(f"/administrativo/estudios/{eid}/autorizacion", headers=headers(admin))
    assert r.status_code == 409 and r.json()["code"] == "ESTUDIO_NO_PENDIENTE"


async def test_cobertura_parcial_autoriza_y_paga_la_diferencia(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    p, cuenta = await _paciente_con_os(session, medico, "MEDIFE")
    eid = (await flujos.alta_estudio(cliente, session, medico, p.id))["id"]
    previo = await flujos.emitir_presupuesto(cliente, admin, eid)
    assert previo["modalidad"] == "MIXTA" and Decimal(previo["monto_a_pagar_usd"]) == Decimal("150.00")
    await ok(await cliente.post(f"/administrativo/estudios/{eid}/autorizacion", headers=headers(admin)))
    assert await flujos.estado(cliente, admin, eid) == "POR_PAGAR"
    pago = await flujos.pagar(cliente, cuenta, eid)
    assert Decimal(pago["monto_usd"]) == Decimal("150.00")
    assert await flujos.estado(cliente, admin, eid) == "PAGADO"
    registro = await ok(await cliente.get("/administrativo/movimientos", headers=headers(admin)))
    assert Decimal(registro["total_obras_sociales_usd"]) == Decimal("350.00")
    assert Decimal(registro["total_pacientes_usd"]) == Decimal("150.00")


async def test_rechazo_y_reautorizacion_con_decision_judicial(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    p, cuenta = await _paciente_con_os(session, medico, "IOMA")  # cobertura total
    eid = (await flujos.alta_estudio(cliente, session, medico, p.id))["id"]
    await flujos.emitir_presupuesto(cliente, admin, eid)

    r = await cliente.post(
        f"/administrativo/estudios/{eid}/rechazo", json={"motivo": ""}, headers=headers(admin)
    )
    assert r.status_code == 422
    await ok(
        await cliente.post(
            f"/administrativo/estudios/{eid}/rechazo",
            json={"motivo": "Estudio genético no incluido en el plan"},
            headers=headers(admin),
        )
    )
    detalle = await ok(await cliente.get(f"/paciente/estudios/{eid}", headers=headers(cuenta)))
    assert detalle["estado"] == "RECHAZADO"
    assert detalle["rechazo_motivo"] == "Estudio genético no incluido en el plan"
    assert not detalle["reautorizacion_pendiente"]

    r = await cliente.post(
        f"/paciente/estudios/{eid}/reautorizacion",
        files={"archivo": ("x.pdf", b"no es un pdf", "application/pdf")},
        headers=headers(cuenta),
    )
    assert r.status_code == 422 and r.json()["code"] == "ARCHIVO_NO_PDF"
    pdf = generar_pdf("Sentencia", ["Se ordena a la Obra Social cubrir el Estudio genético."])
    await ok(
        await cliente.post(
            f"/paciente/estudios/{eid}/reautorizacion",
            files={"archivo": ("sentencia.pdf", pdf, "application/pdf")},
            headers=headers(cuenta),
        )
    )
    detalle = await ok(await cliente.get(f"/paciente/estudios/{eid}", headers=headers(cuenta)))
    assert detalle["estado"] == "PENDIENTE_AUTORIZACION" and detalle["reautorizacion_pendiente"]

    pendientes = await ok(await cliente.get("/administrativo/reautorizaciones", headers=headers(admin)))
    assert len(pendientes) == 1 and pendientes[0]["estudio_id"] == eid
    assert pendientes[0]["decision_judicial_url"].startswith("memoria://decision_judicial_pdf/")

    await ok(await cliente.post(f"/administrativo/estudios/{eid}/autorizacion", headers=headers(admin)))
    assert await flujos.estado(cliente, admin, eid) == "AUTORIZADO"
    sol = await session.scalar(
        select(SolicitudReautorizacion).where(SolicitudReautorizacion.estudio_id == eid)
    )
    assert sol is not None
    await session.refresh(sol)
    assert sol.estado == EstadoReaut.AUTORIZADA and sol.resuelto_at is not None
    assert await ok(await cliente.get("/administrativo/reautorizaciones", headers=headers(admin))) == []


async def test_reautorizacion_solo_si_esta_rechazado(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    paciente = demo[RolUsuario.PACIENTE]
    eid = (
        await flujos.alta_estudio(
            cliente, session, demo[RolUsuario.MEDICO_TRATANTE], (await _paciente_demo(session)).id
        )
    )["id"]
    r = await cliente.post(
        f"/paciente/estudios/{eid}/reautorizacion",
        files={"archivo": ("s.pdf", generar_pdf("S", ["x"]), "application/pdf")},
        headers=headers(paciente),
    )
    assert r.status_code == 409 and r.json()["code"] == "ESTUDIO_NO_RECHAZADO"


async def test_cupon_no_aplica_con_cobertura_total(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    p, cuenta = await _paciente_con_os(session, medico, "IOMA")
    eid = (await flujos.alta_estudio(cliente, session, medico, p.id))["id"]
    await flujos.emitir_presupuesto(cliente, demo[RolUsuario.ADMINISTRATIVO], eid)
    cupon = await _cupon_para(cliente, demo, p.id, 10)
    r = await cliente.post(
        f"/paciente/estudios/{eid}/cupon", data={"codigo": cupon["codigo"]}, headers=headers(cuenta)
    )
    assert r.status_code == 422 and r.json()["code"] == "CUPON_NO_APLICA"


async def test_solo_administrativo_emite(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    eid = (
        await flujos.alta_estudio(
            cliente, session, demo[RolUsuario.MEDICO_TRATANTE], (await _paciente_demo(session)).id
        )
    )["id"]
    for rol in (RolUsuario.PACIENTE, RolUsuario.MEDICO_TRATANTE, RolUsuario.GERENTE_MEDICO):
        r = await cliente.post(f"/administrativo/estudios/{eid}/presupuesto", headers=headers(demo[rol]))
        assert r.status_code == 403


# --- API de Obras Sociales: la Obra Social se simula con los botones del Administrativo --------


async def _con_obra_social(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario], codigo: str = "IOMA"
) -> tuple[int, Usuario, Usuario]:
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    p, cuenta = await _paciente_con_os(session, medico, codigo)
    eid = (await flujos.alta_estudio(cliente, session, medico, p.id))["id"]
    return eid, admin, cuenta


async def test_presupuesto_con_obra_social_crea_la_solicitud(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    eid, admin, _ = await _con_obra_social(cliente, session, demo)
    await flujos.emitir_presupuesto(cliente, admin, eid)
    p = await session.scalar(select(Presupuesto).where(Presupuesto.estudio_id == eid))
    assert p is not None and p.os_solicitud_id and p.os_url_autorizar and p.os_url_rechazar
    log = await session.scalar(
        select(IntegracionLog).where(
            IntegracionLog.servicio == ServicioExterno.OBRAS_SOCIALES,
            IntegracionLog.operacion == "solicitar",
            IntegracionLog.estudio_id == eid,
        )
    )
    assert log is not None and log.ok
    assert log.request["paciente_nombre"] == "[omitido]"  # no queda el nombre del Paciente en el log
    assert "mock://" not in str(log.request) and "mock://" not in str(log.response)  # ni las URLs


async def test_presupuesto_particular_no_crea_solicitud(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    eid = (
        await flujos.alta_estudio(
            cliente, session, demo[RolUsuario.MEDICO_TRATANTE], (await _paciente_demo(session)).id
        )
    )["id"]
    await flujos.emitir_presupuesto(cliente, demo[RolUsuario.ADMINISTRATIVO], eid)
    p = await session.scalar(select(Presupuesto).where(Presupuesto.estudio_id == eid))
    assert p is not None and p.os_solicitud_id is None


async def test_si_falla_la_cobertura_no_se_emite_como_particular(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    eid, admin, _ = await _con_obra_social(cliente, session, demo)
    adaptadores.obras_sociales = ObrasSocialesFalla(
        "cobertura", ErrorObraSocial("sin respuesta", incierto=True)
    )
    r = await cliente.post(f"/administrativo/estudios/{eid}/presupuesto", headers=headers(admin))
    assert r.status_code == 502 and r.json()["code"] == "OBRA_SOCIAL_SIN_RESPUESTA"
    assert await flujos.estado(cliente, admin, eid) == "CREADO"
    assert await session.scalar(select(Presupuesto.id).where(Presupuesto.estudio_id == eid)) is None


@pytest.mark.parametrize(
    ("operacion", "error", "status", "code"),
    [
        (
            "autorizar",
            ErrorObraSocial("HTTP 500", status=500, incierto=True),
            502,
            "OBRA_SOCIAL_SIN_RESPUESTA",
        ),
        (
            "autorizar",
            ErrorObraSocial("HTTP 409", status=409, codigo="ESTADO_INVALIDO"),
            409,
            "OBRA_SOCIAL_ESTADO",
        ),
        ("autorizar", ErrorObraSocial("HTTP 401", status=401), 502, "OBRA_SOCIAL_NO_DISPONIBLE"),
        ("rechazar", ErrorObraSocial("HTTP 400", status=400), 422, "OBRA_SOCIAL_RECHAZO"),
    ],
)
async def test_si_la_api_falla_el_estudio_no_cambia(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
    operacion: str,
    error: ErrorObraSocial,
    status: int,
    code: str,
) -> None:
    eid, admin, _ = await _con_obra_social(cliente, session, demo)
    await flujos.emitir_presupuesto(cliente, admin, eid)
    adaptadores.obras_sociales = ObrasSocialesFalla(operacion, error)
    if operacion == "autorizar":
        r = await cliente.post(f"/administrativo/estudios/{eid}/autorizacion", headers=headers(admin))
    else:
        r = await cliente.post(
            f"/administrativo/estudios/{eid}/rechazo", json={"motivo": "No cubre"}, headers=headers(admin)
        )
    assert r.status_code == status and r.json()["code"] == code
    assert await flujos.estado(cliente, admin, eid) == "PENDIENTE_AUTORIZACION"
    assert (
        await session.scalar(select(MovimientoFinanciero.id).where(MovimientoFinanciero.estudio_id == eid))
        is None
    )


async def test_demanda_rechazada_por_la_api_no_guarda_la_reautorizacion(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    eid, admin, cuenta = await _con_obra_social(cliente, session, demo)
    await flujos.emitir_presupuesto(cliente, admin, eid)
    await ok(
        await cliente.post(
            f"/administrativo/estudios/{eid}/rechazo", json={"motivo": "No cubre"}, headers=headers(admin)
        )
    )
    adaptadores.obras_sociales = ObrasSocialesFalla(
        "presentar_demanda", ErrorObraSocial("HTTP 409", status=409, codigo="ESTADO_INVALIDO")
    )
    pdf = generar_pdf("Sentencia", ["Se ordena cubrir el Estudio."])
    r = await cliente.post(
        f"/paciente/estudios/{eid}/reautorizacion",
        files={"archivo": ("s.pdf", pdf, "application/pdf")},
        headers=headers(cuenta),
    )
    assert r.status_code == 409 and r.json()["code"] == "OBRA_SOCIAL_ESTADO"
    assert await flujos.estado(cliente, admin, eid) == "RECHAZADO"
    assert (
        await session.scalar(
            select(SolicitudReautorizacion.id).where(SolicitudReautorizacion.estudio_id == eid)
        )
        is None
    )


async def test_la_decision_judicial_no_puede_pasar_de_5_mb(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    eid, admin, cuenta = await _con_obra_social(cliente, session, demo)
    await flujos.emitir_presupuesto(cliente, admin, eid)
    await ok(
        await cliente.post(
            f"/administrativo/estudios/{eid}/rechazo", json={"motivo": "No cubre"}, headers=headers(admin)
        )
    )
    grande = b"%PDF-1.4\n" + b"0" * (5 * 1024 * 1024)
    r = await cliente.post(
        f"/paciente/estudios/{eid}/reautorizacion",
        files={"archivo": ("s.pdf", grande, "application/pdf")},
        headers=headers(cuenta),
    )
    assert r.status_code == 422 and r.json()["code"] == "ARCHIVO_DEMASIADO_GRANDE"
