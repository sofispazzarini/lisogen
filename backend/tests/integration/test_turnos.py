"""E11 Sacar Turno, E12 Cancelar Turno, inasistencias (5 → pierde el pago) y Tomar Muestra."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import ConceptoMov, EstadoEstudio, EstadoMuestra, EstadoTurno, RolUsuario
from app.domain.errores import Conflicto
from app.domain.reglas import TZ_AR
from app.models import (
    CentroExtraccion,
    Estudio,
    Feriado,
    MovimientoFinanciero,
    Paciente,
    Pago,
    Turno,
    Usuario,
)
from app.services.extracciones import registrar_extraccion
from app.services.turnos import registrar_inasistencia
from tests import factories, flujos
from tests.factories import headers
from tests.flujos import ok


@pytest.fixture
async def demo(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    return await factories.seed(session)


async def _centro(session: AsyncSession, nombre: str = "Centro de Extracción Palermo") -> int:
    cid = await session.scalar(select(CentroExtraccion.id).where(CentroExtraccion.nombre == nombre))
    assert cid is not None
    return cid


async def _estudio_pagado(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> int:
    p = await session.scalar(select(Paciente).where(Paciente.dni == "30111222"))
    assert p is not None
    eid = (await flujos.alta_estudio(cliente, session, demo[RolUsuario.MEDICO_TRATANTE], p.id))["id"]
    await flujos.emitir_presupuesto(cliente, demo[RolUsuario.ADMINISTRATIVO], eid)
    await flujos.pagar(cliente, demo[RolUsuario.PACIENTE], eid)
    return int(eid)


# --- Agenda -----------------------------------------------------------------------------------


async def test_centros_y_agenda(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    h = headers(demo[RolUsuario.PACIENTE])
    centros = await ok(await cliente.get("/paciente/centros", headers=h))
    assert len(centros) == 10 and all(c["latitud"] and c["longitud"] for c in centros)

    cid = await _centro(session)
    dia = await flujos.proximo_dia_habil(session)
    agenda = await ok(
        await cliente.get(f"/paciente/centros/{cid}/agenda", params={"fecha": dia.isoformat()}, headers=h)
    )
    assert agenda["habil"] and len(agenda["slots"]) == 36
    assert all(s["libre"] for s in agenda["slots"])
    primero = datetime.fromisoformat(agenda["slots"][0]["inicio"]).astimezone(TZ_AR)
    assert (primero.hour, primero.minute) == (9, 0)

    sabado = dia + timedelta(days=(5 - dia.weekday()) % 7 or 7)
    agenda = await ok(
        await cliente.get(f"/paciente/centros/{cid}/agenda", params={"fecha": sabado.isoformat()}, headers=h)
    )
    assert not agenda["habil"] and agenda["slots"] == []
    ayer = (date.today() - timedelta(days=1)).isoformat()
    assert (
        await ok(await cliente.get(f"/paciente/centros/{cid}/agenda", params={"fecha": ayer}, headers=h))
    )["slots"] == []


async def test_agenda_sin_turnos_en_feriado(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    dia = await flujos.proximo_dia_habil(session, 3)
    session.add(Feriado(fecha=dia, descripcion="Feriado de prueba"))
    await session.flush()
    agenda = await ok(
        await cliente.get(
            f"/paciente/centros/{await _centro(session)}/agenda",
            params={"fecha": dia.isoformat()},
            headers=headers(demo[RolUsuario.PACIENTE]),
        )
    )
    assert not agenda["habil"] and agenda["slots"] == []


# --- E11 Sacar Turno --------------------------------------------------------------------------


async def test_sacar_turno_genera_documentos_y_recordatorio(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    paciente, admin = demo[RolUsuario.PACIENTE], demo[RolUsuario.ADMINISTRATIVO]
    eid = await _estudio_pagado(cliente, session, demo)
    cid = await _centro(session)
    dia = await flujos.proximo_dia_habil(session, 2)
    turno = await flujos.sacar_turno(cliente, paciente, eid, cid, flujos.slot(dia, 10, 15))

    assert turno["estado"] == "RESERVADO" and turno["centro_nombre"] == "Centro de Extracción Palermo"
    assert turno["orden_extraccion_url"].startswith("memoria://orden_extraccion_pdf/")
    assert turno["consentimiento_url"].startswith("memoria://consentimiento_pdf/")
    assert await flujos.estado(cliente, admin, eid) == "TURNO_SACADO"

    t = await session.get(Turno, turno["id"])
    assert t is not None and t.recordatorio_at is not None
    recordatorio = t.recordatorio_at.astimezone(TZ_AR)
    assert recordatorio.date() == dia - timedelta(days=1) and recordatorio.hour == 9

    agenda = await ok(
        await cliente.get(
            f"/paciente/centros/{cid}/agenda", params={"fecha": dia.isoformat()}, headers=headers(paciente)
        )
    )
    ocupado = next(
        s
        for s in agenda["slots"]
        if datetime.fromisoformat(s["inicio"]).astimezone(TZ_AR).strftime("%H:%M") == "10:15"
    )
    assert not ocupado["libre"]
    mi_turno = await ok(await cliente.get(f"/paciente/estudios/{eid}/turno", headers=headers(paciente)))
    assert mi_turno["id"] == turno["id"]


async def test_no_se_saca_turno_sin_pago_aunque_sea_urgente(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    bebe = await factories.paciente(session, medico, fecha_nacimiento=date.today() - timedelta(days=40))
    cuenta = await session.get(Usuario, bebe.usuario_id)
    assert cuenta is not None
    estudio = await flujos.alta_estudio(cliente, session, medico, bebe.id, patologia="Pompe")
    assert estudio["urgente"]
    dia = await flujos.proximo_dia_habil(session)
    r = await cliente.post(
        "/paciente/turnos",
        json={
            "estudio_id": estudio["id"],
            "centro_id": await _centro(session),
            "inicio": flujos.slot(dia, 9),
        },
        headers=headers(cuenta),
    )
    assert r.status_code == 422 and r.json()["code"] == "ESTUDIO_NO_HABILITADO"


@pytest.mark.parametrize(
    ("hora", "minuto", "codigo"),
    [(10, 10, "TURNO_FUERA_DE_AGENDA"), (8, 45, "TURNO_FUERA_DE_AGENDA"), (18, 0, "TURNO_FUERA_DE_AGENDA")],
)
async def test_turno_fuera_de_agenda(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    hora: int,
    minuto: int,
    codigo: str,
) -> None:
    eid = await _estudio_pagado(cliente, session, demo)
    dia = await flujos.proximo_dia_habil(session)
    r = await cliente.post(
        "/paciente/turnos",
        json={
            "estudio_id": eid,
            "centro_id": await _centro(session),
            "inicio": flujos.slot(dia, hora, minuto),
        },
        headers=headers(demo[RolUsuario.PACIENTE]),
    )
    assert r.status_code == 422 and r.json()["code"] == codigo


async def test_un_paciente_por_slot(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    eid = await _estudio_pagado(cliente, session, demo)
    otro = await factories.paciente(session, medico)
    cuenta = await session.get(Usuario, otro.usuario_id)
    assert cuenta is not None
    eid2 = (await flujos.alta_estudio(cliente, session, medico, otro.id))["id"]
    await flujos.emitir_presupuesto(cliente, admin, eid2)
    await flujos.pagar(cliente, cuenta, eid2)

    cid = await _centro(session)
    inicio = flujos.slot(await flujos.proximo_dia_habil(session), 11, 30)
    await flujos.sacar_turno(cliente, demo[RolUsuario.PACIENTE], eid, cid, inicio)
    r = await cliente.post(
        "/paciente/turnos",
        json={"estudio_id": eid2, "centro_id": cid, "inicio": inicio},
        headers=headers(cuenta),
    )
    assert r.status_code == 409 and r.json()["code"] == "TURNO_OCUPADO"
    # Mismo horario en otro Centro: sí
    otro_centro = await _centro(session, "Centro de Extracción Caballito")
    await flujos.sacar_turno(cliente, cuenta, eid2, otro_centro, inicio)


async def test_un_turno_activo_por_estudio(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    eid = await _estudio_pagado(cliente, session, demo)
    cid = await _centro(session)
    dia = await flujos.proximo_dia_habil(session)
    await flujos.sacar_turno(cliente, demo[RolUsuario.PACIENTE], eid, cid, flujos.slot(dia, 9))
    r = await cliente.post(
        "/paciente/turnos",
        json={"estudio_id": eid, "centro_id": cid, "inicio": flujos.slot(dia, 9, 15)},
        headers=headers(demo[RolUsuario.PACIENTE]),
    )
    assert r.status_code == 422 and r.json()["code"] == "ESTUDIO_NO_HABILITADO"  # ya está en Turno Sacado


# --- E12 Cancelar Turno -----------------------------------------------------------------------


async def test_cancelar_turno_libera_el_horario(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    paciente, admin = demo[RolUsuario.PACIENTE], demo[RolUsuario.ADMINISTRATIVO]
    eid = await _estudio_pagado(cliente, session, demo)
    cid = await _centro(session)
    inicio = flujos.slot(await flujos.proximo_dia_habil(session), 14)
    turno = await flujos.sacar_turno(cliente, paciente, eid, cid, inicio)

    otro = await factories.usuario(session, RolUsuario.PACIENTE)
    assert (
        await cliente.post(f"/paciente/turnos/{turno['id']}/cancelar", headers=headers(otro))
    ).status_code == 404

    await ok(await cliente.post(f"/paciente/turnos/{turno['id']}/cancelar", headers=headers(paciente)))
    assert await flujos.estado(cliente, admin, eid) == "PAGADO"
    r = await cliente.post(f"/paciente/turnos/{turno['id']}/cancelar", headers=headers(paciente))
    assert r.status_code == 409 and r.json()["code"] == "TURNO_NO_RESERVADO"
    assert (
        await cliente.get(f"/paciente/estudios/{eid}/turno", headers=headers(paciente))
    ).status_code == 404
    # El horario quedó libre y el Paciente puede sacar otro Turno
    await flujos.sacar_turno(cliente, paciente, eid, cid, inicio)


# --- Inasistencias ----------------------------------------------------------------------------


async def _vencer(session: AsyncSession, turno_id: int) -> Turno:
    await session.execute(
        text("UPDATE turno SET inicio = inicio - interval '60 days' WHERE id = :id"), {"id": turno_id}
    )
    turno = await session.get(Turno, turno_id)
    assert turno is not None
    await session.refresh(turno)
    return turno


async def test_inasistencia_permite_nuevo_turno(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    eid = await _estudio_pagado(cliente, session, demo)
    turno = await flujos.sacar_turno(
        cliente,
        demo[RolUsuario.PACIENTE],
        eid,
        await _centro(session),
        flujos.slot(await flujos.proximo_dia_habil(session), 9),
    )
    destino = await registrar_inasistencia(session, await _vencer(session, turno["id"]))
    assert destino == EstadoEstudio.PAGADO
    estudio = await session.get(Estudio, eid)
    assert estudio is not None and estudio.inasistencias == 1
    t = await session.get(Turno, turno["id"])
    assert t is not None and t.estado == EstadoTurno.AUSENTE


async def test_cinco_inasistencias_pierden_el_pago_y_se_vuelve_a_pagar(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    paciente, admin = demo[RolUsuario.PACIENTE], demo[RolUsuario.ADMINISTRATIVO]
    eid = await _estudio_pagado(cliente, session, demo)
    cid = await _centro(session)
    dia = await flujos.proximo_dia_habil(session)
    for n in range(1, 6):
        turno = await flujos.sacar_turno(cliente, paciente, eid, cid, flujos.slot(dia, 9 + n))
        destino = await registrar_inasistencia(session, await _vencer(session, turno["id"]))
        assert destino == (EstadoEstudio.PAGADO if n < 5 else EstadoEstudio.POR_PAGAR)

    assert await flujos.estado(cliente, admin, eid) == "POR_PAGAR"
    estudio = await session.get(Estudio, eid)
    assert estudio is not None
    await session.refresh(estudio)
    assert estudio.inasistencias == 0
    perdida = await session.scalar(
        select(MovimientoFinanciero).where(
            MovimientoFinanciero.estudio_id == eid,
            MovimientoFinanciero.concepto == ConceptoMov.PERDIDA_POR_INASISTENCIAS,
        )
    )
    assert perdida is not None and perdida.monto_usd == Decimal("500.00")
    detalle = await ok(await cliente.get(f"/paciente/estudios/{eid}", headers=headers(paciente)))
    assert "5 inasistencias" in detalle["historial"][-1]["motivo"]
    assert not detalle["presupuesto"]["pagado"]

    # Migración 0002: el Presupuesto admite un segundo pago porque el anterior quedó anulado
    await flujos.pagar(cliente, paciente, eid)
    pagos = list(await session.scalars(select(Pago).order_by(Pago.id)))
    assert [p.anulado_at is not None for p in pagos] == [True, False]
    assert await flujos.estado(cliente, admin, eid) == "PAGADO"


async def test_inasistencia_solo_de_turnos_vencidos(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    eid = await _estudio_pagado(cliente, session, demo)
    turno = await flujos.sacar_turno(
        cliente,
        demo[RolUsuario.PACIENTE],
        eid,
        await _centro(session),
        flujos.slot(await flujos.proximo_dia_habil(session), 9),
    )
    t = await session.get(Turno, turno["id"])
    assert t is not None
    with pytest.raises(Conflicto):
        await registrar_inasistencia(session, t)


# --- Tomar Muestra (servicio sin endpoint, DECISIONES C6) --------------------------------------


async def test_registrar_extraccion(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    eid = await _estudio_pagado(cliente, session, demo)
    turno = await flujos.sacar_turno(
        cliente,
        demo[RolUsuario.PACIENTE],
        eid,
        await _centro(session),
        flujos.slot(await flujos.proximo_dia_habil(session), 9),
    )
    muestra = await registrar_extraccion(session, turno["id"], Decimal("4.5"))
    assert muestra.estado == EstadoMuestra.LISTO_PARA_RETIRAR and muestra.nro_extraccion == 1
    assert await flujos.estado(cliente, demo[RolUsuario.ADMINISTRATIVO], eid) == "LISTO_PARA_RETIRAR"
    t = await session.get(Turno, turno["id"])
    assert t is not None and t.estado == EstadoTurno.REALIZADO
    with pytest.raises(Conflicto):
        await registrar_extraccion(session, turno["id"], Decimal("3"))


# --- E14 Chatbot ------------------------------------------------------------------------------


async def test_chatbot(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    from app.domain.enums import ServicioExterno
    from app.models import IntegracionLog

    h = headers(demo[RolUsuario.PACIENTE])
    r = await ok(
        await cliente.post(
            "/paciente/chatbot", json={"pregunta": "¿Qué es la enfermedad de Gaucher?"}, headers=h
        )
    )
    assert "GBA1" in r["respuesta"] and "Médico Tratante" in r["respuesta"]
    r = await ok(
        await cliente.post("/paciente/chatbot", json={"pregunta": "Quiero hablar con una persona"}, headers=h)
    )
    assert "Fabry, Pompe, MPS 1, Gaucher y ASMD" in r["respuesta"]  # no deriva a una persona
    historial = await ok(await cliente.get("/paciente/chatbot", headers=h))
    assert [m["pregunta"] for m in historial] == [
        "¿Qué es la enfermedad de Gaucher?",
        "Quiero hablar con una persona",
    ]
    log = await session.scalar(
        select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.CHATBOT)
    )
    assert log is not None and "Gaucher" not in str(log.request)
    assert (await cliente.post("/paciente/chatbot", json={"pregunta": ""}, headers=h)).status_code == 422
