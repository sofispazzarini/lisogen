"""`/administrativo`: tablero, E16 Emitir Presupuesto, E17 Registrar Autorización, E18 Registrar Rechazo
de Obra Social y registro financiero. E19–E22 (logística, Lotes y laboratorio) llegan en la etapa 4 (3/3)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import Ints, Sesion, ip_cliente, requiere_rol
from app.domain.enums import EstadoEstudio, RolUsuario
from app.models import Estudio, Usuario
from app.schemas.comun import Error, EstudioDetalle, EstudioResumen, Ok
from app.schemas.roles import PresupuestoPrevio, ReautorizacionSalida, RechazoEntrada, RegistroFinanciero
from app.services import consultas, finanzas
from app.services.comun import auditar
from app.services.estudios import obtener_estudio

router = APIRouter(
    prefix="/administrativo",
    tags=["administrativo"],
    responses={403: {"model": Error}, 404: {"model": Error}, 409: {"model": Error}, 422: {"model": Error}},
)
Admin = Annotated[Usuario, Depends(requiere_rol(RolUsuario.ADMINISTRATIVO))]


@router.get("/estudios", response_model=list[EstudioResumen], summary="Tablero de Estudios")
async def tablero(_: Admin, session: Sesion, estado: EstadoEstudio | None = None) -> list[EstudioResumen]:
    filtros = [Estudio.estado == estado] if estado else []
    return await consultas.resumenes(session, *filtros)


@router.get("/estudios/{estudio_id}", response_model=EstudioDetalle, summary="Detalle del Estudio")
async def detalle(
    estudio_id: int, admin: Admin, session: Sesion, ints: Ints, request: Request
) -> EstudioDetalle:
    estudio = await obtener_estudio(session, estudio_id)
    auditar(session, admin.id, "VER_ESTUDIO", "estudio", estudio.id, ip_cliente(request))
    return await consultas.detalle(session, ints, estudio)


# --- E16 --------------------------------------------------------------------------------------


@router.get(
    "/estudios/{estudio_id}/presupuesto/previo",
    response_model=PresupuestoPrevio,
    summary="Calcular Presupuesto (E16)",
)
async def presupuesto_previo(estudio_id: int, _: Admin, session: Sesion, ints: Ints) -> PresupuestoPrevio:
    """Calcula el monto por cantidad de genes y consulta la cobertura a la API de obras sociales."""
    return await finanzas.previsualizar_presupuesto(session, ints, await obtener_estudio(session, estudio_id))


@router.post(
    "/estudios/{estudio_id}/presupuesto", response_model=PresupuestoPrevio, summary="Emitir Presupuesto (E16)"
)
async def emitir_presupuesto(estudio_id: int, admin: Admin, session: Sesion, ints: Ints) -> PresupuestoPrevio:
    estudio = await obtener_estudio(session, estudio_id, para_actualizar=True)
    return await finanzas.emitir_presupuesto(session, ints, admin, estudio)


# --- E17 / E18 --------------------------------------------------------------------------------


@router.post("/estudios/{estudio_id}/autorizacion", response_model=Ok, summary="Registrar Autorización (E17)")
async def autorizar(estudio_id: int, admin: Admin, session: Sesion) -> Ok:
    await finanzas.registrar_autorizacion(
        session, admin, await obtener_estudio(session, estudio_id, para_actualizar=True)
    )
    return Ok()


@router.post("/estudios/{estudio_id}/rechazo", response_model=Ok, summary="Registrar Rechazo (E18)")
async def rechazar(estudio_id: int, datos: RechazoEntrada, admin: Admin, session: Sesion) -> Ok:
    estudio = await obtener_estudio(session, estudio_id, para_actualizar=True)
    await finanzas.registrar_rechazo(session, admin, estudio, datos.motivo)
    return Ok()


@router.get(
    "/reautorizaciones",
    response_model=list[ReautorizacionSalida],
    summary="Reautorizaciones pendientes (E10)",
)
async def reautorizaciones(_: Admin, session: Sesion, ints: Ints) -> list[ReautorizacionSalida]:
    return await finanzas.reautorizaciones_pendientes(session, ints)


# --- Registro financiero ----------------------------------------------------------------------


@router.get("/movimientos", response_model=RegistroFinanciero, summary="Registro financiero")
async def movimientos(_: Admin, session: Sesion) -> RegistroFinanciero:
    return await finanzas.registro_financiero(session)
