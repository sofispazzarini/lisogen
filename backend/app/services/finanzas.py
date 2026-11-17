"""E8 Pagar Presupuesto, E10 reautorización, E16 Emitir Presupuesto, E17/E18 Autorización y Rechazo
de Obra Social, registro financiero."""

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    ConceptoMov,
    EstadoEstudio,
    EstadoReaut,
    ModalidadPago,
    OrigenGen,
    ResultadoOS,
    TipoArchivo,
)
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado
from app.domain.reglas import TZ_AR, CalculoPresupuesto, calcular_presupuesto
from app.integrations.pdf import es_pdf
from app.integrations.ports import ErrorObraSocial, SolicitudExterna
from app.integrations.registro import Integraciones
from app.models import (
    AutorizacionObraSocial,
    Cupon,
    Estudio,
    EstudioGen,
    MovimientoFinanciero,
    ObraSocial,
    Paciente,
    Pago,
    Presupuesto,
    SolicitudReautorizacion,
    Usuario,
)
from app.schemas.roles import MovimientoSalida, PresupuestoPrevio, ReautorizacionSalida, RegistroFinanciero
from app.services.comun import ahora, guardar_archivo, url_archivo
from app.services.consultas import pago_vigente
from app.services.transiciones import transicionar

MAX_DEMANDA_BYTES = 5 * 1024 * 1024  # límite de la API de Obras Sociales para la decisión judicial


def _rechazo_os(e: ErrorObraSocial) -> ErrorNegocio:
    """Traduce lo que respondió la API de Obras Sociales a un error de negocio en español."""
    if e.incierto or e.status == 0 or e.status >= 500:
        return ErrorNegocio(
            "OBRA_SOCIAL_SIN_RESPUESTA",
            "El módulo de obras sociales no respondió. Esperá unos minutos y revisá el estado de la "
            "solicitud antes de reintentar.",
            status=502,
        )
    if e.status in (401, 403):
        return ErrorNegocio(
            "OBRA_SOCIAL_NO_DISPONIBLE",
            "El módulo de obras sociales no está disponible por ahora. Intentá de nuevo más tarde.",
            status=502,
        )
    if e.status == 404:
        return ErrorNegocio(
            "OBRA_SOCIAL_DESCONOCIDA", "El módulo de obras sociales no reconoce esa Obra Social."
        )
    if e.status == 409:
        return Conflicto(
            "OBRA_SOCIAL_ESTADO",
            "La solicitud ya fue resuelta en el módulo de obras sociales o tiene una demanda en curso.",
        )
    if e.status == 413:
        return ErrorNegocio("ARCHIVO_DEMASIADO_GRANDE", "La decisión judicial puede pesar hasta 5 MB.")
    return ErrorNegocio("OBRA_SOCIAL_RECHAZO", "El módulo de obras sociales rechazó los datos del pedido.")


def _guardar_solicitud(p: Presupuesto, sol: SolicitudExterna) -> None:
    p.os_solicitud_id = sol.id
    p.os_url_autorizar = sol.url_autorizar or p.os_url_autorizar
    p.os_url_rechazar = sol.url_rechazar or p.os_url_rechazar


async def _solicitud_de(
    session: AsyncSession, ints: Integraciones, estudio: Estudio, p: Presupuesto
) -> SolicitudExterna:
    """La solicitud de cobertura del Presupuesto. Si todavía no existe (Presupuesto anterior a la
    integración) se crea ahora."""
    if p.os_solicitud_id:
        return SolicitudExterna(
            id=p.os_solicitud_id, estado="", url_autorizar=p.os_url_autorizar, url_rechazar=p.os_url_rechazar
        )
    os_ = await session.get(ObraSocial, p.obra_social_id) if p.obra_social_id else None
    paciente = await session.get(Paciente, estudio.paciente_id)
    assert os_ is not None and os_.codigo_externo and paciente is not None
    try:
        sol = await ints.para_estudio(estudio.id).obras_sociales.solicitar(
            codigo_obra_social=os_.codigo_externo,
            paciente_nombre=paciente.nombre_completo,
            fecha=ahora().astimezone(TZ_AR).date(),
            referencia=estudio.codigo,
        )
    except ErrorObraSocial as e:
        raise _rechazo_os(e) from e
    _guardar_solicitud(p, sol)
    return sol


# --- E16 Emitir Presupuesto -------------------------------------------------------------------


async def _calcular(
    session: AsyncSession, ints: Integraciones, estudio: Estudio
) -> tuple[CalculoPresupuesto, ObraSocial | None]:
    cantidad = await session.scalar(
        select(func.count())
        .select_from(EstudioGen)
        .where(EstudioGen.estudio_id == estudio.id, EstudioGen.origen != OrigenGen.HALLAZGO_SECUNDARIO)
    )
    paciente = await session.get(Paciente, estudio.paciente_id)
    assert paciente is not None
    os_ = await session.get(ObraSocial, paciente.obra_social_id) if paciente.obra_social_id else None
    cobertura = Decimal(0)
    if os_ is not None and os_.codigo_externo:
        try:
            cobertura = await ints.para_estudio(estudio.id).obras_sociales.cobertura(
                codigo_obra_social=os_.codigo_externo, cantidad_genes=int(cantidad or 0)
            )
        except ErrorObraSocial as e:  # no se emite como particular: cambiaría el monto
            raise _rechazo_os(e) from e
    calculo = calcular_presupuesto(int(cantidad or 0), os_ is not None, cobertura)
    return calculo, os_ if calculo.modalidad != ModalidadPago.PARTICULAR else None


def _previo(c: CalculoPresupuesto, os_: ObraSocial | None) -> PresupuestoPrevio:
    return PresupuestoPrevio(
        cantidad_genes=c.cantidad_genes,
        monto_base_usd=c.monto_base_usd,
        modalidad=c.modalidad,
        obra_social=os_.nombre if os_ else None,
        cobertura_pct=c.cobertura_pct,
        monto_obra_social_usd=c.monto_obra_social_usd,
        monto_a_pagar_usd=c.monto_a_pagar_usd,
    )


def _exigir_creado(estudio: Estudio) -> None:
    if estudio.estado != EstadoEstudio.CREADO or estudio.tipo.value != "EXOMA":
        raise Conflicto("ESTUDIO_NO_CREADO", "Sólo se presupuestan Estudios en estado Creado.")


async def previsualizar_presupuesto(
    session: AsyncSession, ints: Integraciones, estudio: Estudio
) -> PresupuestoPrevio:
    _exigir_creado(estudio)
    return _previo(*await _calcular(session, ints, estudio))


async def emitir_presupuesto(
    session: AsyncSession, ints: Integraciones, admin: Usuario, estudio: Estudio
) -> PresupuestoPrevio:
    """Particular → POR_PAGAR. Con Obra Social (total o parcial) → PENDIENTE_AUTORIZACION."""
    _exigir_creado(estudio)
    calculo, os_ = await _calcular(session, ints, estudio)
    presupuesto = Presupuesto(
        estudio_id=estudio.id,
        cantidad_genes=calculo.cantidad_genes,
        monto_base_usd=calculo.monto_base_usd,
        modalidad=calculo.modalidad,
        obra_social_id=os_.id if os_ else None,
        cobertura_pct=calculo.cobertura_pct,
        monto_a_pagar_usd=calculo.monto_a_pagar_usd,
        emitido_por=admin.id,
    )
    if os_ is not None:  # con cobertura se pide la autorización a la Obra Social (queda pendiente)
        await _solicitud_de(session, ints, estudio, presupuesto)
    session.add(presupuesto)
    if calculo.modalidad == ModalidadPago.PARTICULAR:
        await transicionar(
            session, estudio, EstadoEstudio.POR_PAGAR, admin, "Presupuesto emitido (pago particular)"
        )
    else:
        await transicionar(
            session,
            estudio,
            EstadoEstudio.PENDIENTE_AUTORIZACION,
            admin,
            f"Presupuesto emitido con cobertura {calculo.cobertura_pct}% de {os_.nombre if os_ else ''}",
        )
    return _previo(calculo, os_)


async def presupuesto_de(session: AsyncSession, estudio: Estudio) -> Presupuesto:
    p = await session.scalar(
        select(Presupuesto).where(Presupuesto.estudio_id == estudio.id).with_for_update()
    )
    if p is None:
        raise NoEncontrado("Presupuesto")
    return p


# --- E17 / E18 Autorización y Rechazo ---------------------------------------------------------


async def _reautorizacion_pendiente(
    session: AsyncSession, estudio: Estudio
) -> SolicitudReautorizacion | None:
    return await session.scalar(
        select(SolicitudReautorizacion).where(
            SolicitudReautorizacion.estudio_id == estudio.id,
            SolicitudReautorizacion.estado == EstadoReaut.PENDIENTE,
        )
    )


async def _resolver_reautorizacion(session: AsyncSession, estudio: Estudio, estado: EstadoReaut) -> None:
    sol = await _reautorizacion_pendiente(session, estudio)
    if sol is not None:
        sol.estado, sol.resuelto_at = estado, ahora()


def _exigir_pendiente(estudio: Estudio) -> None:
    if estudio.estado != EstadoEstudio.PENDIENTE_AUTORIZACION:
        raise Conflicto("ESTUDIO_NO_PENDIENTE", "El Estudio no está Pendiente de Autorización.")


async def registrar_autorizacion(
    session: AsyncSession, ints: Integraciones, admin: Usuario, estudio: Estudio
) -> None:
    """E17: Autorizado equivale a pagado; se registra el pago de la Obra Social.
    SUPUESTO S1: con cobertura parcial el Estudio queda POR_PAGAR por la diferencia.
    La Obra Social se simula en la API: primero se la autoriza ahí y recién después cambia el Estudio.
    Si hay una demanda (reautorización), la API pide el porcentaje: es el del Presupuesto (S37)."""
    _exigir_pendiente(estudio)
    p = await presupuesto_de(session, estudio)
    assert p.obra_social_id is not None
    con_demanda = await _reautorizacion_pendiente(session, estudio) is not None
    sol = await _solicitud_de(session, ints, estudio, p)
    try:
        sol = await ints.para_estudio(estudio.id).obras_sociales.autorizar(
            solicitud=sol, porcentaje=p.cobertura_pct if con_demanda else None
        )
    except ErrorObraSocial as e:
        raise _rechazo_os(e) from e
    _guardar_solicitud(p, sol)
    session.add(
        AutorizacionObraSocial(
            estudio_id=estudio.id,
            obra_social_id=p.obra_social_id,
            resultado=ResultadoOS.AUTORIZADO,
            registrado_por=admin.id,
        )
    )
    monto_os = p.monto_base_usd - p.monto_a_pagar_usd - p.descuento_cupon_usd
    session.add(
        MovimientoFinanciero(
            estudio_id=estudio.id,
            concepto=ConceptoMov.PAGO_OBRA_SOCIAL,
            monto_usd=monto_os,
            obra_social_id=p.obra_social_id,
        )
    )
    await _resolver_reautorizacion(session, estudio, EstadoReaut.AUTORIZADA)
    if p.modalidad == ModalidadPago.MIXTA and p.monto_a_pagar_usd > 0:
        await transicionar(
            session,
            estudio,
            EstadoEstudio.POR_PAGAR,
            admin,
            "Autorización parcial: resta pagar la diferencia",
        )
    else:
        await transicionar(session, estudio, EstadoEstudio.AUTORIZADO, admin, "Autorizado por la Obra Social")


async def registrar_rechazo(
    session: AsyncSession, ints: Integraciones, admin: Usuario, estudio: Estudio, motivo: str
) -> None:
    """E18: el Estudio pasa a Rechazado y el Paciente puede pedir la reautorización (E10).
    Igual que la Autorización, primero se rechaza en la API de Obras Sociales."""
    _exigir_pendiente(estudio)
    p = await presupuesto_de(session, estudio)
    assert p.obra_social_id is not None
    sol = await _solicitud_de(session, ints, estudio, p)
    try:
        sol = await ints.para_estudio(estudio.id).obras_sociales.rechazar(solicitud=sol, motivo=motivo)
    except ErrorObraSocial as e:
        raise _rechazo_os(e) from e
    _guardar_solicitud(p, sol)
    session.add(
        AutorizacionObraSocial(
            estudio_id=estudio.id,
            obra_social_id=p.obra_social_id,
            resultado=ResultadoOS.RECHAZADO,
            motivo=motivo,
            registrado_por=admin.id,
        )
    )
    await _resolver_reautorizacion(session, estudio, EstadoReaut.RECHAZADA)
    await transicionar(session, estudio, EstadoEstudio.RECHAZADO, admin, motivo)


# --- E10 Solicitar reautorización -------------------------------------------------------------


async def solicitar_reautorizacion(
    session: AsyncSession,
    ints: Integraciones,
    usuario: Usuario,
    estudio: Estudio,
    nombre: str,
    contenido: bytes,
) -> SolicitudReautorizacion:
    """SUPUESTO S2: el PDF judicial vuelve el Estudio a PENDIENTE_AUTORIZACION para que el
    Administrativo registre de nuevo la Autorización o el Rechazo."""
    if estudio.estado != EstadoEstudio.RECHAZADO:
        raise Conflicto("ESTUDIO_NO_RECHAZADO", "Sólo se pide reautorización de un Estudio Rechazado.")
    if not es_pdf(contenido):
        raise ErrorNegocio("ARCHIVO_NO_PDF", "Adjuntá la decisión judicial en PDF.")
    if len(contenido) > MAX_DEMANDA_BYTES:
        raise ErrorNegocio("ARCHIVO_DEMASIADO_GRANDE", "La decisión judicial puede pesar hasta 5 MB.")
    p = await presupuesto_de(session, estudio)
    sol_os = await _solicitud_de(session, ints, estudio, p)
    try:  # la decisión judicial se presenta como demanda en la API; si falla no se guarda nada
        sol_os = await ints.para_estudio(estudio.id).obras_sociales.presentar_demanda(
            solicitud=sol_os, nombre_archivo=nombre or "decision-judicial.pdf", contenido=contenido
        )
    except ErrorObraSocial as e:
        raise _rechazo_os(e) from e
    _guardar_solicitud(p, sol_os)
    rechazo = await session.scalar(
        select(AutorizacionObraSocial)
        .where(
            AutorizacionObraSocial.estudio_id == estudio.id,
            AutorizacionObraSocial.resultado == ResultadoOS.RECHAZADO,
        )
        .order_by(AutorizacionObraSocial.id.desc())
        .limit(1)
    )
    assert rechazo is not None
    archivo = await guardar_archivo(
        session,
        ints,
        tipo=TipoArchivo.DECISION_JUDICIAL_PDF,
        nombre=nombre or "decision-judicial.pdf",
        mime="application/pdf",
        contenido=contenido,
        subido_por=usuario.id,
    )
    sol = SolicitudReautorizacion(
        estudio_id=estudio.id, rechazo_id=rechazo.id, decision_judicial=archivo.id, solicitado_por=usuario.id
    )
    session.add(sol)
    await transicionar(
        session,
        estudio,
        EstadoEstudio.PENDIENTE_AUTORIZACION,
        usuario,
        "Reautorización con decisión judicial",
    )
    return sol


# --- E8 Pagar Presupuesto ---------------------------------------------------------------------


async def pagar(session: AsyncSession, usuario: Usuario, estudio: Estudio) -> Pago:
    """Pago simulado en un solo pago; registra el movimiento financiero y habilita Sacar Turno."""
    if estudio.estado != EstadoEstudio.POR_PAGAR:
        raise Conflicto("ESTUDIO_NO_POR_PAGAR", "El Estudio no tiene un Presupuesto pendiente de pago.")
    p = await presupuesto_de(session, estudio)
    if await pago_vigente(session, p.id) is not None:
        raise Conflicto("PRESUPUESTO_PAGADO", "El Presupuesto ya está pagado.")
    pago = Pago(
        presupuesto_id=p.id,
        monto_usd=p.monto_a_pagar_usd,
        referencia_sim=f"SIM-{uuid.uuid4().hex[:12].upper()}",
        pagado_por=usuario.id,
    )
    session.add(pago)
    await session.flush()
    session.add(
        MovimientoFinanciero(
            estudio_id=estudio.id,
            concepto=ConceptoMov.PAGO_PACIENTE,
            monto_usd=p.monto_a_pagar_usd,
            pago_id=pago.id,
        )
    )
    await transicionar(
        session, estudio, EstadoEstudio.PAGADO, usuario, f"Pago simulado {pago.referencia_sim}"
    )
    return pago


async def perder_pago(session: AsyncSession, estudio: Estudio) -> Decimal:
    """SUPUESTO S9: con 5 inasistencias se anula el pago vigente y se registra la pérdida."""
    p = await presupuesto_de(session, estudio)
    pago = await pago_vigente(session, p.id)
    monto = pago.monto_usd if pago else Decimal("0.00")
    if pago is not None:
        pago.anulado_at = ahora()
    session.add(
        MovimientoFinanciero(
            estudio_id=estudio.id,
            concepto=ConceptoMov.PERDIDA_POR_INASISTENCIAS,
            monto_usd=monto,
            pago_id=pago.id if pago else None,
            obra_social_id=p.obra_social_id,
        )
    )
    return monto


# --- Registro financiero ----------------------------------------------------------------------


async def registro_financiero(session: AsyncSession) -> RegistroFinanciero:
    filas = await session.execute(
        select(MovimientoFinanciero, Estudio.codigo, ObraSocial.nombre)
        .join(Estudio, Estudio.id == MovimientoFinanciero.estudio_id)
        .outerjoin(ObraSocial, ObraSocial.id == MovimientoFinanciero.obra_social_id)
        .order_by(MovimientoFinanciero.created_at.desc(), MovimientoFinanciero.id.desc())
        .limit(500)
    )
    movimientos = [
        MovimientoSalida(
            id=m.id,
            created_at=m.created_at,
            concepto=m.concepto,
            monto_usd=m.monto_usd,
            estudio_codigo=c,
            obra_social=o,
        )
        for m, c, o in filas
    ]

    def total(concepto: ConceptoMov) -> Decimal:
        return sum((m.monto_usd for m in movimientos if m.concepto == concepto), Decimal("0.00"))

    return RegistroFinanciero(
        movimientos=movimientos,
        total_pacientes_usd=total(ConceptoMov.PAGO_PACIENTE),
        total_obras_sociales_usd=total(ConceptoMov.PAGO_OBRA_SOCIAL),
        total_perdidas_usd=total(ConceptoMov.PERDIDA_POR_INASISTENCIAS),
    )


async def cupon_del_presupuesto(session: AsyncSession, presupuesto: Presupuesto) -> Cupon | None:
    return await session.get(Cupon, presupuesto.cupon_id) if presupuesto.cupon_id else None


async def reautorizaciones_pendientes(
    session: AsyncSession, ints: Integraciones
) -> list[ReautorizacionSalida]:
    """E17/E18 tras E10: solicitudes con decisión judicial que el Administrativo tiene que resolver."""
    filas = await session.execute(
        select(SolicitudReautorizacion, Estudio, Paciente)
        .join(Estudio, Estudio.id == SolicitudReautorizacion.estudio_id)
        .join(Paciente, Paciente.id == Estudio.paciente_id)
        .where(SolicitudReautorizacion.estado == EstadoReaut.PENDIENTE)
        .order_by(SolicitudReautorizacion.created_at)
    )
    return [
        ReautorizacionSalida(
            id=sol.id,
            estudio_id=e.id,
            estudio_codigo=e.codigo,
            paciente=p.nombre_completo,
            estado=sol.estado,
            created_at=sol.created_at,
            decision_judicial_url=await url_archivo(session, ints, sol.decision_judicial),
        )
        for sol, e, p in filas
    ]
