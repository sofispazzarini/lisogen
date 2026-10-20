"""Constructores mínimos de entidades para tests de integración."""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.domain.enums import RolUsuario, TipoEstudio
from app.models import Estudio, Paciente, ProfesionalMedico, Usuario
from app.services.transiciones import registrar_alta

PASSWORD = "Clave-segura-2026"


def _sufijo() -> str:
    return uuid.uuid4().hex[:8]


async def usuario(
    session: AsyncSession,
    rol: RolUsuario,
    email: str | None = None,
    *,
    debe_cambiar: bool = False,
    password: str = PASSWORD,
) -> Usuario:
    u = Usuario(
        email=email or f"{rol.value.lower()}-{_sufijo()}@test.com.ar",
        password_hash=security.hashear_password(password),
        rol=rol,
        nombre="Prueba",
        apellido=rol.value.title(),
        telefono="1145550000",
        debe_cambiar_password=debe_cambiar,
    )
    session.add(u)
    await session.flush()
    if rol in (RolUsuario.MEDICO_TRATANTE, RolUsuario.GERENTE_MEDICO):
        session.add(ProfesionalMedico(usuario_id=u.id, matricula=f"MN {_sufijo()}"))
        await session.flush()
    return u


async def paciente(
    session: AsyncSession,
    medico: Usuario,
    *,
    con_cuenta: bool = True,
    fecha_nacimiento: date = date(1990, 5, 20),
    obra_social_id: int | None = None,
) -> Paciente:
    cuenta = await usuario(session, RolUsuario.PACIENTE) if con_cuenta else None
    p = Paciente(
        usuario_id=cuenta.id if cuenta else None,
        dni=str(uuid.uuid4().int)[:8],
        nombre="Juana",
        apellido=f"Pérez {_sufijo()}",
        fecha_nacimiento=fecha_nacimiento,
        telefono="1145550001",
        email_contacto=cuenta.email if cuenta else f"sin-cuenta-{_sufijo()}@test.com.ar",
        es_menor_al_alta=False,
        obra_social_id=obra_social_id,
        resumen_historia_clinica="Resumen de prueba.",
        medico_alta_id=medico.id,
    )
    session.add(p)
    await session.flush()
    return p


async def estudio(
    session: AsyncSession,
    paciente_: Paciente,
    medico: Usuario,
    *,
    tipo: TipoEstudio = TipoEstudio.EXOMA,
    origen: Estudio | None = None,
    urgente: bool = False,
) -> Estudio:
    e = Estudio(
        codigo=f"EST-TEST-{_sufijo()}",
        paciente_id=paciente_.id,
        medico_tratante_id=medico.id,
        tipo=tipo,
        estudio_origen_id=origen.id if origen else None,
        urgente=urgente,
    )
    session.add(e)
    await session.flush()
    await registrar_alta(session, e, medico)
    await session.flush()
    return e
