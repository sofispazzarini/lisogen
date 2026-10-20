"""El seed deja 6 Estudios en distintos Estados (uno Urgente) armados con los servicios reales."""

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EstadoCupon, EstadoEstudio, RolUsuario, TipoResultado
from app.domain.reglas import es_dia_habil
from app.integrations.registro import Adaptadores, Integraciones
from app.models import (
    Cupon,
    Estudio,
    EstudioEstadoHistorial,
    Feriado,
    OrdenDelDia,
    Paciente,
    Resultado,
    Usuario,
)
from app.seed.cargar import cargar
from app.seed.estudios import cargar_estudios
from app.services import logistica
from tests.factories import headers
from tests.flujos import ok


async def test_seed_de_estudios(
    cliente: httpx.AsyncClient, session: AsyncSession, adaptadores: Adaptadores
) -> None:
    await cargar(session)
    await cargar_estudios(session, Integraciones(session, adaptadores))

    estudios = list(await session.scalars(select(Estudio).order_by(Estudio.id)))
    assert len(estudios) == 6
    assert {e.estado for e in estudios} == {
        EstadoEstudio.FINALIZADO,
        EstadoEstudio.POR_PAGAR,
        EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        EstadoEstudio.CREADO,
        EstadoEstudio.PENDIENTE_AUTORIZACION,
        EstadoEstudio.LISTO_PARA_RETIRAR,
    }
    urgentes = [e for e in estudios if e.urgente]
    assert len(urgentes) == 1 and urgentes[0].estado == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA

    finalizado = next(e for e in estudios if e.estado == EstadoEstudio.FINALIZADO)
    resultado = await session.scalar(select(Resultado).where(Resultado.estudio_id == finalizado.id))
    assert resultado is not None and resultado.tipo == TipoResultado.POSITIVO
    historial = list(
        await session.scalars(
            select(EstudioEstadoHistorial.estado_nuevo)
            .where(EstudioEstadoHistorial.estudio_id == finalizado.id)
            .order_by(EstudioEstadoHistorial.id)
        )
    )
    assert len(historial) == 12 and historial[-1] == EstadoEstudio.FINALIZADO

    cuenta = await session.scalar(select(Usuario).where(Usuario.email == "paciente@lisogen-demo.com.ar"))
    assert cuenta is not None
    demo = await session.scalar(select(Paciente).where(Paciente.usuario_id == cuenta.id))
    assert demo is not None
    cupon = await session.scalar(select(Cupon).where(Cupon.paciente_asignado_id == demo.id))
    assert cupon is not None and cupon.estado == EstadoCupon.ASIGNADO_PACIENTE

    # El Paciente demo ve sus dos Estudios y el Resultado
    mios = await ok(await cliente.get("/paciente/estudios", headers=headers(cuenta)))
    assert {e["estado"] for e in mios} == {"FINALIZADO", "POR_PAGAR"}
    r = await ok(await cliente.get(f"/paciente/estudios/{finalizado.id}/resultado", headers=headers(cuenta)))
    assert r["tipo"] == "POSITIVO"

    # El Bioinformático ve el Urgente pendiente
    bio = await session.scalar(select(Usuario).where(Usuario.rol == RolUsuario.BIOINFORMATICO))
    assert bio is not None
    pendientes = await ok(await cliente.get("/bioinformatico/pendientes", headers=headers(bio)))
    assert pendientes[0]["urgente"]

    # La Orden del Día de hoy existe sólo si hoy es hábil (E23)
    no_habiles = set(await session.scalars(select(Feriado.fecha)))
    orden_hoy = await session.scalar(select(OrdenDelDia).where(OrdenDelDia.fecha == logistica.hoy()))
    assert (orden_hoy is not None) == es_dia_habil(logistica.hoy(), no_habiles)
