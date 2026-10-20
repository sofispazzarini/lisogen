"""Constructores mínimos de entidades para tests de integración."""

import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.domain.enums import EstadoEstudio, EstadoMuestra, EstadoTurno, RolUsuario, TipoArchivo, TipoEstudio
from app.models import (
    Archivo,
    CentroExtraccion,
    DatosCrudos,
    Estudio,
    Muestra,
    Paciente,
    ProfesionalMedico,
    Turno,
    Usuario,
)
from app.seed.cargar import cargar
from app.services.transiciones import registrar_alta, transicionar

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


def headers(u: Usuario) -> dict[str, str]:
    """Authorization con un access token válido (el flujo de ingreso se prueba en test_auth).

    Usa la identidad del objeto sin tocar la base: tras un request con error, el rollback expira los
    atributos. La API carga el Usuario por id, así que el rol del token es informativo."""
    identidad = inspect(u).identity
    assert identidad is not None
    rol = u.__dict__.get("rol", "")
    return {"Authorization": f"Bearer {security.crear_token(int(identidad[0]), str(rol), 'access')}"}


async def seed(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    """Carga el seed (catálogos, usuarios demo, Paciente demo) y devuelve un usuario por rol."""
    await cargar(session)
    return {u.rol: u for u in await session.scalars(select(Usuario))}


async def estudio_finalizado(
    session: AsyncSession, paciente_: Paciente, medico: Usuario, bioinformatico: Usuario
) -> Estudio:
    """Exoma FINALIZADO con Muestra procesada y datos crudos, para probar el Reanálisis (E6)."""
    e = await estudio(session, paciente_, medico)
    pasos = [
        EstadoEstudio.POR_PAGAR,
        EstadoEstudio.PAGADO,
        EstadoEstudio.TURNO_SACADO,
        EstadoEstudio.LISTO_PARA_RETIRAR,
        EstadoEstudio.EN_CAMINO_LAB_CENTRAL,
        EstadoEstudio.EN_LAB_CENTRAL,
        EstadoEstudio.EN_ESPERA_RETIRO,
        EstadoEstudio.EN_VIAJE_COREA,
        EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        EstadoEstudio.EN_ANALISIS,
        EstadoEstudio.FINALIZADO,
    ]
    actores = {
        EstadoEstudio.POR_PAGAR: RolUsuario.ADMINISTRATIVO,
        EstadoEstudio.PAGADO: RolUsuario.PACIENTE,
        EstadoEstudio.TURNO_SACADO: RolUsuario.PACIENTE,
        EstadoEstudio.EN_CAMINO_LAB_CENTRAL: RolUsuario.TRANSPORTISTA,
        EstadoEstudio.EN_LAB_CENTRAL: RolUsuario.TRANSPORTISTA,
        EstadoEstudio.EN_ANALISIS_BIOINFORMATICA: RolUsuario.ADMINISTRATIVO,
        EstadoEstudio.EN_ANALISIS: RolUsuario.BIOINFORMATICO,
        EstadoEstudio.FINALIZADO: RolUsuario.BIOINFORMATICO,
    }
    usuarios: dict[RolUsuario, Usuario] = {RolUsuario.BIOINFORMATICO: bioinformatico}
    for destino in pasos:
        rol = actores.get(destino)
        if rol is not None and rol not in usuarios:
            usuarios[rol] = await usuario(session, rol)
        if destino == EstadoEstudio.EN_ANALISIS:
            e.bioinformatico_id = bioinformatico.id
        await transicionar(session, e, destino, usuarios[rol] if rol else None)

    centro = await session.scalar(select(CentroExtraccion).limit(1))
    assert centro is not None, "estudio_finalizado requiere el seed (Centros de Extracción)"
    turno = Turno(
        estudio_id=e.id,
        centro_id=centro.id,
        inicio=datetime(2026, 9, 1, 13, 0, tzinfo=UTC),
        estado=EstadoTurno.REALIZADO,
    )
    session.add(turno)
    await session.flush()
    muestra = Muestra(
        estudio_id=e.id, turno_id=turno.id, volumen_ml=Decimal("4"), estado=EstadoMuestra.PROCESADA
    )
    contenido = b"datos crudos"
    archivo = Archivo(
        tipo=TipoArchivo.DATOS_CRUDOS,
        nombre="crudos.fastq",
        mime="application/octet-stream",
        tamano_bytes=len(contenido),
        storage_key=f"datos_crudos/{_sufijo()}",
        sha256=hashlib.sha256(contenido).hexdigest(),
    )
    session.add_all([muestra, archivo])
    await session.flush()
    session.add(
        DatosCrudos(
            estudio_id=e.id, muestra_id=muestra.id, archivo_id=archivo.id, cargado_por=bioinformatico.id
        )
    )
    await session.flush()
    return e
