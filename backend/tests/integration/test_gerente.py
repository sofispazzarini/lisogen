"""`/gerente`: E30 Dar de alta Patología, E31 Modificar Patología, E32 Generar Cupón,
E33 Asignar Cupón a Médico Tratante."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RolUsuario, ServicioExterno
from app.integrations.mock import CuponesMock
from app.integrations.registro import Adaptadores
from app.models import Cupon, IntegracionLog, Notificacion, Patologia, Usuario
from app.services.comun import ahora
from tests import factories
from tests.factories import headers

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


async def test_generar_cupones_con_qr(
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
    assert all(
        c["codigo"].startswith("LG15-") and c["qr_url"].startswith("memoria://cupon_pdf/") for c in cupones
    )
    assert len({c["codigo"] for c in cupones}) == 3
    log = await session.scalar(
        select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.CUPONES)
    )
    assert log is not None and log.ok


async def test_generar_cupones_sin_qr_usa_codigo_numerico(
    cliente: httpx.AsyncClient, adaptadores: Adaptadores, demo: dict[RolUsuario, Usuario]
) -> None:
    """E32 excepción: si el módulo no genera el QR, el Cupón queda con código numérico."""
    adaptadores.cupones = CuponesMock(sin_qr=True)
    r = await cliente.post(
        "/gerente/cupones",
        json={"descuento_pct": 30, "cantidad": 2},
        headers=headers(demo[RolUsuario.GERENTE_MEDICO]),
    )
    assert all(c["qr_url"] is None and c["codigo"].isdigit() and len(c["codigo"]) == 10 for c in r.json())


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


async def test_generar_cupones_vencimiento_pasado(
    cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario]
) -> None:
    pasado = (ahora() - timedelta(days=1)).isoformat()
    r = await cliente.post(
        "/gerente/cupones",
        json={"descuento_pct": 10, "cantidad": 1, "vence_at": pasado},
        headers=headers(demo[RolUsuario.GERENTE_MEDICO]),
    )
    assert r.json()["code"] == "VENCIMIENTO_INVALIDO"


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
    vence = (ahora() + timedelta(hours=1)).isoformat()
    cid = (
        await cliente.post(
            "/gerente/cupones",
            json={"descuento_pct": 5, "cantidad": 1, "vence_at": vence},
            headers=headers(gerente),
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
