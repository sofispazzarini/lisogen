"""`/transportista` (app mobile): E23 Consultar Orden del Día, E24 Recolectar Muestras,
E25 Confirmar llegada al Laboratorio Central y envío de posición para Seguir Muestra (E19)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Ints, Sesion, requiere_rol
from app.domain.enums import RolUsuario
from app.models import Usuario
from app.schemas.comun import Error, Ok
from app.schemas.roles import LlegadaSalida, OrdenDelDiaSalida, PosicionEntrada
from app.services import logistica, lotes

router = APIRouter(
    prefix="/transportista",
    tags=["transportista"],
    responses={403: {"model": Error}, 404: {"model": Error}, 409: {"model": Error}, 422: {"model": Error}},
)
TransportistaU = Annotated[Usuario, Depends(requiere_rol(RolUsuario.TRANSPORTISTA))]


@router.get("/orden-del-dia", response_model=OrdenDelDiaSalida, summary="Orden del Día (E23)")
async def orden_del_dia(usuario: TransportistaU, session: Sesion) -> OrdenDelDiaSalida:
    return await logistica.orden_del_dia(session, usuario)


@router.post(
    "/paradas/{parada_id}/recolectar", response_model=OrdenDelDiaSalida, summary="Recolectar Muestras (E24)"
)
async def recolectar(parada_id: int, usuario: TransportistaU, session: Sesion) -> OrdenDelDiaSalida:
    await logistica.recolectar(session, usuario, parada_id)
    return await logistica.orden_del_dia(session, usuario)


@router.post("/posicion", response_model=Ok, summary="Enviar posición (Seguir Muestra, E19)")
async def posicion(datos: PosicionEntrada, usuario: TransportistaU, session: Sesion) -> Ok:
    await logistica.registrar_posicion(session, usuario, datos.latitud, datos.longitud)
    return Ok()


@router.post(
    "/llegada", response_model=LlegadaSalida, summary="Confirmar llegada al Laboratorio Central (E25)"
)
async def llegada(usuario: TransportistaU, session: Sesion, ints: Ints) -> LlegadaSalida:
    return await lotes.confirmar_llegada(session, ints, usuario)
