"""E5 Asignar Cupón a Paciente, E9 Aplicar Cupón, E32 Generar Cupón, E33 Asignar Cupón a Médico.

Cada paso se hace primero en la API de Cupones de Exoma Care (generar → asignar al médico → asignar al
paciente → canjear) y recién después se refleja en la base de LisoGen: si la API rechaza, nada cambia acá.
La API sólo entrega el código: el PDF con el QR lo arma LisoGen (`cupon_pdf`).
SUPUESTOS: la API los vence a los 30 días (el Gerente no elige vencimiento); un Paciente sólo puede
recibir un Cupón por grupo (409); hay un solo Gerente Médico por grupo (403)."""

from datetime import timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.enums import EstadoCupon, EstadoEstudio, ModalidadPago, RolUsuario, TipoArchivo
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado
from app.domain.reglas import avanzar_cupon, calcular_presupuesto, cupon_vencido
from app.integrations.cupon_pdf import leer_codigo_de_pdf_cupon, pdf_de_cupon
from app.integrations.ports import ErrorCupones
from app.integrations.registro import Integraciones
from app.models import Cupon, Estudio, Paciente, ProfesionalMedico, Usuario
from app.schemas.roles import CuponSalida, MedicoSalida
from app.services.comun import ahora, guardar_archivo, notificar, url_archivo
from app.services.finanzas import presupuesto_de
from app.services.pacientes import paciente_del_medico

MedicoU = aliased(Usuario)
VENCIMIENTO_DIAS = 30  # lo fija la API de Cupones


def _rechazo(e: ErrorCupones) -> ErrorNegocio:
    """Traduce lo que respondió la API de Cupones a un error de negocio en español."""
    if e.incierto or e.status == 0 or e.status >= 500:
        return ErrorNegocio(
            "CUPONES_SIN_RESPUESTA",
            "El módulo de cupones no respondió. Esperá unos minutos y revisá el estado del Cupón antes de "
            "reintentar.",
            status=502,
        )
    if e.status == 409:
        return Conflicto(
            "CUPON_CONFLICTO",
            "El módulo de cupones informó un conflicto: el Cupón ya fue usado o el Paciente ya recibió un "
            "Cupón.",
        )
    if e.status == 403:
        return ErrorNegocio(
            "CUPON_SIN_PERMISO", "El módulo de cupones sólo admite un Gerente Médico por grupo."
        )
    if e.status == 404:
        return ErrorNegocio(
            "CUPON_INVALIDO", "El módulo de cupones no reconoce ese Cupón para esta operación."
        )
    return ErrorNegocio(
        "CUPON_INVALIDO", "El módulo de cupones rechazó la operación (Cupón vencido o inválido)."
    )


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
    session: AsyncSession, ints: Integraciones, gerente: Usuario, descuento_pct: int, cantidad: int
) -> list[Cupon]:
    """E32: la API genera el lote (vencen a los 30 días); LisoGen arma el PDF con QR de cada Cupón."""
    try:
        externos = await ints.cupones.generar(
            gerente_id=gerente.id, descuento_pct=descuento_pct, cantidad=cantidad
        )
    except ErrorCupones as e:
        raise _rechazo(e) from e
    vence_at = ahora() + timedelta(days=VENCIMIENTO_DIAS)
    cupones = []
    for ext in externos:
        pdf = pdf_de_cupon(codigo=ext.codigo, descuento_pct=descuento_pct, vence_at=vence_at)
        archivo = await guardar_archivo(
            session,
            ints,
            tipo=TipoArchivo.CUPON_PDF,
            nombre=f"cupon-{ext.codigo}.pdf",
            mime="application/pdf",
            contenido=pdf,
            subido_por=gerente.id,
        )
        cupon = Cupon(
            codigo=ext.codigo,
            qr_archivo_id=archivo.id,
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


async def asignar_a_medico(
    session: AsyncSession, ints: Integraciones, gerente: Usuario, cupon_ids: list[int], medico_id: int
) -> None:
    """E33: los Cupones DISPONIBLES pasan a ASIGNADO_MEDICO (uno por uno en la API de Cupones)."""
    medico = await session.get(Usuario, medico_id)
    if medico is None or medico.rol != RolUsuario.MEDICO_TRATANTE:
        raise NoEncontrado("Médico Tratante")
    cupones = list(
        await session.scalars(
            select(Cupon).where(Cupon.id.in_(cupon_ids)).order_by(Cupon.id).with_for_update()
        )
    )
    if len(cupones) != len(set(cupon_ids)):
        raise NoEncontrado("Cupón")
    for c in cupones:
        avanzar_cupon(c.estado, EstadoCupon.ASIGNADO_MEDICO, c.vence_at, ahora())
    hechos = 0
    for c in cupones:
        try:
            await ints.cupones.asignar_a_medico(gerente_id=gerente.id, medico_id=medico.id, codigo=c.codigo)
        except ErrorCupones as e:
            if hechos:
                # los anteriores ya quedaron asignados en la API: se confirman acá antes de informar el error
                _avisar_al_medico(session, medico, hechos)
                await session.commit()
            raise _rechazo(e) from e
        c.estado, c.medico_asignado_id, c.asignado_medico_at = EstadoCupon.ASIGNADO_MEDICO, medico.id, ahora()
        hechos += 1
    _avisar_al_medico(session, medico, hechos)


def _avisar_al_medico(session: AsyncSession, medico: Usuario, cantidad: int) -> None:
    notificar(
        session,
        medico.id,
        "Recibiste Cupones de descuento",
        f"El Gerente Médico te asignó {cantidad} Cupón(es).",
    )


# --- Médico Tratante --------------------------------------------------------------------------


async def del_medico(session: AsyncSession, ints: Integraciones, medico: Usuario) -> list[CuponSalida]:
    return await _salida(session, ints, [Cupon.medico_asignado_id == medico.id])


async def asignar_a_paciente(
    session: AsyncSession, ints: Integraciones, medico: Usuario, cupon_id: int, paciente_id: int
) -> None:
    """E5: el Cupón deja de estar disponible para el Médico y queda asignado al Paciente."""
    paciente = await paciente_del_medico(session, medico, paciente_id)
    cupon = await session.scalar(select(Cupon).where(Cupon.id == cupon_id).with_for_update())
    if cupon is None or cupon.medico_asignado_id != medico.id:
        raise NoEncontrado("Cupón")
    if cupon.estado != EstadoCupon.ASIGNADO_MEDICO:
        raise Conflicto("CUPON_NO_DISPONIBLE", "Ese Cupón ya no está disponible.")
    avanzar_cupon(cupon.estado, EstadoCupon.ASIGNADO_PACIENTE, cupon.vence_at, ahora())
    try:
        await ints.cupones.asignar_a_paciente(
            medico_id=medico.id, paciente_id=paciente.id, codigo=cupon.codigo
        )
    except ErrorCupones as e:
        raise _rechazo(e) from e
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


# --- Paciente ---------------------------------------------------------------------------------


async def del_paciente(session: AsyncSession, ints: Integraciones, paciente: Paciente) -> list[CuponSalida]:
    return await _salida(
        session,
        ints,
        [Cupon.paciente_asignado_id == paciente.id, Cupon.estado == EstadoCupon.ASIGNADO_PACIENTE],
    )


async def aplicar(
    session: AsyncSession,
    ints: Integraciones,
    paciente: Paciente,
    estudio: Estudio,
    codigo: str | None,
    pdf: bytes | None,
) -> None:
    """E9: canjea el Cupón en la API de Cupones, aplica el % sobre lo que paga el Paciente y lo marca usado.
    El código se ingresa o se lee del PDF con el QR.
    SUPUESTO S6: si no es válido se rechaza (422) y el Presupuesto mantiene el precio original."""
    if estudio.estado not in (EstadoEstudio.POR_PAGAR, EstadoEstudio.PENDIENTE_AUTORIZACION):
        raise Conflicto("ESTUDIO_NO_POR_PAGAR", "Sólo se aplica un Cupón antes de pagar el Presupuesto.")
    if pdf is not None and not codigo:
        codigo = leer_codigo_de_pdf_cupon(pdf)
        if codigo is None:
            raise ErrorNegocio("CUPON_INVALIDO", "No pudimos leer el QR del PDF. Probá ingresando el código.")
    if not codigo or not codigo.strip():
        raise ErrorNegocio("CUPON_INVALIDO", "Ingresá el código del Cupón o subí el PDF con el QR.")
    p = await presupuesto_de(session, estudio)
    if p.cupon_id is not None:
        raise Conflicto("PRESUPUESTO_CON_CUPON", "El Presupuesto ya tiene un Cupón aplicado.")
    if p.modalidad == ModalidadPago.OBRA_SOCIAL:
        raise ErrorNegocio(
            "CUPON_NO_APLICA", "La Obra Social cubre el 100%: no hay monto sobre el cual aplicar el Cupón."
        )
    cupon = await session.scalar(
        select(Cupon).where(func.lower(Cupon.codigo) == codigo.strip().lower()).with_for_update()
    )
    if cupon is None or cupon.paciente_asignado_id != paciente.id:
        raise ErrorNegocio("CUPON_INVALIDO", "El Cupón no es válido.")
    if cupon.estado == EstadoCupon.USADO:
        raise ErrorNegocio("CUPON_USADO", "El Cupón ya fue usado.")
    try:
        avanzar_cupon(cupon.estado, EstadoCupon.USADO, cupon.vence_at, ahora())
    except Conflicto as e:
        raise ErrorNegocio(e.code, e.message) from e
    calculo = calcular_presupuesto(
        p.cantidad_genes,
        p.obra_social_id is not None,
        p.cobertura_pct,
        descuento_cupon_pct=cupon.descuento_pct,
    )
    try:
        await ints.para_estudio(estudio.id).cupones.canjear(paciente_id=paciente.id, codigo=cupon.codigo)
    except ErrorCupones as e:
        raise _rechazo(e) from e
    p.cupon_id, p.descuento_cupon_usd, p.monto_a_pagar_usd = (
        cupon.id,
        calculo.descuento_cupon_usd,
        calculo.monto_a_pagar_usd,
    )
    cupon.estado, cupon.usado_at = EstadoCupon.USADO, ahora()
