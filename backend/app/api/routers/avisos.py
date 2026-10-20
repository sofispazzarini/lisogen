"""`/avisos`: bandeja de Avisos de cualquier rol (cambios de Estado, Cupones, Estudios listos
para análisis)."""

from fastapi import APIRouter

from app.api.deps import Sesion, UsuarioActual
from app.schemas.comun import Aviso, Error, Ok
from app.services import avisos

router = APIRouter(
    prefix="/avisos", tags=["avisos"], responses={401: {"model": Error}, 404: {"model": Error}}
)


@router.get("", response_model=list[Aviso], summary="Mis Avisos")
async def listar(usuario: UsuarioActual, session: Sesion, solo_no_leidos: bool = False) -> list[Aviso]:
    return await avisos.listar(session, usuario, solo_no_leidos)


@router.post("/{aviso_id}/leido", response_model=Ok, summary="Marcar Aviso como leído")
async def marcar_leido(aviso_id: int, usuario: UsuarioActual, session: Sesion) -> Ok:
    await avisos.marcar_leido(session, usuario, aviso_id)
    return Ok()


@router.post("/leidos", response_model=Ok, summary="Marcar todos los Avisos como leídos")
async def marcar_todos(usuario: UsuarioActual, session: Sesion) -> Ok:
    await avisos.marcar_todos_leidos(session, usuario)
    return Ok()
