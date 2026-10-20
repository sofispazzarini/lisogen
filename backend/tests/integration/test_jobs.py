"""Tareas programadas: Orden del Día, cierre de jornada, recordatorios, despacho de mails y FedEx (mock)."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    CanalNotif,
    EstadoEstudio,
    EstadoLote,
    EstadoTurno,
    OrigenGen,
    RolUsuario,
    ServicioExterno,
    TipoArchivo,
)
from app.domain.reglas import TZ_AR
from app.integrations.infra import MailMemoria
from app.integrations.registro import Adaptadores, Integraciones
from app.jobs import tareas
from app.jobs.scheduler import PROGRAMACION, crear_scheduler
from app.models import (
    Archivo,
    CentroExtraccion,
    Estudio,
    EstudioGen,
    Feriado,
    Gen,
    IntegracionLog,
    Lote,
    Muestra,
    Notificacion,
    OrdenDelDia,
    Turno,
    Usuario,
)
from app.schemas.roles import TurnoEntrada
from app.services import finanzas, turnos
from app.services.comun import ahora, notificar
from app.services.extracciones import registrar_extraccion
from tests import factories, flujos


@pytest.fixture
async def demo(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    return await factories.seed(session)


@pytest.fixture
def ints(session: AsyncSession, adaptadores: Adaptadores) -> Integraciones:
    return Integraciones(session, adaptadores)


async def _con_turno(
    session: AsyncSession, ints: Integraciones, demo: dict[RolUsuario, Usuario], hora: int = 10
) -> tuple[Estudio, Turno]:
    """Estudio pagado con un Turno reservado para el próximo día hábil, por los servicios reales."""
    medico, admin = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.ADMINISTRATIVO]
    p = await factories.paciente(session, medico)
    cuenta = await session.get(Usuario, p.usuario_id)
    assert cuenta is not None
    estudio = await factories.estudio(session, p, medico)
    gla = await session.scalar(select(Gen).where(Gen.simbolo == "GLA"))
    assert gla is not None
    session.add(EstudioGen(estudio_id=estudio.id, gen_id=gla.id, origen=OrigenGen.API_PATOLOGIA))
    await finanzas.emitir_presupuesto(session, ints, admin, estudio)
    await finanzas.pagar(session, cuenta, estudio)
    centro = await session.scalar(select(CentroExtraccion.id).order_by(CentroExtraccion.id).limit(1))
    assert centro is not None
    dia = await flujos.proximo_dia_habil(session)
    inicio = datetime(dia.year, dia.month, dia.day, hora, 0, tzinfo=TZ_AR)
    salida = await turnos.sacar_turno(
        session, ints, cuenta, TurnoEntrada(estudio_id=estudio.id, centro_id=centro, inicio=inicio)
    )
    turno = await session.get(Turno, salida.id)
    assert turno is not None
    return estudio, turno


async def _vencer(session: AsyncSession, turno: Turno, dias: int = 60) -> None:
    await session.execute(
        text("UPDATE turno SET inicio = inicio - make_interval(days => :d) WHERE id = :id"),
        {"d": dias, "id": turno.id},
    )
    await session.refresh(turno)


# --- Orden del Día ----------------------------------------------------------------------------


async def test_orden_del_dia(
    session: AsyncSession, ints: Integraciones, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    await factories.estudio_en(
        session, await factories.paciente(session, medico), medico, EstadoEstudio.LISTO_PARA_RETIRAR
    )
    dia = await flujos.proximo_dia_habil(session)
    assert await tareas.generar_ordenes_del_dia(session, ints, dia) == 1
    assert await tareas.generar_ordenes_del_dia(session, ints, dia) == 0  # no se regenera
    feriado = await flujos.proximo_dia_habil(session, (dia - ahora().date()).days + 1)
    session.add(Feriado(fecha=feriado, descripcion="Feriado de prueba"))
    await session.flush()
    assert await tareas.generar_ordenes_del_dia(session, ints, feriado) == 0
    assert await session.scalar(select(func.count()).select_from(OrdenDelDia)) == 1


# --- Cierre de jornada ------------------------------------------------------------------------


async def test_cierre_de_jornada_marca_ausentes(
    session: AsyncSession, ints: Integraciones, demo: dict[RolUsuario, Usuario]
) -> None:
    vencido, turno_vencido = await _con_turno(session, ints, demo, hora=9)
    futuro, turno_futuro = await _con_turno(session, ints, demo, hora=10)
    con_muestra, turno_con_muestra = await _con_turno(session, ints, demo, hora=11)
    await registrar_extraccion(session, turno_con_muestra.id, Decimal("4"))
    await _vencer(session, turno_vencido)
    await _vencer(session, turno_con_muestra)

    assert await tareas.cierre_de_jornada(session, ints) == 1
    await session.refresh(turno_vencido)
    await session.refresh(turno_futuro)
    assert turno_vencido.estado == EstadoTurno.AUSENTE
    assert turno_futuro.estado == EstadoTurno.RESERVADO
    assert vencido.estado == EstadoEstudio.PAGADO and vencido.inasistencias == 1
    assert futuro.estado == EstadoEstudio.TURNO_SACADO
    assert con_muestra.estado == EstadoEstudio.LISTO_PARA_RETIRAR
    assert await tareas.cierre_de_jornada(session, ints) == 0


# --- Recordatorios ----------------------------------------------------------------------------


async def test_recordatorio_del_dia_anterior(
    session: AsyncSession, ints: Integraciones, demo: dict[RolUsuario, Usuario]
) -> None:
    estudio, turno = await _con_turno(session, ints, demo)
    programado = turno.recordatorio_at
    assert programado is not None
    await session.execute(
        update(Turno).where(Turno.id == turno.id).values(recordatorio_at=ahora() + timedelta(hours=1))
    )
    assert await tareas.enviar_recordatorios(session, ints) == 0  # todavía no es el momento

    await session.execute(
        update(Turno).where(Turno.id == turno.id).values(recordatorio_at=ahora() - timedelta(minutes=1))
    )
    await session.refresh(turno)
    assert await tareas.enviar_recordatorios(session, ints) == 1
    assert await tareas.enviar_recordatorios(session, ints) == 0  # no se repite
    aviso = await session.scalar(
        select(Notificacion).where(
            Notificacion.estudio_id == estudio.id,
            Notificacion.asunto.startswith("Recordatorio"),
            Notificacion.canal == CanalNotif.MAIL,
        )
    )
    assert aviso is not None and estudio.codigo in aviso.cuerpo


# --- Bandeja de salida de mails ---------------------------------------------------------------


async def test_despachar_mails_pendientes(
    session: AsyncSession, ints: Integraciones, mails: MailMemoria, demo: dict[RolUsuario, Usuario]
) -> None:
    admin = demo[RolUsuario.ADMINISTRATIVO]
    notificar(session, admin.id, "Asunto 1", "Cuerpo 1")
    notificar(session, admin.id, "Asunto 2", "Cuerpo 2")
    await session.flush()

    assert await tareas.despachar_mails(session, ints) == 2
    assert [(m.destinatario, m.asunto) for m in mails.enviados] == [
        ("administrativo@lisogen-demo.com.ar", "Asunto 1"),
        ("administrativo@lisogen-demo.com.ar", "Asunto 2"),
    ]
    pendientes = await session.scalar(
        select(func.count())
        .select_from(Notificacion)
        .where(Notificacion.canal == CanalNotif.MAIL, Notificacion.enviada_at.is_(None))
    )
    assert pendientes == 0
    assert await tareas.despachar_mails(session, ints) == 0
    logs = list(
        await session.scalars(select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.MAIL))
    )
    assert len(logs) == 2 and all("administrativo@" not in str(lg.request) for lg in logs)


async def test_mail_que_falla_queda_pendiente(
    session: AsyncSession, adaptadores: Adaptadores, demo: dict[RolUsuario, Usuario]
) -> None:
    class MailCaido:
        async def enviar(self, *, destinatario: str, asunto: str, cuerpo: str) -> None:
            raise ConnectionError("SMTP caído")

    adaptadores.mail = MailCaido()
    ints = Integraciones(session, adaptadores)
    notificar(session, demo[RolUsuario.ADMINISTRATIVO].id, "Asunto", "Cuerpo")
    await session.flush()
    assert await tareas.despachar_mails(session, ints) == 0
    log = await session.scalar(select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.MAIL))
    assert (
        log is not None
        and not log.ok
        and log.http_status == 502
        and log.response == {"error": "ConnectionError"}
    )
    pendiente = await session.scalar(select(Notificacion).where(Notificacion.canal == CanalNotif.MAIL))
    assert pendiente is not None and pendiente.enviada_at is None


# --- FedEx (mock) -----------------------------------------------------------------------------


async def test_fedex_mock_confirma_retiros_vencidos(
    session: AsyncSession, ints: Integraciones, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    estudio = await factories.estudio_en(
        session, await factories.paciente(session, medico), medico, EstadoEstudio.EN_ESPERA_RETIRO
    )
    archivo = Archivo(
        tipo=TipoArchivo.AUTORIZACION_MINISTERIO_PDF,
        nombre="a.pdf",
        mime="application/pdf",
        tamano_bytes=1,
        storage_key="x/fedex-test",
        sha256="0" * 64,
    )
    session.add(archivo)
    await session.flush()
    lote = Lote(
        codigo="LOTE-TEST-FEDEX",
        estado=EstadoLote.EN_ESPERA_RETIRO,
        sellado_at=ahora(),
        autorizacion_ministerio_id=archivo.id,
        retiro_programado_at=ahora() + timedelta(hours=2),
    )
    session.add(lote)
    await session.flush()
    await session.execute(update(Muestra).where(Muestra.estudio_id == estudio.id).values(lote_id=lote.id))

    assert await tareas.simular_fedex(session, ints) == 0  # todavía no es la hora
    lote.retiro_programado_at = ahora() - timedelta(minutes=1)
    await session.flush()
    assert await tareas.simular_fedex(session, ints) == 1
    await session.refresh(lote)
    assert lote.estado == EstadoLote.EN_VIAJE_COREA
    assert estudio.estado == EstadoEstudio.EN_VIAJE_COREA


# --- Programación -----------------------------------------------------------------------------


def test_programacion_del_scheduler() -> None:
    scheduler = crear_scheduler()
    assert {j.id for j in scheduler.get_jobs()} == set(tareas.TAREAS) == set(PROGRAMACION)
    orden = PROGRAMACION["orden_del_dia"]
    assert isinstance(orden, CronTrigger)
    campos = {f.name: str(f) for f in orden.fields}
    assert (campos["hour"], campos["minute"], campos["day_of_week"]) == ("6", "0", "mon-fri")
    assert str(orden.timezone) == "America/Argentina/Buenos_Aires"
