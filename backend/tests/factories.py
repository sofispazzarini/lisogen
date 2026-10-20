"""Constructores mínimos de entidades para tests de integración."""

import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.domain.enums import (
    EstadoEstudio,
    EstadoMuestra,
    EstadoTurno,
    OrigenGen,
    RolUsuario,
    TipoArchivo,
    TipoEstudio,
)
from app.models import (
    Archivo,
    CentroExtraccion,
    DatosCrudos,
    Estudio,
    EstudioGen,
    Gen,
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


CAMINO: list[tuple[EstadoEstudio, RolUsuario | None]] = [
    (EstadoEstudio.POR_PAGAR, RolUsuario.ADMINISTRATIVO),
    (EstadoEstudio.PAGADO, RolUsuario.PACIENTE),
    (EstadoEstudio.TURNO_SACADO, RolUsuario.PACIENTE),
    (EstadoEstudio.LISTO_PARA_RETIRAR, None),
    (EstadoEstudio.EN_CAMINO_LAB_CENTRAL, RolUsuario.TRANSPORTISTA),
    (EstadoEstudio.EN_LAB_CENTRAL, RolUsuario.TRANSPORTISTA),
    (EstadoEstudio.EN_ESPERA_RETIRO, None),
    (EstadoEstudio.EN_VIAJE_COREA, None),
    (EstadoEstudio.EN_ANALISIS_BIOINFORMATICA, RolUsuario.ADMINISTRATIVO),
    (EstadoEstudio.EN_ANALISIS, RolUsuario.BIOINFORMATICO),
    (EstadoEstudio.FINALIZADO, RolUsuario.BIOINFORMATICO),
]
_ESTADO_MUESTRA = {
    EstadoEstudio.LISTO_PARA_RETIRAR: EstadoMuestra.LISTO_PARA_RETIRAR,
    EstadoEstudio.EN_CAMINO_LAB_CENTRAL: EstadoMuestra.EN_CAMINO_LAB_CENTRAL,
    EstadoEstudio.EN_LAB_CENTRAL: EstadoMuestra.EN_LAB_CENTRAL,
    EstadoEstudio.EN_ESPERA_RETIRO: EstadoMuestra.EN_LOTE,
    EstadoEstudio.EN_VIAJE_COREA: EstadoMuestra.EN_VIAJE_COREA,
}


async def estudio_en(
    session: AsyncSession,
    paciente_: Paciente,
    medico: Usuario,
    hasta: EstadoEstudio,
    *,
    bioinformatico: Usuario | None = None,
    genes: tuple[str, ...] = ("GLA",),
    urgente: bool = False,
    centro_id: int | None = None,
    volumen_ml: Decimal = Decimal("4"),
) -> Estudio:
    """Exoma llevado por `transicionar` hasta `hasta`, con Turno, Muestra y datos crudos coherentes.
    Requiere el seed (Centros de Extracción). Para probar servicios sin recorrer toda la API."""
    e = await estudio(session, paciente_, medico, urgente=urgente)
    for simbolo in genes:
        gen = await session.scalar(select(Gen).where(Gen.simbolo == simbolo))
        if gen is None:
            gen = Gen(simbolo=simbolo)
            session.add(gen)
            await session.flush()
        session.add(EstudioGen(estudio_id=e.id, gen_id=gen.id, origen=OrigenGen.API_PATOLOGIA))
    usuarios: dict[RolUsuario, Usuario] = {}
    if bioinformatico is not None:
        usuarios[RolUsuario.BIOINFORMATICO] = bioinformatico
    muestra: Muestra | None = None
    for destino, rol in CAMINO:
        if rol is not None and rol not in usuarios:
            usuarios[rol] = await usuario(session, rol)
        if destino == EstadoEstudio.EN_ANALISIS:
            e.bioinformatico_id = usuarios[RolUsuario.BIOINFORMATICO].id
        await transicionar(session, e, destino, usuarios[rol] if rol else None)
        if destino == EstadoEstudio.LISTO_PARA_RETIRAR:
            cid = centro_id or await session.scalar(
                select(CentroExtraccion.id).order_by(CentroExtraccion.id).limit(1)
            )
            assert cid is not None, "estudio_en requiere el seed (Centros de Extracción)"
            turno = Turno(
                estudio_id=e.id,
                centro_id=cid,
                inicio=datetime(2026, 9, 1, 13, 0, tzinfo=UTC) + timedelta(minutes=15 * (e.id % 30)),
                estado=EstadoTurno.REALIZADO,
            )
            session.add(turno)
            await session.flush()
            muestra = Muestra(estudio_id=e.id, turno_id=turno.id, volumen_ml=volumen_ml)
            session.add(muestra)
            await session.flush()
        if muestra is not None and destino in _ESTADO_MUESTRA:
            muestra.estado = _ESTADO_MUESTRA[destino]
        if destino == EstadoEstudio.EN_ANALISIS_BIOINFORMATICA:
            assert muestra is not None
            muestra.estado = EstadoMuestra.PROCESADA
            contenido = b"datos crudos"
            archivo = Archivo(
                tipo=TipoArchivo.DATOS_CRUDOS,
                nombre="crudos.fastq",
                mime="application/octet-stream",
                tamano_bytes=len(contenido),
                storage_key=f"datos_crudos/{_sufijo()}",
                sha256=hashlib.sha256(contenido).hexdigest(),
            )
            session.add(archivo)
            await session.flush()
            session.add(
                DatosCrudos(
                    estudio_id=e.id,
                    muestra_id=muestra.id,
                    archivo_id=archivo.id,
                    cargado_por=usuarios[RolUsuario.ADMINISTRATIVO].id,
                )
            )
        if destino == hasta:
            break
    await session.flush()
    return e


async def estudio_finalizado(
    session: AsyncSession, paciente_: Paciente, medico: Usuario, bioinformatico: Usuario
) -> Estudio:
    """Exoma FINALIZADO con Muestra procesada y datos crudos, para probar el Reanálisis (E6)."""
    return await estudio_en(
        session, paciente_, medico, EstadoEstudio.FINALIZADO, bioinformatico=bioinformatico, genes=()
    )
