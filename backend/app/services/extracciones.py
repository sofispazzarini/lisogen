"""Tomar Muestra: el Centro de Extracción informa la Muestra tomada en el Turno.

DECISIONES C6: el Extraccionista no es un rol del sistema y el endpoint del Centro se implementa más
adelante. Este servicio lo usan el seed y los tests de punta a punta."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EstadoEstudio, EstadoTurno
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado
from app.models import Estudio, Muestra, Turno
from app.services.transiciones import transicionar


async def registrar_extraccion(session: AsyncSession, turno_id: int, volumen_ml: Decimal) -> Muestra:
    """Turno RESERVADO → REALIZADO; nueva Muestra LISTO_PARA_RETIRAR; Estudio → Listo para Retirar."""
    if volumen_ml <= 0:
        raise ErrorNegocio("VOLUMEN_INVALIDO", "El volumen de la Muestra tiene que ser mayor a cero.")
    turno = await session.get(Turno, turno_id, with_for_update=True)
    if turno is None:
        raise NoEncontrado("Turno")
    if turno.estado != EstadoTurno.RESERVADO:
        raise Conflicto("TURNO_NO_RESERVADO", "El Turno no está reservado.")
    estudio = await session.get(Estudio, turno.estudio_id)
    assert estudio is not None
    previas = int(await session.scalar(select(func.count()).where(Muestra.estudio_id == estudio.id)) or 0)
    turno.estado = EstadoTurno.REALIZADO
    muestra = Muestra(
        estudio_id=estudio.id, turno_id=turno.id, nro_extraccion=previas + 1, volumen_ml=volumen_ml
    )
    session.add(muestra)
    await session.flush()
    await transicionar(
        session,
        estudio,
        EstadoEstudio.LISTO_PARA_RETIRAR,
        None,
        f"Muestra tomada (extracción {muestra.nro_extraccion}, {volumen_ml} ml)",
    )
    return muestra
