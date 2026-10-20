"""`/paciente`: E8 Pagar Presupuesto, E9 Aplicar Cupón, E10 Solicitar reautorización, E11 Sacar Turno,
E12 Cancelar Turno, E14 Consultar Chatbot. Un Paciente sólo ve sus Estudios."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from sqlalchemy import select

from app.api.deps import Ints, Sesion, ip_cliente, requiere_rol
from app.domain.enums import RolUsuario
from app.domain.errores import ErrorNegocio, NoEncontrado
from app.models import Estudio, Paciente, Usuario
from app.schemas.comun import (
    CentroSalida,
    Error,
    EstudioDetalle,
    EstudioResumen,
    Ok,
    PresupuestoSalida,
    ResultadoSalida,
    TurnoSalida,
)
from app.schemas.roles import AgendaDia, ChatEntrada, ChatMensajeSalida, CuponSalida, PagoSalida, TurnoEntrada
from app.services import chatbot, consultas, cupones, finanzas, resultados, turnos
from app.services.estudios import estudio_del_paciente

router = APIRouter(
    prefix="/paciente",
    tags=["paciente"],
    responses={403: {"model": Error}, 404: {"model": Error}, 409: {"model": Error}, 422: {"model": Error}},
)
PacienteU = Annotated[Usuario, Depends(requiere_rol(RolUsuario.PACIENTE))]

MAX_PDF_BYTES = 10 * 1024 * 1024


async def _paciente(session: Sesion, usuario: Usuario) -> Paciente:
    p = await session.scalar(select(Paciente).where(Paciente.usuario_id == usuario.id))
    if p is None:
        raise NoEncontrado("Paciente")
    return p


async def _leer_pdf(archivo: UploadFile) -> bytes:
    contenido = await archivo.read(MAX_PDF_BYTES + 1)
    if len(contenido) > MAX_PDF_BYTES:
        raise ErrorNegocio("ARCHIVO_DEMASIADO_GRANDE", "El PDF no puede superar los 10 MB.")
    return contenido


# --- Mis Estudios -----------------------------------------------------------------------------


@router.get("/estudios", response_model=list[EstudioResumen], summary="Mis Estudios")
async def mis_estudios(usuario: PacienteU, session: Sesion) -> list[EstudioResumen]:
    paciente = await _paciente(session, usuario)
    return await consultas.resumenes(
        session, Estudio.paciente_id == paciente.id, orden=[Estudio.created_at.desc(), Estudio.id.desc()]
    )


@router.get("/estudios/{estudio_id}", response_model=EstudioDetalle, summary="Detalle con línea de pasos")
async def detalle(estudio_id: int, usuario: PacienteU, session: Sesion, ints: Ints) -> EstudioDetalle:
    estudio = await estudio_del_paciente(session, usuario, estudio_id)
    return await consultas.detalle(session, ints, estudio)


# --- E8 / E9 Presupuesto, Cupón y pago --------------------------------------------------------


@router.get(
    "/estudios/{estudio_id}/presupuesto", response_model=PresupuestoSalida, summary="Ver Presupuesto (E8)"
)
async def presupuesto(estudio_id: int, usuario: PacienteU, session: Sesion) -> PresupuestoSalida:
    estudio = await estudio_del_paciente(session, usuario, estudio_id)
    salida = await consultas.presupuesto_salida(session, estudio.id)
    if salida is None:
        raise NoEncontrado("Presupuesto")
    return salida


@router.get("/cupones", response_model=list[CuponSalida], summary="Mis Cupones para aplicar (E9)")
async def mis_cupones(usuario: PacienteU, session: Sesion, ints: Ints) -> list[CuponSalida]:
    return await cupones.del_paciente(session, ints, await _paciente(session, usuario))


@router.post("/estudios/{estudio_id}/cupon", response_model=PresupuestoSalida, summary="Aplicar Cupón (E9)")
async def aplicar_cupon(
    estudio_id: int,
    usuario: PacienteU,
    session: Sesion,
    ints: Ints,
    codigo: Annotated[str | None, Form(max_length=40)] = None,
    archivo: Annotated[UploadFile | None, File(description="PDF del Cupón con el QR")] = None,
) -> PresupuestoSalida:
    """Ingresá el código o subí el PDF con el QR. Si el Cupón no es válido, el precio no cambia."""
    estudio = await estudio_del_paciente(session, usuario, estudio_id)
    pdf = await _leer_pdf(archivo) if archivo is not None else None
    await cupones.aplicar(session, ints, await _paciente(session, usuario), estudio, codigo, pdf)
    salida = await consultas.presupuesto_salida(session, estudio.id)
    assert salida is not None
    return salida


@router.post(
    "/estudios/{estudio_id}/pagar", response_model=PagoSalida, summary="Pagar Presupuesto (E8, simulado)"
)
async def pagar(estudio_id: int, usuario: PacienteU, session: Sesion) -> PagoSalida:
    estudio = await estudio_del_paciente(session, usuario, estudio_id)
    pago = await finanzas.pagar(session, usuario, estudio)
    return PagoSalida(referencia=pago.referencia_sim, monto_usd=pago.monto_usd)


# --- E10 Reautorización -----------------------------------------------------------------------


@router.post(
    "/estudios/{estudio_id}/reautorizacion", response_model=Ok, summary="Solicitar reautorización (E10)"
)
async def reautorizacion(
    estudio_id: int,
    usuario: PacienteU,
    session: Sesion,
    ints: Ints,
    archivo: Annotated[UploadFile, File(description="PDF de la decisión judicial")],
) -> Ok:
    estudio = await estudio_del_paciente(session, usuario, estudio_id)
    contenido = await _leer_pdf(archivo)
    await finanzas.solicitar_reautorizacion(
        session, ints, usuario, estudio, "decision-judicial.pdf", contenido
    )
    return Ok()


# --- E11 / E12 Turnos -------------------------------------------------------------------------


@router.get("/centros", response_model=list[CentroSalida], summary="Centros de Extracción para el mapa (E11)")
async def centros(_: PacienteU, session: Sesion) -> list[CentroSalida]:
    return await turnos.centros(session)


@router.get("/centros/{centro_id}/agenda", response_model=AgendaDia, summary="Turnos de un día (E11)")
async def agenda(centro_id: int, _: PacienteU, session: Sesion, fecha: Annotated[date, Query()]) -> AgendaDia:
    return await turnos.agenda(session, centro_id, fecha)


@router.post(
    "/turnos", response_model=TurnoSalida, status_code=status.HTTP_201_CREATED, summary="Sacar Turno (E11)"
)
async def sacar_turno(datos: TurnoEntrada, usuario: PacienteU, session: Sesion, ints: Ints) -> TurnoSalida:
    return await turnos.sacar_turno(session, ints, usuario, datos)


@router.get("/estudios/{estudio_id}/turno", response_model=TurnoSalida, summary="Mi Turno")
async def mi_turno(estudio_id: int, usuario: PacienteU, session: Sesion, ints: Ints) -> TurnoSalida:
    return await turnos.turno_del_estudio(session, ints, usuario, estudio_id)


@router.post("/turnos/{turno_id}/cancelar", response_model=Ok, summary="Cancelar Turno (E12)")
async def cancelar_turno(turno_id: int, usuario: PacienteU, session: Sesion) -> Ok:
    await turnos.cancelar_turno(session, usuario, turno_id)
    return Ok()


# --- E14 Chatbot ------------------------------------------------------------------------------


@router.get("/chatbot", response_model=list[ChatMensajeSalida], summary="Historial del Chatbot (E14)")
async def chatbot_historial(usuario: PacienteU, session: Sesion) -> list[ChatMensajeSalida]:
    return await chatbot.historial(session, usuario)


@router.post("/chatbot", response_model=ChatMensajeSalida, summary="Consultar Chatbot (E14)")
async def chatbot_preguntar(
    datos: ChatEntrada, usuario: PacienteU, session: Sesion, ints: Ints
) -> ChatMensajeSalida:
    return await chatbot.preguntar(session, ints, usuario, datos.pregunta)


# --- E13 Consultar Resultado ------------------------------------------------------------------


@router.get(
    "/estudios/{estudio_id}/resultado", response_model=ResultadoSalida, summary="Consultar Resultado (E13)"
)
async def resultado(
    estudio_id: int, usuario: PacienteU, session: Sesion, ints: Ints, request: Request
) -> ResultadoSalida:
    """Cada lectura queda auditada. El PDF se descarga con una URL firmada de corta duración."""
    estudio = await estudio_del_paciente(session, usuario, estudio_id)
    return await resultados.resultado(session, ints, usuario, estudio, ip_cliente(request))
