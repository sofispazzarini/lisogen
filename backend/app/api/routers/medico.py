"""`/medico`: E2 Dar de alta Paciente, E3 Cargar Familiograma, E4 Dar de alta Estudio,
E5 Asignar Cupón a Paciente, E6 Solicitar Reanálisis. Un Médico sólo ve a sus Pacientes y Estudios."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select

from app.api.deps import Ints, Sesion, ip_cliente, requiere_rol
from app.domain.enums import RolUsuario
from app.domain.errores import NoEncontrado
from app.models import Estudio, ObraSocial, Patologia, Usuario
from app.schemas.comun import Concepto, Error, EstudioDetalle, EstudioResumen, Ok, Opcion, ResultadoSalida
from app.schemas.roles import (
    AsignarCuponEntrada,
    BuscarEntrada,
    CuponSalida,
    EstudioAlta,
    FamiliogramaEntrada,
    GenesSugeridos,
    PacienteAlta,
    PacienteFicha,
    PacienteResumen,
    PatologiaSalida,
    ReanalisisEntrada,
)
from app.services import consultas, cupones, estudios, pacientes, patologias, resultados
from app.services.comun import auditar

router = APIRouter(
    prefix="/medico",
    tags=["medico"],
    responses={403: {"model": Error}, 404: {"model": Error}, 409: {"model": Error}, 422: {"model": Error}},
)
Medico = Annotated[Usuario, Depends(requiere_rol(RolUsuario.MEDICO_TRATANTE))]


# --- Catálogos para los formularios -----------------------------------------------------------


@router.get("/snomed", response_model=list[Concepto], summary="Buscar síntomas SNOMED (E2)")
async def buscar_snomed(
    _: Medico, ints: Ints, q: Annotated[str, Query(min_length=2, max_length=60)]
) -> list[Concepto]:
    return [Concepto(concept_id=c.concept_id, termino=c.termino) for c in await ints.snomed.buscar(texto=q)]


@router.get(
    "/patologias", response_model=list[PatologiaSalida], summary="Patologías con sus síntomas (E2, E4)"
)
async def listar_patologias(_: Medico, session: Sesion) -> list[PatologiaSalida]:
    return await patologias.listar(session)


@router.get("/obras-sociales", response_model=list[Opcion], summary="Obras Sociales (E2)")
async def obras_sociales(_: Medico, session: Sesion) -> list[Opcion]:
    return [
        Opcion(id=o.id, nombre=o.nombre)
        for o in await session.scalars(select(ObraSocial).order_by(ObraSocial.nombre))
    ]


@router.get(
    "/patologias/{patologia_id}/genes",
    response_model=GenesSugeridos,
    summary="Genes de la API de bioinformática (E4)",
)
async def genes_sugeridos(patologia_id: int, _: Medico, session: Sesion, ints: Ints) -> GenesSugeridos:
    patologia = await session.get(Patologia, patologia_id)
    if patologia is None:
        raise NoEncontrado("Patología", "la")
    genes = await estudios.genes_de_patologia(session, ints, patologia)
    return GenesSugeridos(
        patologia_id=patologia.id,
        patologia=patologia.nombre,
        genes=[g.simbolo for g in genes],
        hallazgos_secundarios=await ints.bioinformatica.genes_hallazgos_secundarios(),
    )


# --- Pacientes (E2, E3) -----------------------------------------------------------------------


@router.post(
    "/pacientes",
    response_model=PacienteResumen,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta Paciente (E2)",
)
async def alta_paciente(datos: PacienteAlta, medico: Medico, session: Sesion, ints: Ints) -> PacienteResumen:
    """Valida el Diagnóstico (síntoma cardinal o dos secundarios) y envía las credenciales por mail.
    Si llegan `familiares`, carga también el Familiograma (E3)."""
    paciente = await pacientes.dar_de_alta_paciente(session, ints, medico, datos)
    return (await pacientes.buscar_pacientes(session, medico, paciente.dni))[0]


@router.post("/pacientes/buscar", response_model=list[PacienteResumen], summary="Buscar mis Pacientes")
async def buscar_pacientes(datos: BuscarEntrada, medico: Medico, session: Sesion) -> list[PacienteResumen]:
    """Por POST para que el DNI o el apellido buscados no queden en URLs ni logs."""
    return await pacientes.buscar_pacientes(session, medico, datos.texto)


@router.get(
    "/pacientes/{paciente_id}", response_model=PacienteFicha, summary="Ficha del Paciente con historial (E6)"
)
async def ficha_paciente(
    paciente_id: int, medico: Medico, session: Sesion, ints: Ints, request: Request
) -> PacienteFicha:
    paciente = await pacientes.paciente_del_medico(session, medico, paciente_id)
    return await pacientes.ficha(session, ints, medico, paciente, ip_cliente(request))


@router.post("/pacientes/{paciente_id}/familiograma", response_model=Ok, summary="Cargar Familiograma (E3)")
async def familiograma(
    paciente_id: int, datos: FamiliogramaEntrada, medico: Medico, session: Sesion, ints: Ints
) -> Ok:
    paciente = await pacientes.paciente_del_medico(session, medico, paciente_id)
    await pacientes.cargar_familiograma(session, ints, medico, paciente, datos.familiares)
    return Ok()


# --- Estudios (E4, E6) ------------------------------------------------------------------------


@router.post(
    "/estudios",
    response_model=EstudioResumen,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta Estudio (E4)",
)
async def alta_estudio(datos: EstudioAlta, medico: Medico, session: Sesion, ints: Ints) -> EstudioResumen:
    estudio = await estudios.dar_de_alta_estudio(session, ints, medico, datos)
    return await consultas.resumen(session, estudio.id)


@router.get("/estudios", response_model=list[EstudioResumen], summary="Mis Estudios")
async def mis_estudios(medico: Medico, session: Sesion) -> list[EstudioResumen]:
    return await consultas.resumenes(session, Estudio.medico_tratante_id == medico.id)


@router.get(
    "/estudios/{estudio_id}", response_model=EstudioDetalle, summary="Detalle del Estudio con historial"
)
async def detalle_estudio(
    estudio_id: int, medico: Medico, session: Sesion, ints: Ints, request: Request
) -> EstudioDetalle:
    estudio = await estudios.estudio_del_medico(session, medico, estudio_id)
    auditar(session, medico.id, "VER_ESTUDIO", "estudio", estudio.id, ip_cliente(request))
    return await consultas.detalle(session, ints, estudio)


@router.post(
    "/estudios/{estudio_id}/reanalisis",
    response_model=EstudioResumen,
    status_code=status.HTTP_201_CREATED,
    summary="Solicitar Reanálisis (E6)",
)
async def reanalisis(
    estudio_id: int, datos: ReanalisisEntrada, medico: Medico, session: Sesion, ints: Ints
) -> EstudioResumen:
    estudio = await estudios.solicitar_reanalisis(session, ints, medico, estudio_id, datos)
    return await consultas.resumen(session, estudio.id)


# --- Cupones (E5) -----------------------------------------------------------------------------


@router.get("/cupones", response_model=list[CuponSalida], summary="Mis Cupones (E5)")
async def mis_cupones(medico: Medico, session: Sesion, ints: Ints) -> list[CuponSalida]:
    return await cupones.del_medico(session, ints, medico)


@router.post("/cupones/{cupon_id}/asignar", response_model=Ok, summary="Asignar Cupón a Paciente (E5)")
async def asignar_cupon(cupon_id: int, datos: AsignarCuponEntrada, medico: Medico, session: Sesion) -> Ok:
    await cupones.asignar_a_paciente(session, medico, cupon_id, datos.paciente_id)
    return Ok()


@router.get(
    "/estudios/{estudio_id}/resultado", response_model=ResultadoSalida, summary="Resultado del Estudio (E28)"
)
async def resultado(
    estudio_id: int, medico: Medico, session: Sesion, ints: Ints, request: Request
) -> ResultadoSalida:
    estudio = await estudios.estudio_del_medico(session, medico, estudio_id)
    return await resultados.resultado(session, ints, medico, estudio, ip_cliente(request))
