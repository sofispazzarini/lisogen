"""`/gerente`: E30 Dar de alta Patología, E31 Modificar Patología, E32 Generar Cupón,
E33 Asignar Cupón a Médico Tratante. El tablero de control quedó fuera del alcance (PO)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import Ints, Sesion, requiere_rol
from app.domain.enums import RolUsuario
from app.models import Usuario
from app.schemas.comun import Concepto, Error, Ok
from app.schemas.roles import (
    AsignarCuponesEntrada,
    CuponSalida,
    GenerarCuponesEntrada,
    MedicoSalida,
    PatologiaEntrada,
    PatologiaSalida,
)
from app.services import cupones, patologias

router = APIRouter(
    prefix="/gerente",
    tags=["gerente"],
    responses={403: {"model": Error}, 404: {"model": Error}, 409: {"model": Error}, 422: {"model": Error}},
)
Gerente = Annotated[Usuario, Depends(requiere_rol(RolUsuario.GERENTE_MEDICO))]


async def _patologia(session: Sesion, patologia_id: int) -> PatologiaSalida:
    return next(p for p in await patologias.listar(session) if p.id == patologia_id)


@router.get("/snomed", response_model=list[Concepto], summary="Buscar síntomas SNOMED (E30, E31)")
async def buscar_snomed(
    _: Gerente, ints: Ints, q: Annotated[str, Query(min_length=2, max_length=60)]
) -> list[Concepto]:
    return [Concepto(concept_id=c.concept_id, termino=c.termino) for c in await ints.snomed.buscar(texto=q)]


@router.get("/patologias", response_model=list[PatologiaSalida], summary="Patologías")
async def listar_patologias(_: Gerente, session: Sesion) -> list[PatologiaSalida]:
    return await patologias.listar(session)


@router.post(
    "/patologias",
    response_model=PatologiaSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta Patología (E30)",
)
async def alta_patologia(datos: PatologiaEntrada, _: Gerente, session: Sesion) -> PatologiaSalida:
    patologia = await patologias.dar_de_alta(session, datos)
    return await _patologia(session, patologia.id)


@router.put("/patologias/{patologia_id}", response_model=PatologiaSalida, summary="Modificar Patología (E31)")
async def modificar_patologia(
    patologia_id: int, datos: PatologiaEntrada, _: Gerente, session: Sesion
) -> PatologiaSalida:
    await patologias.modificar(session, patologia_id, datos)
    return await _patologia(session, patologia_id)


@router.get("/cupones", response_model=list[CuponSalida], summary="Cupones generados")
async def listar_cupones(_: Gerente, session: Sesion, ints: Ints) -> list[CuponSalida]:
    return await cupones.listar_todos(session, ints)


@router.post(
    "/cupones",
    response_model=list[CuponSalida],
    status_code=status.HTTP_201_CREATED,
    summary="Generar Cupones (E32)",
)
async def generar_cupones(
    datos: GenerarCuponesEntrada, gerente: Gerente, session: Sesion, ints: Ints
) -> list[CuponSalida]:
    nuevos = await cupones.generar(
        session, ints, gerente, datos.descuento_pct, datos.cantidad, datos.vence_at
    )
    ids = {c.id for c in nuevos}
    return [c for c in await cupones.listar_todos(session, ints) if c.id in ids]


@router.get("/medicos", response_model=list[MedicoSalida], summary="Médicos Tratantes (E33)")
async def medicos(_: Gerente, session: Sesion) -> list[MedicoSalida]:
    return await cupones.medicos(session)


@router.post("/cupones/asignar", response_model=Ok, summary="Asignar Cupones a Médico Tratante (E33)")
async def asignar_cupones(datos: AsignarCuponesEntrada, _: Gerente, session: Sesion) -> Ok:
    await cupones.asignar_a_medico(session, datos.cupon_ids, datos.medico_id)
    return Ok()
