"""E23 Orden del Día, E24 Recolectar, E19 Seguir Muestra, E25 Confirmar llegada (Lotes) y E20 FedEx."""

from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import get_settings
from app.domain.enums import (
    EstadoEstudio,
    EstadoLote,
    EstadoMuestra,
    MotivoReextraccion,
    RolUsuario,
    ServicioExterno,
)
from app.integrations.registro import Adaptadores, Integraciones
from app.models import (
    Archivo,
    CentroExtraccion,
    Estudio,
    Feriado,
    IntegracionLog,
    Lote,
    Muestra,
    Notificacion,
    OrdenDelDia,
    Paciente,
    SolicitudReextraccion,
    Transportista,
    Usuario,
)
from app.services import logistica
from tests import factories, flujos
from tests.factories import headers
from tests.flujos import ok


@pytest.fixture
async def demo(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    return await factories.seed(session)


async def _centro(session: AsyncSession, nombre: str) -> int:
    cid = await session.scalar(select(CentroExtraccion.id).where(CentroExtraccion.nombre.contains(nombre)))
    assert cid is not None
    return cid


async def _lista(
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    centro: str,
    *,
    volumen: str = "4",
    urgente: bool = False,
) -> Estudio:
    p = await factories.paciente(session, demo[RolUsuario.MEDICO_TRATANTE])
    return await factories.estudio_en(
        session,
        p,
        demo[RolUsuario.MEDICO_TRATANTE],
        EstadoEstudio.LISTO_PARA_RETIRAR,
        centro_id=await _centro(session, centro),
        volumen_ml=Decimal(volumen),
        urgente=urgente,
    )


async def _orden_de_hoy(
    session: AsyncSession, adaptadores: Adaptadores, demo: dict[RolUsuario, Usuario]
) -> OrdenDelDia:
    t = await session.get(Transportista, demo[RolUsuario.TRANSPORTISTA].id)
    assert t is not None
    orden = await logistica.crear_orden(session, Integraciones(session, adaptadores), t, logistica.hoy())
    assert orden is not None
    return orden


async def _recolectar_todo(cliente: httpx.AsyncClient, transportista: Usuario) -> None:
    orden = await ok(await cliente.get("/transportista/orden-del-dia", headers=headers(transportista)))
    for parada in orden["paradas"]:
        await ok(
            await cliente.post(
                f"/transportista/paradas/{parada['id']}/recolectar", headers=headers(transportista)
            )
        )


# --- E23 Orden del Día ------------------------------------------------------------------------


async def test_orden_del_dia_por_provincia_y_ordenada(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    await _lista(session, demo, "Caballito")
    await _lista(session, demo, "Palermo")
    await _lista(session, demo, "Palermo")
    await _lista(session, demo, "La Plata")  # otra provincia: no entra en la Orden del Transportista de CABA
    await _orden_de_hoy(session, adaptadores, demo)

    orden = await ok(
        await cliente.get("/transportista/orden-del-dia", headers=headers(demo[RolUsuario.TRANSPORTISTA]))
    )
    assert orden["provincia"] == "Ciudad Autónoma de Buenos Aires"
    assert [(p["posicion"], p["centro"]["nombre"], p["muestras_listas"]) for p in orden["paradas"]] == [
        (1, "Centro de Extracción Palermo", 2),  # el más cercano al Laboratorio Central
        (2, "Centro de Extracción Caballito", 1),
    ]
    assert await session.scalar(
        select(IntegracionLog.id).where(IntegracionLog.servicio == ServicioExterno.OPTIMIZACION_RUTAS)
    )


async def test_sin_orden_en_feriado_ni_sin_muestras(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    ints = Integraciones(session, adaptadores)
    dia = await flujos.proximo_dia_habil(session)
    assert await logistica.generar_ordenes_del_dia(session, ints, dia) == []  # no hay Muestras listas
    await _lista(session, demo, "Palermo")
    session.add(Feriado(fecha=dia, descripcion="Feriado de prueba"))
    await session.flush()
    assert await logistica.generar_ordenes_del_dia(session, ints, dia) == []  # E23 excepción
    sabado = dia + timedelta(days=(5 - dia.weekday()) % 7 or 7)
    assert await logistica.generar_ordenes_del_dia(session, ints, sabado) == []
    otro = await flujos.proximo_dia_habil(session, (dia - date.today()).days + 1)
    generadas = await logistica.generar_ordenes_del_dia(session, ints, otro)
    assert len(generadas) == 1
    assert await logistica.generar_ordenes_del_dia(session, ints, otro) == []  # no se regenera (S8)

    r = await cliente.get("/transportista/orden-del-dia", headers=headers(demo[RolUsuario.TRANSPORTISTA]))
    assert r.status_code == 404 and r.json()["code"] == "SIN_ORDEN_DEL_DIA"


# --- E24 Recolectar y E19 Seguir Muestra -------------------------------------------------------


async def test_recolectar_en_orden_y_seguir_muestra(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    transportista, admin = demo[RolUsuario.TRANSPORTISTA], demo[RolUsuario.ADMINISTRATIVO]
    caballito = await _lista(session, demo, "Caballito")
    palermo = await _lista(session, demo, "Palermo")
    await _orden_de_hoy(session, adaptadores, demo)
    orden = await ok(await cliente.get("/transportista/orden-del-dia", headers=headers(transportista)))
    primera, segunda = orden["paradas"]

    paciente = await session.get(Paciente, palermo.paciente_id)
    assert paciente is not None
    muestras = await ok(
        await cliente.post(
            "/administrativo/muestras/buscar", json={"texto": paciente.apellido}, headers=headers(admin)
        )
    )
    assert [m["estudio_codigo"] for m in muestras] == [palermo.codigo]
    mid = muestras[0]["id"]
    ubic = await ok(await cliente.get(f"/administrativo/muestras/{mid}/ubicacion", headers=headers(admin)))
    assert (
        ubic["estado"] == "LISTO_PARA_RETIRAR"
        and "Palermo" in ubic["descripcion"]
        and ubic["transportista"] is None
    )

    r = await cliente.post(
        f"/transportista/paradas/{segunda['id']}/recolectar", headers=headers(transportista)
    )
    assert r.status_code == 409 and r.json()["code"] == "PARADA_FUERA_DE_ORDEN"
    orden = await ok(
        await cliente.post(
            f"/transportista/paradas/{primera['id']}/recolectar", headers=headers(transportista)
        )
    )
    assert orden["paradas"][0]["estado"] == "RECOGIDO" and orden["muestras_en_camino"] == 1
    r = await cliente.post(
        f"/transportista/paradas/{primera['id']}/recolectar", headers=headers(transportista)
    )
    assert r.json()["code"] == "PARADA_RECOGIDA"

    assert await flujos.estado(cliente, admin, palermo.id) == "EN_CAMINO_LAB_CENTRAL"
    assert await flujos.estado(cliente, admin, caballito.id) == "LISTO_PARA_RETIRAR"
    ubic = await ok(await cliente.get(f"/administrativo/muestras/{mid}/ubicacion", headers=headers(admin)))
    assert ubic["transportista"] == "Diego Molina" and Decimal(ubic["latitud"]) == Decimal("-34.588900")

    await ok(
        await cliente.post(
            "/transportista/posicion",
            json={"latitud": "-34.600000", "longitud": "-58.400000"},
            headers=headers(transportista),
        )
    )
    ubic = await ok(await cliente.get(f"/administrativo/muestras/{mid}/ubicacion", headers=headers(admin)))
    assert Decimal(ubic["latitud"]) == Decimal("-34.600000")

    r = await cliente.post(
        "/transportista/posicion", json={"latitud": "-95", "longitud": "0"}, headers=headers(transportista)
    )
    assert r.status_code == 422


# --- E25 Confirmar llegada --------------------------------------------------------------------


async def test_llegada_con_muestra_insuficiente_y_lote_abierto(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    transportista, admin = demo[RolUsuario.TRANSPORTISTA], demo[RolUsuario.ADMINISTRATIVO]
    buena = await _lista(session, demo, "Palermo", volumen="4")
    poca = await _lista(session, demo, "Palermo", volumen="1.5")
    await _orden_de_hoy(session, adaptadores, demo)
    await _recolectar_todo(cliente, transportista)

    llegada = await ok(await cliente.post("/transportista/llegada", headers=headers(transportista)))
    assert llegada["recibidas"] == 2
    assert llegada["volumen_insuficiente"] == [poca.codigo]
    assert llegada["lotes_sellados"] == [] and llegada["lote_en_formacion"] is not None

    assert await flujos.estado(cliente, admin, buena.id) == "EN_LAB_CENTRAL"
    assert await flujos.estado(cliente, admin, poca.id) == "PAGADO"  # nueva extracción sin costo
    m = await session.scalar(select(Muestra).where(Muestra.estudio_id == poca.id))
    assert m is not None and m.estado == EstadoMuestra.VOLUMEN_INSUFICIENTE and m.lote_id is None
    sol = await session.scalar(
        select(SolicitudReextraccion).where(SolicitudReextraccion.estudio_id == poca.id)
    )
    assert (
        sol is not None
        and sol.motivo == MotivoReextraccion.VOLUMEN_INSUFICIENTE
        and sol.solicitado_por is None
    )
    aviso = await session.scalar(
        select(Notificacion).where(
            Notificacion.estudio_id == poca.id, Notificacion.cuerpo.contains("1.50 ml")
        )
    )
    assert aviso is not None

    r = await cliente.post("/transportista/llegada", headers=headers(transportista))
    assert r.status_code == 409 and r.json()["code"] == "LLEGADA_CONFIRMADA"


async def test_lote_se_sella_con_10_y_el_resto_pasa_al_siguiente(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    transportista, admin = demo[RolUsuario.TRANSPORTISTA], demo[RolUsuario.ADMINISTRATIVO]
    estudios = [await _lista(session, demo, "Palermo") for _ in range(11)]
    await _orden_de_hoy(session, adaptadores, demo)
    await _recolectar_todo(cliente, transportista)
    llegada = await ok(await cliente.post("/transportista/llegada", headers=headers(transportista)))
    assert len(llegada["lotes_sellados"]) == 1 and llegada["lote_en_formacion"] is not None

    lotes = await ok(await cliente.get("/administrativo/lotes", headers=headers(admin)))
    por_estado = {lt["estado"]: lt for lt in lotes}
    sellado = por_estado["EN_ESPERA_RETIRO"]
    assert sellado["cantidad_muestras"] == 10 and not sellado["incluye_urgente"]
    assert sellado["csv_url"] and sellado["autorizacion_url"]
    assert por_estado["EN_FORMACION"]["cantidad_muestras"] == 1
    estados = [await flujos.estado(cliente, admin, e.id) for e in estudios]
    assert estados.count("EN_ESPERA_RETIRO") == 10 and estados.count("EN_LAB_CENTRAL") == 1

    lote = await session.get(Lote, sellado["id"])
    assert lote is not None and lote.csv_ministerio_id is not None
    csv_archivo = await session.get(Archivo, lote.csv_ministerio_id)
    assert csv_archivo is not None
    csv = adaptadores.storage.objetos[csv_archivo.storage_key][0].decode()  # type: ignore[attr-defined]
    assert csv.splitlines()[0] == "lote,estudio,nro_extraccion,volumen_ml,urgente,patologias"
    assert len(csv.splitlines()) == 11
    for e in estudios[:10]:
        p = await session.get(Paciente, e.paciente_id)
        assert p is not None and p.dni not in csv and p.apellido not in csv  # sin datos personales
    assert await session.scalar(
        select(IntegracionLog.id).where(IntegracionLog.servicio == ServicioExterno.MINISTERIO_SALUD)
    )
    aviso = await session.scalar(select(Notificacion).where(Notificacion.usuario_id == admin.id))
    assert aviso is not None and "sellado" in aviso.asunto


async def test_urgente_sella_el_lote_sin_esperar_10(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    transportista = demo[RolUsuario.TRANSPORTISTA]
    await _lista(session, demo, "Palermo")
    urgente = await _lista(session, demo, "Palermo", urgente=True)
    await _orden_de_hoy(session, adaptadores, demo)
    await _recolectar_todo(cliente, transportista)
    llegada = await ok(await cliente.post("/transportista/llegada", headers=headers(transportista)))
    assert len(llegada["lotes_sellados"]) == 1 and llegada["lote_en_formacion"] is None
    lote = await session.scalar(select(Lote).where(Lote.estado == EstadoLote.EN_ESPERA_RETIRO))
    assert lote is not None and lote.incluye_urgente
    assert await session.scalar(select(func.count()).where(Muestra.lote_id == lote.id)) == 2
    assert await flujos.estado(cliente, demo[RolUsuario.ADMINISTRATIVO], urgente.id) == "EN_ESPERA_RETIRO"


# --- E20 Programar retiro con FedEx -----------------------------------------------------------


async def _lote_sellado(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> tuple[int, Estudio]:
    urgente = await _lista(session, demo, "Palermo", urgente=True)
    await _orden_de_hoy(session, adaptadores, demo)
    await _recolectar_todo(cliente, demo[RolUsuario.TRANSPORTISTA])
    await ok(await cliente.post("/transportista/llegada", headers=headers(demo[RolUsuario.TRANSPORTISTA])))
    lote_id = await session.scalar(select(Lote.id).where(Lote.estado == EstadoLote.EN_ESPERA_RETIRO))
    assert lote_id is not None
    return lote_id, urgente


async def test_programar_retiro_y_webhook_de_fedex(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    admin = demo[RolUsuario.ADMINISTRATIVO]
    lote_id, urgente = await _lote_sellado(cliente, session, adaptadores, demo)
    dia = await flujos.proximo_dia_habil(session)
    sabado = dia + timedelta(days=(5 - dia.weekday()) % 7 or 7)
    for mal in (flujos.slot(dia, 19), flujos.slot(sabado, 10)):
        r = await cliente.post(
            f"/administrativo/lotes/{lote_id}/retiro", json={"fecha_hora": mal}, headers=headers(admin)
        )
        assert r.status_code == 422 and r.json()["code"] == "RETIRO_FUERA_DE_HORARIO"

    lote = await ok(
        await cliente.post(
            f"/administrativo/lotes/{lote_id}/retiro",
            json={"fecha_hora": flujos.slot(dia, 11)},
            headers=headers(admin),
        )
    )
    assert lote["retiro_programado_at"] is not None and lote["estado"] == "EN_ESPERA_RETIRO"
    log = await session.scalar(select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.FEDEX))
    assert log is not None and log.ok

    token = security.token_webhook("lote", lote_id)
    lote_db = await session.get(Lote, lote_id)
    assert lote_db is not None
    await session.refresh(lote_db)
    assert lote_db.fedex_url == f"{get_settings().api_public_url}/integraciones/fedex/lotes/{lote_id}/{token}"

    r = await cliente.post(f"/integraciones/fedex/lotes/{lote_id}/token-falso")
    assert r.status_code == 404
    await ok(await cliente.post(f"/integraciones/fedex/lotes/{lote_id}/{token}"))
    await ok(await cliente.post(f"/integraciones/fedex/lotes/{lote_id}/{token}"))  # idempotente
    assert await flujos.estado(cliente, admin, urgente.id) == "EN_VIAJE_COREA"
    await session.refresh(lote_db)
    assert lote_db.estado == EstadoLote.EN_VIAJE_COREA and lote_db.fedex_confirmado_at is not None
    m = await session.scalar(select(Muestra).where(Muestra.estudio_id == urgente.id))
    assert m is not None and m.estado == EstadoMuestra.EN_VIAJE_COREA
    ubic = await ok(await cliente.get(f"/administrativo/muestras/{m.id}/ubicacion", headers=headers(admin)))
    assert "Corea" in ubic["descripcion"]


async def test_no_se_programa_retiro_de_lote_sin_sellar(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    await _lista(session, demo, "Palermo")
    await _orden_de_hoy(session, adaptadores, demo)
    await _recolectar_todo(cliente, demo[RolUsuario.TRANSPORTISTA])
    await ok(await cliente.post("/transportista/llegada", headers=headers(demo[RolUsuario.TRANSPORTISTA])))
    lote_id = await session.scalar(select(Lote.id).where(Lote.estado == EstadoLote.EN_FORMACION))
    dia = await flujos.proximo_dia_habil(session)
    r = await cliente.post(
        f"/administrativo/lotes/{lote_id}/retiro",
        json={"fecha_hora": flujos.slot(dia, 11)},
        headers=headers(demo[RolUsuario.ADMINISTRATIVO]),
    )
    assert r.status_code == 409 and r.json()["code"] == "LOTE_NO_SELLADO"
    r = await cliente.post(
        f"/integraciones/fedex/lotes/{lote_id}/{security.token_webhook('lote', lote_id or 0)}"
    )
    assert r.status_code == 409


async def test_solo_transportista(cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario]) -> None:
    r = await cliente.get("/transportista/orden-del-dia", headers=headers(demo[RolUsuario.ADMINISTRATIVO]))
    assert r.status_code == 403
