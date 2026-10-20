"""Webhooks de servicios externos. Sin sesión de usuario: la URL lleva un token HMAC por recurso."""

from fastapi import APIRouter

from app.api.deps import Sesion
from app.schemas.comun import Error, Ok
from app.services import lotes

router = APIRouter(prefix="/integraciones", tags=["integraciones"], responses={404: {"model": Error}})


@router.post(
    "/fedex/lotes/{lote_id}/{token}", response_model=Ok, summary="FedEx confirma el retiro del Lote (E20)"
)
async def fedex_confirma_retiro(lote_id: int, token: str, session: Sesion) -> Ok:
    await lotes.confirmar_retiro_fedex(session, lote_id, token)
    return Ok()
