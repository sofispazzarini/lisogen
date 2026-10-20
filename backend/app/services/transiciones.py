"""Único punto del sistema que cambia `estudio.estado` (ver models.estudio: el ORM lo hace cumplir)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.domain.enums import EstadoEstudio
from app.domain.errores import Conflicto
from app.domain.estados import SISTEMA, Actor, estado_habilitante, mensaje_notificacion, validar_transicion
from app.models import Estudio, EstudioEstadoHistorial, Paciente, Usuario
from app.models.estudio import permitir_cambio_de_estado
from app.services.comun import ahora, notificar


def _actor(usuario: Usuario | None) -> Actor:
    return SISTEMA if usuario is None else usuario.rol


async def registrar_alta(session: AsyncSession, estudio: Estudio, usuario: Usuario | None) -> None:
    """Primera fila del historial: el Estudio nace en CREADO (E4, E6)."""
    session.add(
        EstudioEstadoHistorial(
            estudio_id=estudio.id,
            estado_anterior=None,
            estado_nuevo=EstadoEstudio.CREADO,
            usuario_id=usuario.id if usuario else None,
            motivo="Alta del Estudio",
        )
    )


async def transicionar(
    session: AsyncSession,
    estudio: Estudio,
    destino: EstadoEstudio,
    actor: Usuario | None,
    motivo: str | None = None,
) -> None:
    """Valida origen→destino y rol, cambia el estado, escribe el historial y avisa (APP + MAIL)
    al Paciente y al Médico Tratante. `actor=None` = proceso automático del sistema."""
    origen = estudio.estado
    validar_transicion(origen, destino, _actor(actor), estudio.tipo)
    with permitir_cambio_de_estado():
        estudio.estado = destino
    if destino == EstadoEstudio.FINALIZADO:
        estudio.finalizado_at = ahora()
    session.add(
        EstudioEstadoHistorial(
            estudio_id=estudio.id,
            estado_anterior=origen,
            estado_nuevo=destino,
            usuario_id=actor.id if actor else None,
            motivo=motivo,
        )
    )
    try:
        await session.flush()
    except StaleDataError as e:
        raise Conflicto(
            "ESTUDIO_MODIFICADO",
            "Otra persona modificó el Estudio al mismo tiempo. Actualizá y probá de nuevo.",
        ) from e

    asunto, cuerpo = mensaje_notificacion(estudio.codigo, destino, motivo)
    paciente = await session.get(Paciente, estudio.paciente_id)
    destinatarios = {estudio.medico_tratante_id}
    if paciente is not None and paciente.usuario_id is not None:
        destinatarios.add(paciente.usuario_id)
    for usuario_id in sorted(destinatarios):
        notificar(session, usuario_id, asunto, cuerpo, estudio.id)


async def volver_a_habilitante(
    session: AsyncSession, estudio: Estudio, actor: Usuario | None, motivo: str
) -> EstadoEstudio:
    """SUPUESTO S11: vuelve al último PAGADO/AUTORIZADO del historial (cancelar Turno, re-extracción)."""
    historial = await session.scalars(
        select(EstudioEstadoHistorial.estado_nuevo)
        .where(EstudioEstadoHistorial.estudio_id == estudio.id)
        .order_by(EstudioEstadoHistorial.created_at, EstudioEstadoHistorial.id)
    )
    destino = estado_habilitante(list(historial))
    await transicionar(session, estudio, destino, actor, motivo)
    return destino
