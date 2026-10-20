"""E1, E7, E15, E26, E29: registro de profesionales, ingreso, verificación de dispositivo y contraseña."""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import get_settings
from app.db import al_confirmar
from app.domain.enums import RolUsuario
from app.domain.errores import Conflicto, ErrorNegocio
from app.integrations.registro import Integraciones
from app.models import (
    CodigoVerificacion,
    DispositivoConfiable,
    Especialidad,
    ProfesionalEspecialidad,
    ProfesionalMedico,
    Usuario,
)
from app.services.comun import ahora

ROLES_AUTORREGISTRO: Final = frozenset(
    {
        RolUsuario.MEDICO_TRATANTE,
        RolUsuario.ADMINISTRATIVO,
        RolUsuario.BIOINFORMATICO,
        RolUsuario.GERENTE_MEDICO,
    }
)
ROLES_CON_MATRICULA: Final = frozenset({RolUsuario.MEDICO_TRATANTE, RolUsuario.GERENTE_MEDICO})
MAX_INTENTOS_CODIGO: Final = 5


class LimitadorIntentos:
    """Rate limit en memoria con ventana deslizante (DECISIONES T2)."""

    def __init__(self) -> None:
        self._intentos: dict[str, deque[float]] = defaultdict(deque)

    def registrar(self, clave: str) -> None:
        s = get_settings()
        ahora_s = time.monotonic()
        cola = self._intentos[clave]
        while cola and ahora_s - cola[0] > s.rate_limit_ventana_seg:
            cola.popleft()
        if len(cola) >= s.rate_limit_intentos:
            raise ErrorNegocio(
                "DEMASIADOS_INTENTOS",
                "Hiciste demasiados intentos. Esperá unos minutos y probá de nuevo.",
                429,
            )
        cola.append(ahora_s)

    def limpiar(self, clave: str) -> None:
        self._intentos.pop(clave, None)

    def reiniciar(self) -> None:
        self._intentos.clear()


limitador = LimitadorIntentos()


@dataclass(frozen=True)
class ResultadoIngreso:
    estado: Literal["OK", "VERIFICACION_REQUERIDA", "CAMBIO_PASSWORD_REQUERIDO"]
    usuario: Usuario
    access_token: str | None = None
    refresh_token: str | None = None
    desafio_token: str | None = None


@dataclass(frozen=True)
class Dispositivo:
    user_agent: str
    device_id: str
    ip: str | None

    @property
    def huella(self) -> str:
        return security.huella_dispositivo(self.user_agent, self.device_id)


def _tokens(usuario: Usuario) -> ResultadoIngreso:
    return ResultadoIngreso(
        "OK",
        usuario,
        access_token=security.crear_token(usuario.id, usuario.rol, "access"),
        refresh_token=security.crear_token(usuario.id, usuario.rol, "refresh"),
    )


def _siguiente_paso(usuario: Usuario) -> ResultadoIngreso:
    if usuario.debe_cambiar_password:
        return ResultadoIngreso(
            "CAMBIO_PASSWORD_REQUERIDO",
            usuario,
            desafio_token=security.crear_token(usuario.id, usuario.rol, "cambio_password"),
        )
    return _tokens(usuario)


async def _dispositivo_confiable(session: AsyncSession, usuario: Usuario, disp: Dispositivo) -> bool:
    if not get_settings().verificar_dispositivo:
        return True
    d = await session.scalar(
        select(DispositivoConfiable).where(
            DispositivoConfiable.usuario_id == usuario.id, DispositivoConfiable.huella == disp.huella
        )
    )
    if d is None:
        return False
    d.ultimo_uso, d.ultima_ip = ahora(), disp.ip
    return True


async def ingresar(
    session: AsyncSession, ints: Integraciones, email: str, password: str, disp: Dispositivo
) -> ResultadoIngreso:
    """E7: usuario y contraseña; dispositivo nuevo → código por mail; credenciales provisorias → cambio."""
    clave_rl = f"login:{disp.ip}:{email.lower()}"
    limitador.registrar(clave_rl)
    usuario = await session.scalar(select(Usuario).where(Usuario.email == email))
    if usuario is None:
        security.verificar_password_senuelo(password)
    if (
        usuario is None
        or not usuario.activo
        or not security.verificar_password(password, usuario.password_hash)
    ):
        raise ErrorNegocio("CREDENCIALES_INVALIDAS", "El mail o la contraseña no son correctos.", 401)
    limitador.limpiar(clave_rl)

    if await _dispositivo_confiable(session, usuario, disp):
        return _siguiente_paso(usuario)

    codigo = security.codigo_verificacion()
    session.add(
        CodigoVerificacion(
            usuario_id=usuario.id,
            codigo_hash=security.hash_codigo(codigo),
            expira_at=ahora() + timedelta(minutes=get_settings().jwt_desafio_min),
        )
    )
    destinatario = usuario.email

    async def _enviar_codigo() -> None:
        await ints.mail.enviar(
            destinatario=destinatario,
            asunto="LisoGen: código de verificación",
            cuerpo=(
                f"Tu código de verificación es {codigo}. Vence en {get_settings().jwt_desafio_min} minutos.\n"
                "Lo pedimos porque ingresaste desde un equipo que no usaste antes. "
                "Si no fuiste vos, cambiá tu contraseña."
            ),
        )

    al_confirmar(session, _enviar_codigo)
    return ResultadoIngreso(
        "VERIFICACION_REQUERIDA",
        usuario,
        desafio_token=security.crear_token(usuario.id, usuario.rol, "verificacion"),
    )


async def _usuario_de_desafio(session: AsyncSession, token: str, tipo: security.TipoToken) -> Usuario:
    payload = security.leer_token(token, tipo)
    if payload is None:
        raise ErrorNegocio("DESAFIO_VENCIDO", "La sesión de ingreso venció. Ingresá de nuevo.", 401)
    usuario = await session.get(Usuario, int(payload["sub"]))
    if usuario is None or not usuario.activo:
        raise ErrorNegocio("DESAFIO_VENCIDO", "La sesión de ingreso venció. Ingresá de nuevo.", 401)
    return usuario


async def verificar_codigo(
    session: AsyncSession, desafio_token: str, codigo: str, disp: Dispositivo
) -> ResultadoIngreso:
    usuario = await _usuario_de_desafio(session, desafio_token, "verificacion")
    limitador.registrar(f"verificar:{disp.ip}:{usuario.id}")
    cv = await session.scalar(
        select(CodigoVerificacion)
        .where(
            CodigoVerificacion.usuario_id == usuario.id,
            CodigoVerificacion.usado_at.is_(None),
            CodigoVerificacion.expira_at > ahora(),
        )
        .order_by(CodigoVerificacion.id.desc())
        .limit(1)
        .with_for_update()
    )
    if cv is None or cv.intentos >= MAX_INTENTOS_CODIGO:
        raise ErrorNegocio(
            "CODIGO_VENCIDO", "El código venció o se bloqueó. Ingresá de nuevo para recibir otro."
        )
    if not security.hmac_igual(cv.codigo_hash, security.hash_codigo(codigo.strip())):
        cv.intentos += 1
        await session.commit()  # el intento fallido cuenta aunque la request termine en error
        raise ErrorNegocio("CODIGO_INCORRECTO", "El código no es correcto.")
    cv.usado_at = ahora()
    existente = await session.scalar(
        select(DispositivoConfiable).where(
            DispositivoConfiable.usuario_id == usuario.id, DispositivoConfiable.huella == disp.huella
        )
    )
    if existente is None:
        session.add(DispositivoConfiable(usuario_id=usuario.id, huella=disp.huella, ultima_ip=disp.ip))
    return _siguiente_paso(usuario)


async def cambiar_password(
    session: AsyncSession,
    password_nueva: str,
    *,
    desafio_token: str | None = None,
    usuario: Usuario | None = None,
    password_actual: str | None = None,
) -> ResultadoIngreso:
    """E7: cambio obligatorio con el desafío del ingreso, o cambio voluntario con la contraseña actual."""
    if desafio_token is not None:
        usuario = await _usuario_de_desafio(session, desafio_token, "cambio_password")
    elif (
        usuario is None
        or password_actual is None
        or not security.verificar_password(password_actual, usuario.password_hash)
    ):
        raise ErrorNegocio("PASSWORD_ACTUAL_INCORRECTA", "La contraseña actual no es correcta.")
    if not security.password_es_robusta(password_nueva):
        raise ErrorNegocio(
            "PASSWORD_DEBIL", "La contraseña nueva debe tener al menos 10 caracteres, con letras y números."
        )
    if security.verificar_password(password_nueva, usuario.password_hash):
        raise ErrorNegocio("PASSWORD_REPETIDA", "La contraseña nueva tiene que ser distinta de la anterior.")
    usuario.password_hash = security.hashear_password(password_nueva)
    usuario.debe_cambiar_password = False
    return _tokens(usuario)


async def renovar(session: AsyncSession, refresh_token: str) -> ResultadoIngreso:
    payload = security.leer_token(refresh_token, "refresh")
    usuario = await session.get(Usuario, int(payload["sub"])) if payload else None
    if usuario is None or not usuario.activo or usuario.debe_cambiar_password:
        raise ErrorNegocio("SESION_VENCIDA", "Tu sesión venció. Ingresá de nuevo.", 401)
    return _tokens(usuario)


async def registrar_profesional(
    session: AsyncSession,
    *,
    rol: RolUsuario,
    nombre: str,
    apellido: str,
    telefono: str,
    email: str,
    password: str,
    matricula: str | None,
    especialidad_ids: list[int],
) -> Usuario:
    """E1, E15, E26, E29. SUPUESTO S4: autorregistro con acceso inmediato."""
    if rol not in ROLES_AUTORREGISTRO:
        raise ErrorNegocio("ROL_NO_REGISTRABLE", "Ese rol no se puede registrar desde acá.")
    if not security.password_es_robusta(password):
        raise ErrorNegocio(
            "PASSWORD_DEBIL", "La contraseña debe tener al menos 10 caracteres, con letras y números."
        )
    if rol in ROLES_CON_MATRICULA:
        if not matricula or not especialidad_ids:
            raise ErrorNegocio(
                "DATOS_PROFESIONALES_FALTANTES", "Ingresá la matrícula y al menos una especialidad."
            )
        validas = set(
            await session.scalars(select(Especialidad.id).where(Especialidad.id.in_(especialidad_ids)))
        )
        if validas != set(especialidad_ids):
            raise ErrorNegocio(
                "ESPECIALIDAD_INVALIDA", "Alguna especialidad no está en la lista estandarizada."
            )
        if await session.scalar(select(ProfesionalMedico).where(ProfesionalMedico.matricula == matricula)):
            raise Conflicto("MATRICULA_EN_USO", "Ya hay un profesional registrado con esa matrícula.")
    if await session.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise Conflicto("EMAIL_EN_USO", "Ya hay una cuenta registrada con ese mail.")
    usuario = Usuario(
        email=email,
        password_hash=security.hashear_password(password),
        rol=rol,
        nombre=nombre,
        apellido=apellido,
        telefono=telefono,
    )
    session.add(usuario)
    await session.flush()
    if rol in ROLES_CON_MATRICULA:
        session.add(ProfesionalMedico(usuario_id=usuario.id, matricula=matricula))
        await session.flush()
        session.add_all(
            ProfesionalEspecialidad(usuario_id=usuario.id, especialidad_id=e)
            for e in sorted(set(especialidad_ids))
        )
    return usuario
