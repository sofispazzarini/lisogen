"""`/auth`: E1, E15, E26, E29 (registro de profesionales) y E7 (ingreso, verificación de
dispositivo y cambio de contraseña)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.api.deps import Ints, Sesion, UsuarioActual, dispositivo, usuario_opcional
from app.domain.enums import RolUsuario
from app.domain.errores import ErrorNegocio
from app.models import Especialidad, Usuario
from app.schemas.auth import (
    CambioPasswordEntrada,
    IngresoSalida,
    LoginEntrada,
    RefreshEntrada,
    RegistroEntrada,
    UsuarioSalida,
    VerificarEntrada,
)
from app.schemas.comun import Error, Opcion
from app.services import auth
from app.services.auth import Dispositivo, ResultadoIngreso

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={401: {"model": Error}, 409: {"model": Error}, 422: {"model": Error}, 429: {"model": Error}},
)

Disp = Annotated[Dispositivo, Depends(dispositivo)]


def _salida(r: ResultadoIngreso) -> IngresoSalida:
    return IngresoSalida(
        estado=r.estado,
        access_token=r.access_token,
        refresh_token=r.refresh_token,
        desafio_token=r.desafio_token,
        usuario=UsuarioSalida.model_validate(r.usuario) if r.estado == "OK" else None,
    )


@router.post("/login", response_model=IngresoSalida, summary="Ingresar (E7)")
async def login(datos: LoginEntrada, session: Sesion, ints: Ints, disp: Disp) -> IngresoSalida:
    """Si el dispositivo es nuevo, envía un código por mail (`VERIFICACION_REQUERIDA`). Si la contraseña
    es provisoria, exige cambiarla (`CAMBIO_PASSWORD_REQUERIDO`)."""
    return _salida(await auth.ingresar(session, ints, datos.email, datos.password, disp))


@router.post("/verificar", response_model=IngresoSalida, summary="Verificar dispositivo nuevo (E7)")
async def verificar(datos: VerificarEntrada, session: Sesion, disp: Disp) -> IngresoSalida:
    return _salida(await auth.verificar_codigo(session, datos.desafio_token, datos.codigo, disp))


@router.post("/cambiar-password", response_model=IngresoSalida, summary="Cambiar contraseña (E7)")
async def cambiar_password(
    datos: CambioPasswordEntrada,
    session: Sesion,
    usuario: Annotated[Usuario | None, Depends(usuario_opcional)],
) -> IngresoSalida:
    """Con `desafio_token` (cambio obligatorio del primer ingreso), o con la sesión iniciada y la
    contraseña actual."""
    if datos.desafio_token is None and usuario is None:
        raise ErrorNegocio("NO_AUTENTICADO", "Tenés que ingresar para cambiar la contraseña.", 401)
    resultado = await auth.cambiar_password(
        session,
        datos.password_nueva,
        desafio_token=datos.desafio_token,
        usuario=usuario,
        password_actual=datos.password_actual,
    )
    return _salida(resultado)


@router.post("/refresh", response_model=IngresoSalida, summary="Renovar el access token")
async def refresh(datos: RefreshEntrada, session: Sesion) -> IngresoSalida:
    return _salida(await auth.renovar(session, datos.refresh_token))


@router.post(
    "/registro",
    response_model=UsuarioSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar profesional (E1, E15, E26, E29)",
)
async def registro(datos: RegistroEntrada, session: Sesion) -> UsuarioSalida:
    usuario = await auth.registrar_profesional(
        session,
        rol=RolUsuario(datos.rol),
        nombre=datos.nombre,
        apellido=datos.apellido,
        telefono=datos.telefono,
        email=datos.email,
        password=datos.password,
        matricula=datos.matricula,
        especialidad_ids=datos.especialidad_ids,
    )
    return UsuarioSalida.model_validate(usuario)


@router.get(
    "/especialidades", response_model=list[Opcion], summary="Lista estandarizada de especialidades (E1)"
)
async def especialidades(session: Sesion) -> list[Opcion]:
    filas = await session.scalars(select(Especialidad).order_by(Especialidad.nombre))
    return [Opcion(id=e.id, nombre=e.nombre) for e in filas]


@router.get("/yo", response_model=UsuarioSalida, summary="Usuario de la sesión")
async def yo(usuario: UsuarioActual) -> UsuarioSalida:
    return UsuarioSalida.model_validate(usuario)
