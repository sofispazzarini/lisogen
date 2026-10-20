"""`/administrativo`: tablero, E16 Emitir Presupuesto, E17 Registrar Autorización, E18 Registrar Rechazo
de Obra Social, E19 Seguir Muestra en mapa, E20 Programar retiro con FedEx, E21 Cargar datos crudos,
E22 Solicitar nueva extracción y registro financiero."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.api.deps import Ints, Sesion, ip_cliente, requiere_rol
from app.domain.enums import EstadoEstudio, RolUsuario
from app.domain.errores import ErrorNegocio
from app.models import Estudio, Usuario
from app.schemas.comun import Error, EstudioDetalle, EstudioResumen, Ok
from app.schemas.roles import (
    BuscarEntrada,
    LoteSalida,
    MuestraSalida,
    PresupuestoPrevio,
    ReautorizacionSalida,
    RechazoEntrada,
    ReextraccionEntrada,
    RegistroFinanciero,
    RetiroEntrada,
    UbicacionMuestra,
)
from app.services import consultas, finanzas, laboratorio, logistica, lotes
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


# --- E19 Seguir Muestra en mapa ---------------------------------------------------------------


@router.post(
    "/muestras/buscar", response_model=list[MuestraSalida], summary="Buscar Muestras por Paciente (E19)"
)
async def buscar_muestras(datos: BuscarEntrada, _: Admin, session: Sesion) -> list[MuestraSalida]:
    """Por POST para que el apellido o el DNI buscados no queden en URLs ni logs."""
    return await logistica.buscar_muestras(session, datos.texto)


@router.get(
    "/muestras/{muestra_id}/ubicacion", response_model=UbicacionMuestra, summary="Ubicación en el mapa (E19)"
)
async def ubicacion(muestra_id: int, _: Admin, session: Sesion) -> UbicacionMuestra:
    return await logistica.ubicar_muestra(session, muestra_id)


# --- E20 Lotes y retiro de FedEx --------------------------------------------------------------


@router.get("/lotes", response_model=list[LoteSalida], summary="Lotes")
async def listar_lotes(_: Admin, session: Sesion, ints: Ints) -> list[LoteSalida]:
    return await lotes.listar(session, ints)


@router.post("/lotes/{lote_id}/retiro", response_model=LoteSalida, summary="Programar retiro con FedEx (E20)")
async def programar_retiro(
    lote_id: int, datos: RetiroEntrada, _: Admin, session: Sesion, ints: Ints
) -> LoteSalida:
    return await lotes.programar_retiro(session, ints, lote_id, datos.fecha_hora)


# --- E21 / E22 Laboratorio --------------------------------------------------------------------

MAX_DATOS_CRUDOS_BYTES = 200 * 1024 * 1024


@router.post(
    "/estudios/{estudio_id}/datos-crudos", response_model=Ok, summary="Cargar datos crudos de Corea (E21)"
)
async def datos_crudos(
    estudio_id: int,
    admin: Admin,
    session: Sesion,
    ints: Ints,
    archivo: Annotated[UploadFile, File(description="Archivo de datos crudos recibido de Corea")],
) -> Ok:
    contenido = await archivo.read(MAX_DATOS_CRUDOS_BYTES + 1)
    if len(contenido) > MAX_DATOS_CRUDOS_BYTES:
        raise ErrorNegocio(
            "ARCHIVO_DEMASIADO_GRANDE", "El archivo de datos crudos no puede superar los 200 MB."
        )
    await laboratorio.cargar_datos_crudos(session, ints, admin, estudio_id, archivo.filename or "", contenido)
    return Ok()


@router.post(
    "/estudios/{estudio_id}/reextraccion", response_model=Ok, summary="Solicitar nueva extracción (E22)"
)
async def reextraccion(estudio_id: int, datos: ReextraccionEntrada, admin: Admin, session: Sesion) -> Ok:
    await laboratorio.solicitar_reextraccion(session, admin, estudio_id, datos.detalle)
    return Ok()
