"""`/gerente`: E30 Dar de alta Patología, E31 Modificar Patología, E32 Generar Cupón,
E33 Asignar Cupón a Médico Tratante."""

import re
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RolUsuario, ServicioExterno
from app.integrations.ports import ErrorCupones
from app.integrations.registro import Adaptadores
from app.models import Cupon, IntegracionLog, Notificacion, Patologia, Usuario
from app.services.comun import ahora
from tests import factories
from tests.factories import headers
from tests.falsos import CuponesFalla

FIEBRE, CEFALEA, FATIGA, ANEMIA = 386661006, 25064002, 84229001, 271737000
ACROPARESTESIA, ANGIOQUERATOMA, HIPOHIDROSIS, CORNEA = 79256006, 254788004, 45004005, 420805002


@pytest.fixture
async def demo(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    return await factories.seed(session)


def _patologia(**cambios: Any) -> dict[str, Any]:
    return {
        "nombre": "Niemann-Pick C",
        "sintoma_cardinal_id": FIEBRE,
        "secundarios_ids": [CEFALEA, FATIGA],
        "es_pompe": False,
    } | cambios


# --- E30 / E31 --------------------------------------------------------------------------------


async def test_alta_de_patologia(cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario]) -> None:
    h = headers(demo[RolUsuario.GERENTE_MEDICO])
    r = await cliente.post("/gerente/patologias", json=_patologia(), headers=h)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["sintoma_cardinal"] == {"concept_id": FIEBRE, "termino": "Fiebre"}
    assert {s["termino"] for s in p["secundarios"]} == {"Cefalea", "Fatiga"}
    assert p["genes"] == []
    assert len((await cliente.get("/gerente/patologias", headers=h)).json()) == 6


@pytest.mark.parametrize(
    ("cambios", "code"),
    [
        ({"nombre": "fabry"}, "PATOLOGIA_EXISTENTE"),
        ({"secundarios_ids": [FIEBRE, CEFALEA]}, "SINTOMA_REPETIDO"),
        ({"secundarios_ids": [CEFALEA, CEFALEA]}, "SECUNDARIOS_INSUFICIENTES"),
        ({"sintoma_cardinal_id": 1}, "SINTOMA_DESCONOCIDO"),
        ({"secundarios_ids": [CEFALEA]}, "DATOS_INVALIDOS"),
        ({"nombre": ""}, "DATOS_INVALIDOS"),
    ],
)
async def test_alta_de_patologia_invalida(
    cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario], cambios: dict[str, Any], code: str
) -> None:
    r = await cliente.post(
        "/gerente/patologias", json=_patologia(**cambios), headers=headers(demo[RolUsuario.GERENTE_MEDICO])
    )
    assert r.json()["code"] == code
    assert r.status_code == (409 if code == "PATOLOGIA_EXISTENTE" else 422)


async def test_modificar_patologia_cambia_la_validacion_de_diagnostico(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    """E31: tras el cambio, Validar Diagnóstico (E2) usa los síntomas nuevos."""
    gerente, medico = demo[RolUsuario.GERENTE_MEDICO], demo[RolUsuario.MEDICO_TRATANTE]
    fabry = await session.scalar(select(Patologia.id).where(Patologia.nombre == "Fabry"))
    alta = {
        "dni": "40500600",
        "nombre": "Leo",
        "apellido": "Sosa",
        "fecha_nacimiento": "1980-01-01",
        "telefono": "1145551111",
        "email": "leo@test.com.ar",
        "resumen_historia_clinica": "Anemia y cansancio.",
        "sintomas": [ANEMIA, FATIGA],
        "diagnosticos": [{"patologia_id": fabry, "tipo_sospecha": "CLINICA"}],
    }
    r = await cliente.post("/medico/pacientes", json=alta, headers=headers(medico))
    assert r.json()["code"] == "DIAGNOSTICO_NO_VALIDADO"

    r = await cliente.put(
        f"/gerente/patologias/{fabry}",
        json=_patologia(
            nombre="Fabry", sintoma_cardinal_id=ACROPARESTESIA, secundarios_ids=[ANEMIA, FATIGA, CORNEA]
        ),
        headers=headers(gerente),
    )
    assert r.status_code == 200, r.text
    assert r.json()["genes"] == ["GLA"]  # los genes no cambian
    assert {s["concept_id"] for s in r.json()["secundarios"]} == {ANEMIA, FATIGA, CORNEA}

    r = await cliente.post("/medico/pacientes", json=alta, headers=headers(medico))
    assert r.status_code == 201, r.text


async def test_modificar_patologia_inexistente_o_nombre_de_otra(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    h = headers(demo[RolUsuario.GERENTE_MEDICO])
    r = await cliente.put("/gerente/patologias/9999", json=_patologia(), headers=h)
    assert r.status_code == 404 and r.json()["code"] == "PATOLOGIA_NO_ENCONTRADO"
    pompe = await session.scalar(select(Patologia.id).where(Patologia.nombre == "Pompe"))
    r = await cliente.put(f"/gerente/patologias/{pompe}", json=_patologia(nombre="Gaucher"), headers=h)
    assert r.status_code == 409


async def test_solo_gerente(cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario]) -> None:
    r = await cliente.post(
        "/gerente/patologias", json=_patologia(), headers=headers(demo[RolUsuario.MEDICO_TRATANTE])
    )
    assert r.status_code == 403


# --- E32 Generar Cupón ------------------------------------------------------------------------


async def test_generar_cupones(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    r = await cliente.post(
        "/gerente/cupones",
        json={"descuento_pct": 15, "cantidad": 3},
        headers=headers(demo[RolUsuario.GERENTE_MEDICO]),
    )
    assert r.status_code == 201, r.text
    cupones = r.json()
    assert len(cupones) == 3
    assert all(c["estado"] == "DISPONIBLE" and c["descuento_pct"] == 15 for c in cupones)
    assert all(re.fullmatch(r"[0-9a-f]{8}", c["codigo"]) for c in cupones)
    assert all(c["qr_url"].startswith("memoria://cupon_pdf/") for c in cupones)  # PDF con QR de LisoGen
    assert len({c["codigo"] for c in cupones}) == 3
    vence = datetime.fromisoformat(cupones[0]["vence_at"])
    assert timedelta(days=29, hours=23) < vence - ahora() <= timedelta(days=30)  # lo fija la API
    log = await session.scalar(
        select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.CUPONES)
    )
    assert log is not None and log.ok and log.operacion == "generar"


@pytest.mark.parametrize(
    ("error", "estado", "codigo"),
    [
        (ErrorCupones("HTTP 403", status=403), 422, "CUPON_SIN_PERMISO"),
        (ErrorCupones("HTTP 400", status=400), 422, "CUPON_INVALIDO"),
        (ErrorCupones("sin respuesta", incierto=True), 502, "CUPONES_SIN_RESPUESTA"),
        (ErrorCupones("HTTP 503", status=503, incierto=True), 502, "CUPONES_SIN_RESPUESTA"),
    ],
)
async def test_generar_cupones_rechazado_por_la_api_no_guarda_nada(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
    error: ErrorCupones,
    estado: int,
    codigo: str,
) -> None:
    adaptadores.cupones = CuponesFalla("generar", error)
    r = await cliente.post(
        "/gerente/cupones",
        json={"descuento_pct": 30, "cantidad": 2},
        headers=headers(demo[RolUsuario.GERENTE_MEDICO]),
    )
    assert r.status_code == estado and r.json()["code"] == codigo
    assert await session.scalar(select(func.count()).select_from(Cupon)) == 0


@pytest.mark.parametrize(
    "datos",
    [
        {"descuento_pct": 0, "cantidad": 1},
        {"descuento_pct": 101, "cantidad": 1},
        {"descuento_pct": 10, "cantidad": 0},
    ],
)
async def test_generar_cupones_invalidos(
    cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario], datos: dict[str, int]
) -> None:
    r = await cliente.post("/gerente/cupones", json=datos, headers=headers(demo[RolUsuario.GERENTE_MEDICO]))
    assert r.status_code == 422


# --- E33 Asignar Cupón a Médico Tratante ------------------------------------------------------


async def test_asignar_cupones_a_medico(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    gerente, medico = demo[RolUsuario.GERENTE_MEDICO], demo[RolUsuario.MEDICO_TRATANTE]
    h = headers(gerente)
    ids = [
        c["id"]
        for c in (
            await cliente.post("/gerente/cupones", json={"descuento_pct": 25, "cantidad": 3}, headers=h)
        ).json()
    ]

    r = await cliente.post(
        "/gerente/cupones/asignar", json={"cupon_ids": ids[:2], "medico_id": medico.id}, headers=h
    )
    assert r.status_code == 200
    medicos = (await cliente.get("/gerente/medicos", headers=h)).json()
    assert next(m for m in medicos if m["id"] == medico.id)["cupones_disponibles"] == 2

    estados = {c["id"]: c for c in (await cliente.get("/gerente/cupones", headers=h)).json()}
    assert estados[ids[0]]["estado"] == "ASIGNADO_MEDICO" and estados[ids[0]]["medico"] == "Lucía Ferreyra"
    assert estados[ids[2]]["estado"] == "DISPONIBLE"

    aviso = await session.scalar(select(Notificacion).where(Notificacion.usuario_id == medico.id))
    assert aviso is not None and "2 Cupón" in aviso.cuerpo

    r = await cliente.post(
        "/gerente/cupones/asignar", json={"cupon_ids": ids[:1], "medico_id": medico.id}, headers=h
    )
    assert r.status_code == 409 and r.json()["code"] == "CUPON_ESTADO_INVALIDO"


async def test_asignar_cupones_validaciones(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    gerente = demo[RolUsuario.GERENTE_MEDICO]
    h = headers(gerente)
    cid = (
        await cliente.post("/gerente/cupones", json={"descuento_pct": 5, "cantidad": 1}, headers=h)
    ).json()[0]["id"]
    r = await cliente.post(
        "/gerente/cupones/asignar", json={"cupon_ids": [cid], "medico_id": gerente.id}, headers=h
    )
    assert r.status_code == 404  # el Gerente no es Médico Tratante
    r = await cliente.post(
        "/gerente/cupones/asignar",
        json={"cupon_ids": [cid, 99999], "medico_id": demo[RolUsuario.MEDICO_TRATANTE].id},
        headers=h,
    )
    assert r.status_code == 404
    cupon = await session.get(Cupon, cid)
    assert cupon is not None and cupon.medico_asignado_id is None


async def test_cupon_vencido_no_se_asigna(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    gerente = demo[RolUsuario.GERENTE_MEDICO]
    cid = (
        await cliente.post(
            "/gerente/cupones", json={"descuento_pct": 5, "cantidad": 1}, headers=headers(gerente)
        )
    ).json()[0]["id"]
    await session.execute(
        Cupon.__table__.update().where(Cupon.id == cid).values(vence_at=ahora() - timedelta(minutes=1))
    )
    r = await cliente.post(
        "/gerente/cupones/asignar",
        json={"cupon_ids": [cid], "medico_id": demo[RolUsuario.MEDICO_TRATANTE].id},
        headers=headers(gerente),
    )
    assert r.status_code == 409 and r.json()["code"] == "CUPON_VENCIDO"
    listado = (await cliente.get("/gerente/cupones", headers=headers(gerente))).json()
    assert next(c for c in listado if c["id"] == cid)["estado"] == "VENCIDO"
    assert await session.scalar(select(func.count()).select_from(Cupon)) == 1


async def test_asignar_cupones_si_la_api_falla_a_mitad_quedan_los_ya_asignados(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    """Lo que la API de Cupones ya asignó se confirma acá aunque el siguiente Cupón falle."""
    gerente, medico = demo[RolUsuario.GERENTE_MEDICO], demo[RolUsuario.MEDICO_TRATANTE]
    h = headers(gerente)
    ids = [
        c["id"]
        for c in (
            await cliente.post("/gerente/cupones", json={"descuento_pct": 25, "cantidad": 3}, headers=h)
        ).json()
    ]
    adaptadores.cupones = CuponesFalla("asignar_a_medico", ErrorCupones("HTTP 404", status=404), desde=2)
    r = await cliente.post(
        "/gerente/cupones/asignar", json={"cupon_ids": ids, "medico_id": medico.id}, headers=h
    )
    assert r.status_code == 422 and r.json()["code"] == "CUPON_INVALIDO"
    estados = {c["id"]: c["estado"] for c in (await cliente.get("/gerente/cupones", headers=h)).json()}
    assert sorted(estados.values()) == ["ASIGNADO_MEDICO", "DISPONIBLE", "DISPONIBLE"]


async def test_asignar_cupon_a_medico_con_api_sin_respuesta_no_cambia_nada(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    gerente, medico = demo[RolUsuario.GERENTE_MEDICO], demo[RolUsuario.MEDICO_TRATANTE]
    h = headers(gerente)
    cid = (
        await cliente.post("/gerente/cupones", json={"descuento_pct": 5, "cantidad": 1}, headers=h)
    ).json()[0]["id"]
    adaptadores.cupones = CuponesFalla("asignar_a_medico", ErrorCupones("timeout", incierto=True))
    r = await cliente.post(
        "/gerente/cupones/asignar", json={"cupon_ids": [cid], "medico_id": medico.id}, headers=h
    )
    assert r.status_code == 502 and r.json()["code"] == "CUPONES_SIN_RESPUESTA"
    cupon = await session.get(Cupon, cid)
    assert cupon is not None
    await session.refresh(cupon)
    assert cupon.medico_asignado_id is None
    