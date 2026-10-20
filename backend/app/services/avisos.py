"""Bandeja de Avisos (notificaciones canal APP) de cualquier rol."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CanalNotif
from app.domain.errores import NoEncontrado
from app.models import Notificacion, Usuario
from app.schemas.comun import Aviso
from app.services.comun import ahora


async def listar(session: AsyncSession, usuario: Usuario, solo_no_leidos: bool = False) -> list[Aviso]:
    consulta = select(Notificacion).where(
        Notificacion.usuario_id == usuario.id, Notificacion.canal == CanalNotif.APP
    )
    if solo_no_leidos:
        consulta = consulta.where(Notificacion.leida_at.is_(None))
    filas = await session.scalars(
        consulta.order_by(Notificacion.created_at.desc(), Notificacion.id.desc()).limit(100)
    )
    return [
        Aviso(
            id=n.id,
            asunto=n.asunto,
            cuerpo=n.cuerpo,
            estudio_id=n.estudio_id,
            leida=n.leida_at is not None,
            created_at=n.created_at,
        )
        for n in filas
    ]


async def marcar_leido(session: AsyncSession, usuario: Usuario, aviso_id: int) -> None:
    n = await session.get(Notificacion, aviso_id)
    if n is None or n.usuario_id != usuario.id or n.canal != CanalNotif.APP:
        raise NoEncontrado("Aviso")
    if n.leida_at is None:
        n.leida_at = ahora()


async def marcar_todos_leidos(session: AsyncSession, usuario: Usuario) -> None:
    for n in await session.scalars(
        select(Notificacion).where(
            Notificacion.usuario_id == usuario.id,
            Notificacion.canal == CanalNotif.APP,
            Notificacion.leida_at.is_(None),
        )
    ):
        n.leida_at = ahora()
