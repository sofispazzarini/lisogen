"""E11 Sacar Turno, E12 Cancelar Turno e inasistencias (las registra el cierre de jornada, etapa 5)."""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EstadoEstudio, EstadoTurno, TipoArchivo, TipoEstudio
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado
from app.domain.estados import HABILITANTES
from app.domain.reglas import (
    TZ_AR,
    VENTANA_RESERVA_DIAS,
    es_dia_habil,
    momento_recordatorio,
    pierde_pago,
    slots_del_dia,
    validar_slot,
)
from app.integrations.pdf import generar_pdf
from app.integrations.registro import Integraciones
from app.models import (
    CentroExtraccion,
    Estudio,
    EstudioGen,
    Muestra,
    Paciente,
    Provincia,
    Turno,
    Usuario,
)
from app.schemas.comun import CentroSalida, TurnoSalida
from app.schemas.roles import AgendaDia, Slot, TurnoEntrada
from app.services import consultas
from app.services.comun import ahora, feriados, guardar_archivo
from app.services.estudios import estudio_del_paciente
from app.services.finanzas import perder_pago
from app.services.transiciones import transicionar, volver_a_habilitante

OCUPAN_SLOT = (EstadoTurno.RESERVADO, EstadoTurno.REALIZADO)


async def centros(session: AsyncSession) -> list[CentroSalida]:
    filas = await session.execute(
        select(CentroExtraccion, Provincia.nombre)
        .join(Provincia, Provincia.id == CentroExtraccion.provincia_id)
        .where(CentroExtraccion.activo.is_(True))
        .order_by(Provincia.nombre, CentroExtraccion.nombre)
    )
    return [
        CentroSalida(
            id=c.id,
            nombre=c.nombre,
            direccion=c.direccion,
            provincia=p,
            latitud=c.latitud,
            longitud=c.longitud,
        )
        for c, p in filas
    ]


async def _centro_activo(session: AsyncSession, centro_id: int) -> CentroExtraccion:
    centro = await session.get(CentroExtraccion, centro_id)
    if centro is None or not centro.activo:
        raise NoEncontrado("Centro de Extracción")
    return centro


async def agenda(session: AsyncSession, centro_id: int, dia: date) -> AgendaDia:
    """Grilla de un día: slots de 15' con su disponibilidad (los pasados figuran ocupados)."""
    await _centro_activo(session, centro_id)
    hoy = ahora().astimezone(TZ_AR).date()
    if dia < hoy or dia > hoy + timedelta(days=VENTANA_RESERVA_DIAS):
        return AgendaDia(fecha=dia, habil=False, slots=[])
    no_habiles = await feriados(session, dia, dia)
    slots = slots_del_dia(dia, no_habiles)
    if not slots:
        return AgendaDia(fecha=dia, habil=es_dia_habil(dia, no_habiles), slots=[])
    tomados = set(
        await session.scalars(
            select(Turno.inicio).where(
                Turno.centro_id == centro_id,
                Turno.estado.in_(OCUPAN_SLOT),
                Turno.inicio.between(slots[0], slots[-1]),
            )
        )
    )
    momento = ahora()
    return AgendaDia(
        fecha=dia, habil=True, slots=[Slot(inicio=s, libre=s not in tomados and s > momento) for s in slots]
    )


def _documentos(
    paciente: Paciente, estudio: Estudio, centro: CentroExtraccion, turno: Turno, genes: int
) -> tuple[bytes, bytes]:
    cuando = turno.inicio.astimezone(TZ_AR).strftime("%d/%m/%Y %H:%M")
    orden = generar_pdf(
        "Orden de extracción",
        [
            f"Paciente: {paciente.nombre_completo} - DNI {paciente.dni}",
            f"Estudio: {estudio.codigo} (exoma clínico, {genes} genes a analizar)",
            f"Centro de Extracción: {centro.nombre} - {centro.direccion}",
            f"Turno: {cuando} (hora Argentina)",
            "",
            "Muestra: sangre entera en tubo con EDTA, volumen mínimo 2 ml.",
            "Presentá esta orden, tu DNI y el consentimiento informado firmado.",
        ],
    )
    consentimiento = generar_pdf(
        "Consentimiento informado",
        [
            f"Yo, {paciente.nombre_completo}, DNI {paciente.dni}, o mi representante legal,",
            f"autorizo la extracción de sangre y el análisis genético del Estudio {estudio.codigo}.",
            "",
            "Entiendo que la Muestra viaja al exterior para su secuenciación, que los datos genéticos son",
            "datos sensibles protegidos por la Ley 25.326, y que el Resultado lo recibe mi Médico Tratante.",
            "Puedo revocar este consentimiento antes de que la Muestra sea enviada.",
            "",
            "Firma: ______________________    Aclaración: ______________________    Fecha: ___/___/______",
        ],
    )
    return orden, consentimiento


async def sacar_turno(
    session: AsyncSession, ints: Integraciones, usuario: Usuario, datos: TurnoEntrada
) -> TurnoSalida:
    """E11: sólo con el Estudio Pagado o Autorizado (aunque sea Urgente). Genera orden de extracción y
    consentimiento, y programa el recordatorio del día anterior."""
    estudio = await estudio_del_paciente(session, usuario, datos.estudio_id)
    if estudio.tipo != TipoEstudio.EXOMA or estudio.estado not in HABILITANTES:
        raise ErrorNegocio(
            "ESTUDIO_NO_HABILITADO",
            "Podés sacar Turno cuando el Estudio está Pagado o Autorizado por la Obra Social.",
        )
    centro = await _centro_activo(session, datos.centro_id)
    dia = datos.inicio.astimezone(TZ_AR).date()
    validar_slot(datos.inicio, await feriados(session, dia, dia), ahora())
    if await consultas.turno_activo(session, estudio.id) is not None:
        raise Conflicto("TURNO_ACTIVO", "El Estudio ya tiene un Turno reservado.")
    ocupado = await session.scalar(
        select(Turno.id).where(
            Turno.centro_id == centro.id, Turno.inicio == datos.inicio, Turno.estado.in_(OCUPAN_SLOT)
        )
    )
    if ocupado is not None:
        raise Conflicto("TURNO_OCUPADO", "Ese horario ya fue reservado. Elegí otro.")

    turno = Turno(
        estudio_id=estudio.id,
        centro_id=centro.id,
        inicio=datos.inicio,
        recordatorio_at=momento_recordatorio(datos.inicio),
    )
    session.add(turno)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as e:  # otra reserva ganó el mismo slot entre la consulta y el insert
        raise Conflicto("TURNO_OCUPADO", "Ese horario ya fue reservado. Elegí otro.") from e

    paciente = await session.get(Paciente, estudio.paciente_id)
    assert paciente is not None
    genes = int(await session.scalar(select(func.count()).where(EstudioGen.estudio_id == estudio.id)) or 0)
    orden, consentimiento = _documentos(paciente, estudio, centro, turno, genes)
    turno.orden_archivo_id = (
        await guardar_archivo(
            session,
            ints,
            tipo=TipoArchivo.ORDEN_EXTRACCION_PDF,
            nombre=f"orden-{estudio.codigo}.pdf",
            mime="application/pdf",
            contenido=orden,
            subido_por=None,
        )
    ).id
    turno.consentimiento_id = (
        await guardar_archivo(
            session,
            ints,
            tipo=TipoArchivo.CONSENTIMIENTO_PDF,
            nombre=f"consentimiento-{estudio.codigo}.pdf",
            mime="application/pdf",
            contenido=consentimiento,
            subido_por=None,
        )
    ).id
    cuando = datos.inicio.astimezone(TZ_AR).strftime("%d/%m/%Y %H:%M")
    await transicionar(
        session, estudio, EstadoEstudio.TURNO_SACADO, usuario, f"Turno en {centro.nombre} el {cuando}"
    )
    return await consultas.turno_salida(session, ints, turno)


async def _turno_del_paciente(
    session: AsyncSession, usuario: Usuario, turno_id: int
) -> tuple[Turno, Estudio]:
    turno = await session.get(Turno, turno_id)
    if turno is None:
        raise NoEncontrado("Turno")
    estudio = await estudio_del_paciente(session, usuario, turno.estudio_id)
    return turno, estudio


async def turno_del_estudio(
    session: AsyncSession, ints: Integraciones, usuario: Usuario, estudio_id: int
) -> TurnoSalida:
    estudio = await estudio_del_paciente(session, usuario, estudio_id)
    turno = await consultas.turno_activo(session, estudio.id)
    if turno is None:
        raise NoEncontrado("Turno")
    return await consultas.turno_salida(session, ints, turno)


async def cancelar_turno(session: AsyncSession, usuario: Usuario, turno_id: int) -> EstadoEstudio:
    """E12: libera el horario y el Estudio vuelve a Pagado o Autorizado para sacar otro Turno."""
    turno, estudio = await _turno_del_paciente(session, usuario, turno_id)
    if turno.estado != EstadoTurno.RESERVADO:
        raise Conflicto("TURNO_NO_RESERVADO", "Ese Turno ya no está reservado.")
    if turno.inicio <= ahora():
        raise Conflicto("TURNO_PASADO", "No se puede cancelar un Turno que ya empezó.")
    turno.estado, turno.cancelado_at = EstadoTurno.CANCELADO, ahora()
    return await volver_a_habilitante(session, estudio, usuario, "Turno cancelado por el Paciente")


async def registrar_inasistencia(session: AsyncSession, turno: Turno) -> EstadoEstudio:
    """E11 excepciones / SUPUESTO S12: el Turno vencido sin Muestra pasa a AUSENTE. Con la quinta
    inasistencia se pierde el pago (SUPUESTO S9) y el Estudio vuelve a Por Pagar."""
    if turno.estado != EstadoTurno.RESERVADO or turno.inicio > ahora():
        raise Conflicto("TURNO_NO_VENCIDO", "El Turno no está vencido.")
    if await session.scalar(select(Muestra.id).where(Muestra.turno_id == turno.id)) is not None:
        raise Conflicto("TURNO_CON_MUESTRA", "El Turno tiene una Muestra registrada.")
    estudio = await session.get(Estudio, turno.estudio_id, with_for_update=True)
    assert estudio is not None
    turno.estado = EstadoTurno.AUSENTE
    if pierde_pago(estudio.inasistencias):
        monto = await perder_pago(session, estudio)
        estudio.inasistencias = 0
        await transicionar(
            session,
            estudio,
            EstadoEstudio.POR_PAGAR,
            None,
            f"5 inasistencias: se perdió el pago de USD {monto}. Hay que volver a pagar el Presupuesto.",
        )
        return EstadoEstudio.POR_PAGAR
    estudio.inasistencias += 1
    return await volver_a_habilitante(
        session, estudio, None, f"Inasistencia {estudio.inasistencias} de 5. Podés sacar un nuevo Turno."
    )
