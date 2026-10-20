"""`/avisos`: bandeja de Avisos (canal APP) de cada usuario."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import RolUsuario
from app.services.comun import notificar
from tests import factories
from tests.factories import headers


async def test_bandeja_de_avisos(cliente: httpx.AsyncClient, session: AsyncSession) -> None:
    yo = await factories.usuario(session, RolUsuario.ADMINISTRATIVO)
    otro = await factories.usuario(session, RolUsuario.ADMINISTRATIVO)
    notificar(session, yo.id, "Primero", "Cuerpo 1")
    notificar(session, yo.id, "Segundo", "Cuerpo 2")
    notificar(session, otro.id, "Ajeno", "No lo veo")
    await session.flush()

    r = await cliente.get("/avisos", headers=headers(yo))
    avisos = r.json()
    assert [a["asunto"] for a in avisos] == ["Segundo", "Primero"]  # sólo canal APP, más nuevos primero
    assert not any(a["leida"] for a in avisos)

    r = await cliente.post(f"/avisos/{avisos[0]['id']}/leido", headers=headers(yo))
    assert r.status_code == 200
    r = await cliente.get("/avisos", params={"solo_no_leidos": True}, headers=headers(yo))
    assert [a["asunto"] for a in r.json()] == ["Primero"]

    ajeno = (await cliente.get("/avisos", headers=headers(otro))).json()[0]["id"]
    r = await cliente.post(f"/avisos/{ajeno}/leido", headers=headers(yo))
    assert r.status_code == 404

    await cliente.post("/avisos/leidos", headers=headers(yo))
    r = await cliente.get("/avisos", params={"solo_no_leidos": True}, headers=headers(yo))
    assert r.json() == []


async def test_avisos_requiere_sesion(cliente: httpx.AsyncClient) -> None:
    assert (await cliente.get("/avisos")).status_code == 401
