"""Tareas programadas. Cada una recibe sesión e integraciones (así se prueban contra Postgres) y devuelve
cuántos elementos procesó. `ejecutar` las corre en su propia transacción para el scheduler y la CLI."""

import logging
from collections.abc import Awaitable, Callable
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import get_settings
from app.domain.enums import CanalNotif, EstadoLote, EstadoTurno
from app.domain.errores import ErrorNegocio
from app.domain.reglas import TZ_AR
from app.integrations.registro import Integraciones, get_adaptadores
from app.models import CentroExtraccion, Estudio, Lote, Muestra, Notificacion, Paciente, Turno, Usuario
from app.services import logistica, lotes, turnos
from app.services.comun import ahora, notificar

log = logging.getLogger("lisogen.jobs")

Tarea = Callable[[AsyncSession, Integraciones], Awaitable[int]]


async def generar_ordenes_del_dia(
    session: AsyncSession, ints: Integraciones, fecha: date | None = None
) -> int:
    """06:00 L–V (E23): una Orden del Día por Transportista; en feriados no se genera."""
    return len(await logistica.generar_ordenes_del_dia(session, ints, fecha or logistica.hoy()))


async def cierre_de_jornada(session: AsyncSession, ints: Integraciones) -> int:
    """Turnos RESERVADO vencidos y sin Muestra → AUSENTE e inasistencia (E11, SUPUESTO S12)."""
    vencidos = list(
        await session.scalars(
            select(Turno)
            .where(
                Turno.estado == EstadoTurno.RESERVADO,
                Turno.inicio < ahora(),
                ~select(Muestra.id).where(Muestra.turno_id == Turno.id).exists(),
            )
            .order_by(Turno.inicio)
            .with_for_update(skip_locked=True)
        )
    )
    procesados = 0
    for turno in vencidos:
        try:
            async with session.begin_nested():
                await turnos.registrar_inasistencia(session, turno)
            procesados += 1
        except (
            ErrorNegocio
        ) as e:  # p. ej. el Estudio cambió mientras tanto: se reintenta en el próximo cierre
            log.warning("No se registró la inasistencia del Turno %s: %s", turno.id, e.code)
    return procesados


async def enviar_recordatorios(session: AsyncSession, ints: Integraciones) -> int:
    """Recordatorio del Turno el día anterior (E11). SUPUESTO S25: `recordatorio_at` se vacía al enviarlo."""
    filas = await session.execute(
        select(Turno, Estudio, Paciente, CentroExtraccion)
        .join(Estudio, Estudio.id == Turno.estudio_id)
        .join(Paciente, Paciente.id == Estudio.paciente_id)
        .join(CentroExtraccion, CentroExtraccion.id == Turno.centro_id)
        .where(
            Turno.estado == EstadoTurno.RESERVADO,
            Turno.recordatorio_at.is_not(None),
            Turno.recordatorio_at <= ahora(),
            Turno.inicio > ahora(),
        )
        .with_for_update(of=Turno, skip_locked=True)
    )
    enviados = 0
    for turno, estudio, paciente, centro in filas:
        turno.recordatorio_at = None
        if paciente.usuario_id is None:
            continue
        cuando = turno.inicio.astimezone(TZ_AR).strftime("%d/%m a las %H:%M")
        notificar(
            session,
            paciente.usuario_id,
            f"Recordatorio: Turno de extracción el {cuando}",
            f"Te esperamos en {centro.nombre} ({centro.direccion}) para el Estudio {estudio.codigo}. "
            "Llevá tu DNI, la orden de extracción y el consentimiento informado firmado.",
            estudio.id,
        )
        enviados += 1
    return enviados


async def despachar_mails(session: AsyncSession, ints: Integraciones, limite: int = 50) -> int:
    """Bandeja de salida: envía los avisos MAIL pendientes. Si falla el SMTP, quedan pendientes para
    el próximo intento."""
    filas = await session.execute(
        select(Notificacion, Usuario.email)
        .join(Usuario, Usuario.id == Notificacion.usuario_id)
        .where(Notificacion.canal == CanalNotif.MAIL, Notificacion.enviada_at.is_(None))
        .order_by(Notificacion.id)
        .limit(limite)
        .with_for_update(of=Notificacion, skip_locked=True)
    )
    enviados = 0
    for notif, email in filas:
        try:
            await ints.mail.enviar(destinatario=email, asunto=notif.asunto, cuerpo=notif.cuerpo)
        except Exception as e:
            log.warning("No se pudo enviar la notificación %s: %s", notif.id, type(e).__name__)
            continue
        notif.enviada_at = ahora()
        enviados += 1
    return enviados


async def simular_fedex(session: AsyncSession, ints: Integraciones) -> int:
    """Sólo en modo mock: FedEx "confirma" en la URL del Lote los retiros cuya hora ya pasó (E20 ep. 4)."""
    if get_settings().integraciones_modo != "mock":
        return 0
    vencidos = list(
        await session.scalars(
            select(Lote.id).where(
                Lote.estado == EstadoLote.EN_ESPERA_RETIRO,
                Lote.retiro_programado_at.is_not(None),
                Lote.retiro_programado_at <= ahora(),
            )
        )
    )
    for lote_id in vencidos:
        await lotes.confirmar_retiro_fedex(session, lote_id, security.token_webhook("lote", lote_id))
    return len(vencidos)


TAREAS: dict[str, Tarea] = {
    "orden_del_dia": generar_ordenes_del_dia,
    "cierre_de_jornada": cierre_de_jornada,
    "recordatorios": enviar_recordatorios,
    "mails": despachar_mails,
    "fedex": simular_fedex,
}


async def ejecutar(nombre: str) -> int:
    """Corre una tarea en su propia transacción (scheduler y `python -m app.jobs <tarea>`)."""
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        try:
            cantidad = await TAREAS[nombre](session, Integraciones(session, get_adaptadores()))
            await session.commit()
        except Exception:
            await session.rollback()
            log.exception("Falló la tarea %s", nombre)
            raise
    if cantidad:
        log.info("Tarea %s: %s procesados", nombre, cantidad)
    return cantidad
