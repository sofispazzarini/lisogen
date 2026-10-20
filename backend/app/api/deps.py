"""Dependencias de FastAPI: sesión transaccional, integraciones, usuario autenticado y control por rol."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.db import get_session
from app.domain.enums import RolUsuario
from app.domain.errores import ErrorNegocio, SinPermiso
from app.integrations.registro import Integraciones, get_adaptadores
from app.models import Usuario
from app.services.auth import Dispositivo

# scope="function": el commit ocurre antes de enviar la respuesta (si falla, el cliente recibe el error).
Sesion = Annotated[AsyncSession, Depends(get_session, scope="function")]

_bearer = HTTPBearer(auto_error=False, description="Access token JWT")


def get_integraciones(session: Sesion) -> Integraciones:
    return Integraciones(session, get_adaptadores())


Ints = Annotated[Integraciones, Depends(get_integraciones)]


def ip_cliente(request: Request) -> str | None:
    return request.client.host if request.client else None


def dispositivo(
    request: Request,
    user_agent: Annotated[str, Header()] = "",
    x_device_id: Annotated[
        str, Header(description="Identificador del dispositivo generado por el front")
    ] = "",
) -> Dispositivo:
    return Dispositivo(user_agent=user_agent, device_id=x_device_id, ip=ip_cliente(request))


_NO_AUTENTICADO = ErrorNegocio("NO_AUTENTICADO", "Tenés que ingresar para usar esta función.", 401)


async def usuario_opcional(
    session: Sesion, credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]
) -> Usuario | None:
    if credenciales is None:
        return None
    payload = security.leer_token(credenciales.credentials, "access")
    if payload is None:
        raise ErrorNegocio("SESION_VENCIDA", "Tu sesión venció. Ingresá de nuevo.", 401)
    usuario = await session.get(Usuario, int(payload["sub"]))
    if usuario is None or not usuario.activo:
        raise _NO_AUTENTICADO
    if usuario.debe_cambiar_password:
        raise ErrorNegocio(
            "CAMBIO_PASSWORD_REQUERIDO", "Tenés que cambiar la contraseña antes de seguir.", 403
        )
    return usuario


async def usuario_actual(usuario: Annotated[Usuario | None, Depends(usuario_opcional)]) -> Usuario:
    if usuario is None:
        raise _NO_AUTENTICADO
    return usuario


UsuarioActual = Annotated[Usuario, Depends(usuario_actual)]


def requiere_rol(*roles: RolUsuario) -> Callable[..., Coroutine[Any, Any, Usuario]]:
    """Dependencia de autorización por rol: `Depends(requiere_rol(RolUsuario.PACIENTE))`."""
    permitidos = frozenset(roles)

    async def _verificar(usuario: UsuarioActual) -> Usuario:
        if usuario.rol not in permitidos:
            raise SinPermiso("Tu rol no tiene acceso a esta sección.")
        return usuario

    return _verificar
