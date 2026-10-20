"""`/bioinformatico`: E27 Tomar Estudio para análisis y E28 Cargar Variantes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import Ints, Sesion, requiere_rol
from app.domain.enums import RolUsuario
from app.models import Usuario
from app.schemas.comun import Error, EstudioResumen, ResultadoSalida
from app.schemas.roles import EstudioAnalisis, ResultadoEntrada, TomarEntrada, VarianteCatalogo
from app.services import analisis, resultados
from app.services.estudios import obtener_estudio

router = APIRouter(
    prefix="/bioinformatico",
    tags=["bioinformatico"],
    responses={403: {"model": Error}, 404: {"model": Error}, 409: {"model": Error}, 422: {"model": Error}},
)
Bio = Annotated[Usuario, Depends(requiere_rol(RolUsuario.BIOINFORMATICO))]


@router.get(
    "/pendientes", response_model=list[EstudioResumen], summary="Estudios pendientes, Urgentes primero (E27)"
)
async def pendientes(_: Bio, session: Sesion) -> list[EstudioResumen]:
    return await analisis.pendientes(session)


@router.get("/estudios", response_model=list[EstudioResumen], summary="Mis Estudios en análisis")
async def mis_estudios(bio: Bio, session: Sesion) -> list[EstudioResumen]:
    return await analisis.mis_estudios(session, bio)


@router.post("/estudios/{estudio_id}/tomar", response_model=EstudioAnalisis, summary="Tomar Estudio (E27)")
async def tomar(
    estudio_id: int, datos: TomarEntrada, bio: Bio, session: Sesion, ints: Ints
) -> EstudioAnalisis:
    """Mandá la `version` que viste en la lista: si otro Bioinformático lo tomó antes, responde 409."""
    await analisis.tomar(session, bio, estudio_id, datos.version)
    return await analisis.para_analisis(session, ints, bio, estudio_id)


@router.get(
    "/estudios/{estudio_id}", response_model=EstudioAnalisis, summary="Estudio con genes y datos crudos"
)
async def estudio(estudio_id: int, bio: Bio, session: Sesion, ints: Ints) -> EstudioAnalisis:
    return await analisis.para_analisis(session, ints, bio, estudio_id)


@router.get(
    "/estudios/{estudio_id}/genes/{simbolo}/variantes",
    response_model=list[VarianteCatalogo],
    summary="Variantes del gen según la API de bioinformática (E28)",
)
async def variantes(
    estudio_id: int, simbolo: str, bio: Bio, session: Sesion, ints: Ints
) -> list[VarianteCatalogo]:
    return await analisis.variantes_de_gen(session, ints, bio, estudio_id, simbolo)


@router.post(
    "/estudios/{estudio_id}/resultado", response_model=ResultadoSalida, summary="Confirmar Resultado (E28)"
)
async def confirmar(
    estudio_id: int, datos: ResultadoEntrada, bio: Bio, session: Sesion, ints: Ints
) -> ResultadoSalida:
    await analisis.confirmar_resultado(session, ints, bio, estudio_id, datos)
    return await resultados.resultado(session, ints, bio, await obtener_estudio(session, estudio_id), None)
