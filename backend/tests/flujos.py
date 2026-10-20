"""Pasos de negocio por la API, reutilizados por los tests de integración y de punta a punta."""

from datetime import date, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.reglas import TZ_AR, es_dia_habil
from app.models import Feriado, Patologia, Usuario
from app.services.comun import ahora
from tests.factories import headers


async def ok(r: httpx.Response, status: int = 200) -> Any:
    assert r.status_code == status, f"{r.status_code}: {r.text}"
    return r.json()


async def patologia_id(session: AsyncSession, nombre: str) -> int:
    pid = await session.scalar(select(Patologia.id).where(Patologia.nombre == nombre))
    assert pid is not None
    return pid


async def proximo_dia_habil(session: AsyncSession, desde_dias: int = 1) -> date:
    no_habiles = set(await session.scalars(select(Feriado.fecha)))
    dia = ahora().astimezone(TZ_AR).date() + timedelta(days=desde_dias)
    while not es_dia_habil(dia, no_habiles):
        dia += timedelta(days=1)
    return dia


def slot(dia: date, hora: int, minuto: int = 0) -> str:
    return datetime(dia.year, dia.month, dia.day, hora, minuto, tzinfo=TZ_AR).isoformat()


async def alta_estudio(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    medico: Usuario,
    paciente_id: int,
    patologia: str = "Fabry",
    genes_manuales: list[str] | None = None,
    hallazgos: bool = False,
) -> dict[str, Any]:
    r = await cliente.post(
        "/medico/estudios",
        json={
            "paciente_id": paciente_id,
            "patologia_ids": [await patologia_id(session, patologia)],
            "genes_manuales": genes_manuales or [],
            "evalua_hallazgos_secundarios": hallazgos,
        },
        headers=headers(medico),
    )
    return dict(await ok(r, 201))


async def emitir_presupuesto(cliente: httpx.AsyncClient, admin: Usuario, estudio_id: int) -> dict[str, Any]:
    r = await cliente.post(f"/administrativo/estudios/{estudio_id}/presupuesto", headers=headers(admin))
    return dict(await ok(r))


async def pagar(cliente: httpx.AsyncClient, paciente: Usuario, estudio_id: int) -> dict[str, Any]:
    return dict(
        await ok(await cliente.post(f"/paciente/estudios/{estudio_id}/pagar", headers=headers(paciente)))
    )


async def sacar_turno(
    cliente: httpx.AsyncClient, paciente: Usuario, estudio_id: int, centro_id: int, inicio: str
) -> dict[str, Any]:
    r = await cliente.post(
        "/paciente/turnos",
        json={"estudio_id": estudio_id, "centro_id": centro_id, "inicio": inicio},
        headers=headers(paciente),
    )
    return dict(await ok(r, 201))


async def estado(cliente: httpx.AsyncClient, admin: Usuario, estudio_id: int) -> str:
    r = await cliente.get(f"/administrativo/estudios/{estudio_id}", headers=headers(admin))
    return str((await ok(r))["estado"])
