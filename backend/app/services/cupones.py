"""E5 Asignar Cupón a Paciente, E9 Aplicar Cupón, E32 Generar Cupón, E33 Asignar Cupón a Médico."""

from datetime import datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.enums import EstadoCupon, RolUsuario, TipoArchivo
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado
from app.domain.reglas import avanzar_cupon, cupon_vencido
from app.integrations.registro import Integraciones
from app.models import Cupon, Paciente, ProfesionalMedico, Usuario
from app.schemas.roles import CuponSalida, MedicoSalida
from app.services.comun import ahora, guardar_archivo, notificar, url_archivo
from app.services.pacientes import paciente_del_medico

MedicoU = aliased(Usuario)


async def _salida(
    session: AsyncSession, ints: Integraciones, filtros: list[ColumnElement[bool]]
) -> list[CuponSalida]:
    filas = await session.execute(
        select(Cupon, MedicoU, Paciente)
        .outerjoin(MedicoU, MedicoU.id == Cupon.medico_asignado_id)
        .outerjoin(Paciente, Paciente.id == Cupon.paciente_asignado_id)
        .where(*filtros)
        .order_by(Cupon.created_at.desc(), Cupon.id.desc())
        .limit(500)
    )
    salida = []
    for c, m, p in filas:
        estado = (
            EstadoCupon.VENCIDO
            if c.estado != EstadoCupon.USADO and cupon_vencido(c.vence_at, ahora())
            else c.estado
        )
        salida.append(
            CuponSalida(
                id=c.id,
                codigo=c.codigo,
                descuento_pct=c.descuento_pct,
                estado=estado,
                medico=m.nombre_completo if m else None,
                paciente=p.nombre_completo if p else None,
                vence_at=c.vence_at,
                qr_url=await url_archivo(session, ints, c.qr_archivo_id),
            )
        )
    return salida


# --- Gerente Médico ---------------------------------------------------------------------------


async def generar(
    session: AsyncSession,
    ints: Integraciones,
    gerente: Usuario,
    descuento_pct: int,
    cantidad: int,
    vence_at: datetime | None,
) -> list[Cupon]:
    """E32: el módulo externo genera los Cupones; si no genera QR, quedan con código numérico."""
    if vence_at is not None and vence_at <= ahora():
        raise ErrorNegocio("VENCIMIENTO_INVALIDO", "El vencimiento tiene que ser futuro.")
    externos = await ints.cupones.generar(descuento_pct=descuento_pct, cantidad=cantidad)
    cupones = []
    for ext in externos:
        qr_id = None
        if ext.qr_pdf is not None:
            archivo = await guardar_archivo(
                session,
                ints,
                tipo=TipoArchivo.CUPON_PDF,
                nombre=f"cupon-{ext.codigo}.pdf",
                mime="application/pdf",
                contenido=ext.qr_pdf,
                subido_por=gerente.id,
            )
            qr_id = archivo.id
        cupon = Cupon(
            codigo=ext.codigo,
            qr_archivo_id=qr_id,
            descuento_pct=descuento_pct,
            generado_por=gerente.id,
            vence_at=vence_at,
        )
        session.add(cupon)
        cupones.append(cupon)
    await session.flush()
    return cupones


async def listar_todos(session: AsyncSession, ints: Integraciones) -> list[CuponSalida]:
    return await _salida(session, ints, [])


async def medicos(session: AsyncSession) -> list[MedicoSalida]:
    disponibles = (
        select(func.count())
        .where(Cupon.medico_asignado_id == Usuario.id, Cupon.estado == EstadoCupon.ASIGNADO_MEDICO)
        .scalar_subquery()
    )
    filas = await session.execute(
        select(Usuario, ProfesionalMedico.matricula, disponibles)
        .join(ProfesionalMedico, ProfesionalMedico.usuario_id == Usuario.id)
        .where(Usuario.rol == RolUsuario.MEDICO_TRATANTE, Usuario.activo.is_(True))
        .order_by(Usuario.apellido, Usuario.nombre)
    )
    return [
        MedicoSalida(id=u.id, nombre_completo=u.nombre_completo, matricula=mat, cupones_disponibles=n or 0)
        for u, mat, n in filas
    ]


async def asignar_a_medico(session: AsyncSession, cupon_ids: list[int], medico_id: int) -> None:
    """E33: los Cupones DISPONIBLES pasan a ASIGNADO_MEDICO."""
    medico = await session.get(Usuario, medico_id)
    if medico is None or medico.rol != RolUsuario.MEDICO_TRATANTE:
        raise NoEncontrado("Médico Tratante")
    cupones = list(await session.scalars(select(Cupon).where(Cupon.id.in_(cupon_ids)).with_for_update()))
    if len(cupones) != len(set(cupon_ids)):
        raise NoEncontrado("Cupón")
    for c in cupones:
        avanzar_cupon(c.estado, EstadoCupon.ASIGNADO_MEDICO, c.vence_at, ahora())
        c.estado, c.medico_asignado_id, c.asignado_medico_at = EstadoCupon.ASIGNADO_MEDICO, medico.id, ahora()
    notificar(
        session,
        medico.id,
        "Recibiste Cupones de descuento",
        f"El Gerente Médico te asignó {len(cupones)} Cupón(es).",
    )


# --- Médico Tratante --------------------------------------------------------------------------


async def del_medico(session: AsyncSession, ints: Integraciones, medico: Usuario) -> list[CuponSalida]:
    return await _salida(session, ints, [Cupon.medico_asignado_id == medico.id])


async def asignar_a_paciente(session: AsyncSession, medico: Usuario, cupon_id: int, paciente_id: int) -> None:
    """E5: el Cupón deja de estar disponible para el Médico y queda asignado al Paciente."""
    paciente = await paciente_del_medico(session, medico, paciente_id)
    cupon = await session.scalar(select(Cupon).where(Cupon.id == cupon_id).with_for_update())
    if cupon is None or cupon.medico_asignado_id != medico.id:
        raise NoEncontrado("Cupón")
    if cupon.estado != EstadoCupon.ASIGNADO_MEDICO:
        raise Conflicto("CUPON_NO_DISPONIBLE", "Ese Cupón ya no está disponible.")
    avanzar_cupon(cupon.estado, EstadoCupon.ASIGNADO_PACIENTE, cupon.vence_at, ahora())
    cupon.estado, cupon.paciente_asignado_id, cupon.asignado_paciente_at = (
        EstadoCupon.ASIGNADO_PACIENTE,
        paciente.id,
        ahora(),
    )
    if paciente.usuario_id:
        notificar(
            session,
            paciente.usuario_id,
            "Tenés un Cupón de descuento",
            f"Tu Médico Tratante te asignó un Cupón del {cupon.descuento_pct}%. "
            "Aplicalo al pagar tu Presupuesto.",
        )
