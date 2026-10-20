"""Lecturas compartidas: resúmenes y detalle de Estudios para las tablas y fichas de cada rol."""

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.enums import EstadoReaut, EstadoTurno, ResultadoOS
from app.domain.estados import etiqueta
from app.integrations.registro import Integraciones
from app.models import (
    AutorizacionObraSocial,
    CentroExtraccion,
    Cupon,
    Estudio,
    EstudioEstadoHistorial,
    EstudioGen,
    EstudioPatologia,
    Gen,
    ObraSocial,
    Paciente,
    Pago,
    Patologia,
    Presupuesto,
    Resultado,
    SolicitudReautorizacion,
    Turno,
    Usuario,
)
from app.schemas.comun import (
    EstudioDetalle,
    EstudioResumen,
    GenEstudio,
    HistorialItem,
    PersonaResumen,
    PresupuestoSalida,
    TurnoSalida,
)
from app.services.comun import url_archivo

Medico = aliased(Usuario)


async def _patologias_por_estudio(session: AsyncSession, ids: Sequence[int]) -> dict[int, list[str]]:
    filas = await session.execute(
        select(EstudioPatologia.estudio_id, Patologia.nombre)
        .join(Patologia, Patologia.id == EstudioPatologia.patologia_id)
        .where(EstudioPatologia.estudio_id.in_(ids))
        .order_by(Patologia.nombre)
    )
    res: dict[int, list[str]] = defaultdict(list)
    for estudio_id, nombre in filas:
        res[estudio_id].append(nombre)
    return res


async def resumenes(
    session: AsyncSession,
    *filtros: ColumnElement[bool],
    orden: Sequence[Any] | None = None,
    limite: int = 500,
) -> list[EstudioResumen]:
    consulta = (
        select(Estudio, Paciente, Medico)
        .join(Paciente, Paciente.id == Estudio.paciente_id)
        .join(Medico, Medico.id == Estudio.medico_tratante_id)
        .where(*filtros)
        .order_by(*(orden or [Estudio.urgente.desc(), Estudio.created_at.desc(), Estudio.id.desc()]))
        .limit(limite)
    )
    filas = (await session.execute(consulta)).all()
    patologias = await _patologias_por_estudio(session, [e.id for e, _, _ in filas])
    return [
        EstudioResumen(
            id=e.id,
            codigo=e.codigo,
            tipo=e.tipo,
            estado=e.estado,
            estado_etiqueta=etiqueta(e.estado),
            urgente=e.urgente,
            created_at=e.created_at,
            paciente=PersonaResumen(id=p.id, nombre_completo=p.nombre_completo),
            medico_tratante=PersonaResumen(id=m.id, nombre_completo=m.nombre_completo),
            patologias=patologias.get(e.id, []),
            version=e.version,
        )
        for e, p, m in filas
    ]


async def resumen(session: AsyncSession, estudio_id: int) -> EstudioResumen:
    return (await resumenes(session, Estudio.id == estudio_id))[0]


async def genes_del_estudio(session: AsyncSession, estudio_id: int) -> list[GenEstudio]:
    filas = await session.execute(
        select(Gen.simbolo, EstudioGen.origen, Patologia.nombre)
        .join(Gen, Gen.id == EstudioGen.gen_id)
        .outerjoin(Patologia, Patologia.id == EstudioGen.patologia_id)
        .where(EstudioGen.estudio_id == estudio_id)
        .order_by(EstudioGen.origen, Gen.simbolo)
    )
    return [GenEstudio(simbolo=s, origen=o.value, patologia=p) for s, o, p in filas]


async def historial(session: AsyncSession, estudio_id: int) -> list[HistorialItem]:
    filas = await session.execute(
        select(EstudioEstadoHistorial, Usuario)
        .outerjoin(Usuario, Usuario.id == EstudioEstadoHistorial.usuario_id)
        .where(EstudioEstadoHistorial.estudio_id == estudio_id)
        .order_by(EstudioEstadoHistorial.created_at, EstudioEstadoHistorial.id)
    )
    return [
        HistorialItem(
            estado_anterior=h.estado_anterior,
            estado_nuevo=h.estado_nuevo,
            estado_etiqueta=etiqueta(h.estado_nuevo),
            motivo=h.motivo,
            actor="Sistema"
            if u is None
            else f"{u.nombre_completo} ({u.rol.value.replace('_', ' ').title()})",
            created_at=h.created_at,
        )
        for h, u in filas
    ]


async def pago_vigente(session: AsyncSession, presupuesto_id: int) -> Pago | None:
    return await session.scalar(
        select(Pago).where(Pago.presupuesto_id == presupuesto_id, Pago.anulado_at.is_(None))
    )


async def presupuesto_salida(session: AsyncSession, estudio_id: int) -> PresupuestoSalida | None:
    fila = (
        await session.execute(
            select(Presupuesto, ObraSocial.nombre, Cupon.codigo)
            .outerjoin(ObraSocial, ObraSocial.id == Presupuesto.obra_social_id)
            .outerjoin(Cupon, Cupon.id == Presupuesto.cupon_id)
            .where(Presupuesto.estudio_id == estudio_id)
        )
    ).first()
    if fila is None:
        return None
    p, os_nombre, cupon = fila
    pagado = await pago_vigente(session, p.id) is not None
    monto_os = p.monto_base_usd - p.monto_a_pagar_usd - p.descuento_cupon_usd
    return PresupuestoSalida(
        id=p.id,
        cantidad_genes=p.cantidad_genes,
        monto_base_usd=p.monto_base_usd,
        modalidad=p.modalidad,
        obra_social=os_nombre,
        cobertura_pct=p.cobertura_pct,
        descuento_cupon_usd=p.descuento_cupon_usd,
        cupon_codigo=cupon,
        monto_a_pagar_usd=p.monto_a_pagar_usd,
        monto_obra_social_usd=monto_os,
        pagado=pagado,
        emitido_at=p.emitido_at,
    )


async def turno_salida(session: AsyncSession, ints: Integraciones, turno: Turno) -> TurnoSalida:
    centro = await session.get(CentroExtraccion, turno.centro_id)
    assert centro is not None
    return TurnoSalida(
        id=turno.id,
        estado=turno.estado,
        inicio=turno.inicio,
        centro_id=centro.id,
        centro_nombre=centro.nombre,
        centro_direccion=centro.direccion,
        orden_extraccion_url=await url_archivo(session, ints, turno.orden_archivo_id),
        consentimiento_url=await url_archivo(session, ints, turno.consentimiento_id),
    )


async def turno_activo(session: AsyncSession, estudio_id: int) -> Turno | None:
    return await session.scalar(
        select(Turno).where(Turno.estudio_id == estudio_id, Turno.estado == EstadoTurno.RESERVADO)
    )


async def detalle(session: AsyncSession, ints: Integraciones, estudio: Estudio) -> EstudioDetalle:
    base = await resumen(session, estudio.id)
    origen = await session.get(Estudio, estudio.estudio_origen_id) if estudio.estudio_origen_id else None
    turno = await turno_activo(session, estudio.id)
    rechazo = await session.scalar(
        select(AutorizacionObraSocial.motivo)
        .where(
            and_(
                AutorizacionObraSocial.estudio_id == estudio.id,
                AutorizacionObraSocial.resultado == ResultadoOS.RECHAZADO,
            )
        )
        .order_by(AutorizacionObraSocial.id.desc())
        .limit(1)
    )
    reaut = await session.scalar(
        select(SolicitudReautorizacion.id).where(
            SolicitudReautorizacion.estudio_id == estudio.id,
            SolicitudReautorizacion.estado == EstadoReaut.PENDIENTE,
        )
    )
    tiene_resultado = await session.scalar(select(Resultado.id).where(Resultado.estudio_id == estudio.id))
    return EstudioDetalle(
        **base.model_dump(),
        evalua_hallazgos_secundarios=estudio.evalua_hallazgos_secundarios,
        estudio_origen_codigo=origen.codigo if origen else None,
        inasistencias=estudio.inasistencias,
        genes=await genes_del_estudio(session, estudio.id),
        historial=await historial(session, estudio.id),
        presupuesto=await presupuesto_salida(session, estudio.id),
        turno=await turno_salida(session, ints, turno) if turno else None,
        tiene_resultado=tiene_resultado is not None,
        rechazo_motivo=rechazo,
        reautorizacion_pendiente=reaut is not None,
    )
