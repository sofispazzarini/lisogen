"""Tests de punta a punta obligatorios. Cada actor opera por la API con su rol; sólo Tomar Muestra
(sin endpoint, DECISIONES C6) y la generación de la Orden del Día (job de las 06:00) llaman al servicio."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.domain.enums import EstadoEstudio, MotivoReextraccion, RolUsuario
from app.integrations.pdf import generar_pdf
from app.integrations.registro import Adaptadores, Integraciones
from app.models import (
    CentroExtraccion,
    Lote,
    MovimientoFinanciero,
    ObraSocial,
    Paciente,
    SolicitudReextraccion,
    Transportista,
    Turno,
    Usuario,
)
from app.services import logistica
from app.services.comun import ahora
from app.services.extracciones import registrar_extraccion
from tests import factories, flujos
from tests.factories import headers
from tests.flujos import ok

E = EstadoEstudio
GLA_PATOGENICA = "c.644A>G (p.Asn215Ser)"


@pytest.fixture
async def demo(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    return await factories.seed(session)


async def _palermo(session: AsyncSession) -> int:
    cid = await session.scalar(select(CentroExtraccion.id).where(CentroExtraccion.nombre.contains("Palermo")))
    assert cid is not None
    return cid


async def _alta_paciente(
    cliente: httpx.AsyncClient, session: AsyncSession, medico: Usuario, **cambios: Any
) -> tuple[int, Usuario]:
    datos: dict[str, Any] = {
        "dni": "35123987",
        "nombre": "Camila",
        "apellido": "Benítez",
        "fecha_nacimiento": "1988-04-12",
        "telefono": "+54 11 4777-1234",
        "email": "camila.benitez@test.com.ar",
        "resumen_historia_clinica": "Acroparestesias desde la infancia e hipohidrosis.",
        "sintomas": [79256006, 45004005],
        "diagnosticos": [
            {"patologia_id": await flujos.patologia_id(session, "Fabry"), "tipo_sospecha": "CLINICA"}
        ],
    } | cambios
    pid = (await ok(await cliente.post("/medico/pacientes", json=datos, headers=headers(medico)), 201))["id"]
    cuenta = await session.scalar(select(Usuario).where(Usuario.email == datos["email"]))
    assert cuenta is not None
    cuenta.debe_cambiar_password = False  # el cambio obligatorio de contraseña se prueba en test_auth
    return pid, cuenta


async def _historial(cliente: httpx.AsyncClient, admin: Usuario, estudio_id: int) -> list[str]:
    detalle = await ok(await cliente.get(f"/administrativo/estudios/{estudio_id}", headers=headers(admin)))
    return [h["estado_nuevo"] for h in detalle["historial"]]


async def _orden_de_hoy(session: AsyncSession, adaptadores: Adaptadores, transportista: Usuario) -> None:
    """Lo que hace el job de las 06:00 (etapa 5) para el Transportista de CABA."""
    t = await session.get(Transportista, transportista.id)
    assert t is not None
    assert await logistica.crear_orden(session, Integraciones(session, adaptadores), t, logistica.hoy())


async def _recolectar_y_entregar(cliente: httpx.AsyncClient, transportista: Usuario) -> dict[str, Any]:
    orden = await ok(await cliente.get("/transportista/orden-del-dia", headers=headers(transportista)))
    for parada in orden["paradas"]:
        await ok(
            await cliente.post(
                f"/transportista/paradas/{parada['id']}/recolectar", headers=headers(transportista)
            )
        )
    return dict(await ok(await cliente.post("/transportista/llegada", headers=headers(transportista))))


async def _fedex_y_corea(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    admin: Usuario,
    lote_codigo: str,
    estudio_ids: list[int],
) -> None:
    lote = await session.scalar(select(Lote).where(Lote.codigo == lote_codigo))
    assert lote is not None
    dia = await flujos.proximo_dia_habil(session)
    await ok(
        await cliente.post(
            f"/administrativo/lotes/{lote.id}/retiro",
            json={"fecha_hora": flujos.slot(dia, 10)},
            headers=headers(admin),
        )
    )
    await ok(
        await cliente.post(f"/integraciones/fedex/lotes/{lote.id}/{security.token_webhook('lote', lote.id)}")
    )
    for eid in estudio_ids:
        await ok(
            await cliente.post(
                f"/administrativo/estudios/{eid}/datos-crudos",
                files={"archivo": (f"{eid}.fastq.gz", b"@SEQ\nACGT\n", "application/gzip")},
                headers=headers(admin),
            )
        )


# --- 1. Particular: todos los Estados hasta FINALIZADO ----------------------------------------


async def test_estudio_particular_recorre_todos_los_estados(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    transportista, bio = demo[RolUsuario.TRANSPORTISTA], demo[RolUsuario.BIOINFORMATICO]
    palermo = await _palermo(session)

    # E2 + E4 Médico Tratante
    pid, paciente = await _alta_paciente(cliente, session, medico)
    estudio = await flujos.alta_estudio(cliente, session, medico, pid, "Fabry", hallazgos=True)
    eid = estudio["id"]
    # E16 Administrativo, E8 Paciente
    assert (await flujos.emitir_presupuesto(cliente, admin, eid))["modalidad"] == "PARTICULAR"
    await flujos.pagar(cliente, paciente, eid)
    # E11 Paciente, Tomar Muestra en el Centro
    turno = await flujos.sacar_turno(
        cliente, paciente, eid, palermo, flujos.slot(await flujos.proximo_dia_habil(session), 9, 30)
    )
    await registrar_extraccion(session, turno["id"], Decimal("4"))

    # Otras 9 Muestras listas en el mismo Centro: el Lote se completa con 10 (E25)
    for _ in range(9):
        otro = await factories.paciente(session, medico)
        await factories.estudio_en(session, otro, medico, E.LISTO_PARA_RETIRAR, centro_id=palermo)

    # E23 + E24 + E25 Transportista
    await _orden_de_hoy(session, adaptadores, transportista)
    llegada = await _recolectar_y_entregar(cliente, transportista)
    assert llegada["recibidas"] == 10 and len(llegada["lotes_sellados"]) == 1

    # E20 + E21 Administrativo
    await _fedex_y_corea(cliente, session, admin, llegada["lotes_sellados"][0], [eid])

    # E27 + E28 Bioinformático
    pendiente = next(
        e
        for e in await ok(await cliente.get("/bioinformatico/pendientes", headers=headers(bio)))
        if e["id"] == eid
    )
    await ok(
        await cliente.post(
            f"/bioinformatico/estudios/{eid}/tomar",
            json={"version": pendiente["version"]},
            headers=headers(bio),
        )
    )
    resultado = await ok(
        await cliente.post(
            f"/bioinformatico/estudios/{eid}/resultado",
            json={
                "variantes": [{"gen": "GLA", "nomenclatura": GLA_PATOGENICA, "clasificacion": "PATOGENICA"}]
            },
            headers=headers(bio),
        )
    )
    assert resultado["tipo"] == "POSITIVO"

    # E13 Paciente
    visto = await ok(await cliente.get(f"/paciente/estudios/{eid}/resultado", headers=headers(paciente)))
    assert visto["tipo"] == "POSITIVO" and visto["pdf_url"]

    assert await _historial(cliente, admin, eid) == [
        "CREADO",
        "POR_PAGAR",
        "PAGADO",
        "TURNO_SACADO",
        "LISTO_PARA_RETIRAR",
        "EN_CAMINO_LAB_CENTRAL",
        "EN_LAB_CENTRAL",
        "EN_ESPERA_RETIRO",
        "EN_VIAJE_COREA",
        "EN_ANALISIS_BIOINFORMATICA",
        "EN_ANALISIS",
        "FINALIZADO",
    ]


# --- 2. Obra Social rechazada y reautorizada --------------------------------------------------


async def test_obra_social_rechazada_y_reautorizada(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    osps = await session.scalar(select(ObraSocial.id).where(ObraSocial.codigo_externo == "OSPS"))
    pid, paciente = await _alta_paciente(
        cliente, session, medico, obra_social_id=osps, nro_afiliado="OSPS-778899"
    )
    eid = (await flujos.alta_estudio(cliente, session, medico, pid))["id"]

    assert (await flujos.emitir_presupuesto(cliente, admin, eid))["modalidad"] == "OBRA_SOCIAL"
    await ok(
        await cliente.post(
            f"/administrativo/estudios/{eid}/rechazo",
            json={"motivo": "Prestación no incluida en el PMO"},
            headers=headers(admin),
        )
    )
    sentencia = generar_pdf("Sentencia", ["Se ordena la cobertura total del exoma clínico."])
    await ok(
        await cliente.post(
            f"/paciente/estudios/{eid}/reautorizacion",
            files={"archivo": ("sentencia.pdf", sentencia, "application/pdf")},
            headers=headers(paciente),
        )
    )
    await ok(await cliente.post(f"/administrativo/estudios/{eid}/autorizacion", headers=headers(admin)))
    await flujos.sacar_turno(
        cliente,
        paciente,
        eid,
        await _palermo(session),
        flujos.slot(await flujos.proximo_dia_habil(session), 11),
    )

    assert await _historial(cliente, admin, eid) == [
        "CREADO",
        "PENDIENTE_AUTORIZACION",
        "RECHAZADO",
        "PENDIENTE_AUTORIZACION",
        "AUTORIZADO",
        "TURNO_SACADO",
    ]
    pagos_paciente = await session.scalar(
        select(func.count())
        .select_from(MovimientoFinanciero)
        .where(MovimientoFinanciero.estudio_id == eid, MovimientoFinanciero.concepto == "PAGO_PACIENTE")
    )
    assert pagos_paciente == 0  # Autorizado equivale a pagado (E17)


# --- 3. Urgente: sella el Lote con menos de 10 Muestras ---------------------------------------


async def test_urgente_sella_lote_con_menos_de_10_y_sale_primero(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    transportista, bio = demo[RolUsuario.TRANSPORTISTA], demo[RolUsuario.BIOINFORMATICO]
    palermo = await _palermo(session)
    osps = await session.scalar(select(ObraSocial.id).where(ObraSocial.codigo_externo == "OSPS"))
    nacimiento = (ahora().date() - timedelta(days=45)).isoformat()
    pid, cuenta_padre = await _alta_paciente(
        cliente,
        session,
        medico,
        dni="58000111",
        nombre="Tomás",
        apellido="Ruiz",
        fecha_nacimiento=nacimiento,
        email="padre.de.tomas@test.com.ar",
        obra_social_id=osps,
        sintomas=[398152000, 8186001],
        diagnosticos=[
            {"patologia_id": await flujos.patologia_id(session, "Pompe"), "tipo_sospecha": "CLINICA"}
        ],
    )
    estudio = await flujos.alta_estudio(cliente, session, medico, pid, "Pompe")
    eid = estudio["id"]
    assert estudio["urgente"]

    # No saltea la autorización ni el pago (E11): sin autorizar no saca Turno
    await flujos.emitir_presupuesto(cliente, admin, eid)
    r = await cliente.post(
        "/paciente/turnos",
        json={
            "estudio_id": eid,
            "centro_id": palermo,
            "inicio": flujos.slot(await flujos.proximo_dia_habil(session), 9),
        },
        headers=headers(cuenta_padre),
    )
    assert r.status_code == 422
    await ok(await cliente.post(f"/administrativo/estudios/{eid}/autorizacion", headers=headers(admin)))
    turno = await flujos.sacar_turno(
        cliente, cuenta_padre, eid, palermo, flujos.slot(await flujos.proximo_dia_habil(session), 9)
    )
    await registrar_extraccion(session, turno["id"], Decimal("3"))

    # Un Estudio común también listo: el Lote se sella con 2 Muestras por el Urgente
    otro = await factories.estudio_en(
        session, await factories.paciente(session, medico), medico, E.LISTO_PARA_RETIRAR, centro_id=palermo
    )
    await _orden_de_hoy(session, adaptadores, transportista)
    llegada = await _recolectar_y_entregar(cliente, transportista)
    assert (
        llegada["recibidas"] == 2
        and len(llegada["lotes_sellados"]) == 1
        and llegada["lote_en_formacion"] is None
    )
    lotes = await ok(await cliente.get("/administrativo/lotes", headers=headers(admin)))
    assert lotes[0]["incluye_urgente"] and lotes[0]["cantidad_muestras"] == 2

    # FedEx retira en el horario programado aunque haya un Urgente (E20); en Bioinformática sale primero
    await _fedex_y_corea(cliente, session, admin, llegada["lotes_sellados"][0], [otro.id, eid])
    pendientes = await ok(await cliente.get("/bioinformatico/pendientes", headers=headers(bio)))
    assert [e["id"] for e in pendientes][:2] == [eid, otro.id]


# --- 4. Muestra de 1,5 ml: nueva extracción sin costo -----------------------------------------


async def test_muestra_de_1_5_ml_genera_reextraccion(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    medico, admin, transportista = (
        demo[RolUsuario.MEDICO_TRATANTE],
        demo[RolUsuario.ADMINISTRATIVO],
        demo[RolUsuario.TRANSPORTISTA],
    )
    palermo = await _palermo(session)
    pid, paciente = await _alta_paciente(cliente, session, medico)
    eid = (await flujos.alta_estudio(cliente, session, medico, pid))["id"]
    await flujos.emitir_presupuesto(cliente, admin, eid)
    await flujos.pagar(cliente, paciente, eid)
    dia = await flujos.proximo_dia_habil(session)
    turno = await flujos.sacar_turno(cliente, paciente, eid, palermo, flujos.slot(dia, 10))
    await registrar_extraccion(session, turno["id"], Decimal("1.5"))

    await _orden_de_hoy(session, adaptadores, transportista)
    llegada = await _recolectar_y_entregar(cliente, transportista)
    codigo = (await ok(await cliente.get(f"/administrativo/estudios/{eid}", headers=headers(admin))))[
        "codigo"
    ]
    assert llegada["volumen_insuficiente"] == [codigo] and llegada["lotes_sellados"] == []

    sol = await session.scalar(select(SolicitudReextraccion).where(SolicitudReextraccion.estudio_id == eid))
    assert sol is not None and sol.motivo == MotivoReextraccion.VOLUMEN_INSUFICIENTE
    assert await flujos.estado(cliente, admin, eid) == "PAGADO"

    # Mismo Estudio, sin costo: nuevo Turno y nueva Muestra (extracción 2), sin nuevo pago
    turno2 = await flujos.sacar_turno(cliente, paciente, eid, palermo, flujos.slot(dia, 10, 30))
    muestra2 = await registrar_extraccion(session, turno2["id"], Decimal("3"))
    assert muestra2.nro_extraccion == 2
    assert await flujos.estado(cliente, admin, eid) == "LISTO_PARA_RETIRAR"
    pagos = await session.scalar(
        select(func.count()).select_from(MovimientoFinanciero).where(MovimientoFinanciero.estudio_id == eid)
    )
    assert pagos == 1
    assert await session.scalar(select(func.count()).where(Turno.estudio_id == eid)) == 2
    paciente_db = await session.get(Paciente, pid)
    assert paciente_db is not None
    assert await _historial(cliente, admin, eid) == [
        "CREADO",
        "POR_PAGAR",
        "PAGADO",
        "TURNO_SACADO",
        "LISTO_PARA_RETIRAR",
        "EN_CAMINO_LAB_CENTRAL",
        "PAGADO",
        "TURNO_SACADO",
        "LISTO_PARA_RETIRAR",
    ]
