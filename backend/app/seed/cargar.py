"""Carga los datos de ejemplo. `vaciar` + `cargar` = `make seed` (recarga desde cero)."""

from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.domain.enums import RolUsuario, TipoSospecha
from app.models import (
    CentroExtraccion,
    DiagnosticoPresuntivo,
    Especialidad,
    Feriado,
    Gen,
    ObraSocial,
    Paciente,
    PacienteSintoma,
    Patologia,
    PatologiaGen,
    PatologiaSintomaSecundario,
    ProfesionalEspecialidad,
    ProfesionalMedico,
    Provincia,
    SnomedConcepto,
    Transportista,
    Usuario,
)
from app.seed import datos


async def vaciar(session: AsyncSession) -> None:
    """TRUNCATE de todas las tablas del esquema (menos alembic_version), reiniciando secuencias."""
    tablas = (
        await session.scalars(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        )
    ).all()
    if tablas:
        await session.execute(text(f"TRUNCATE {', '.join(tablas)} RESTART IDENTITY CASCADE"))


async def _catalogos(session: AsyncSession) -> None:
    session.add_all(Provincia(nombre=n) for n in datos.PROVINCIAS)
    session.add_all(Especialidad(nombre=n) for n in datos.ESPECIALIDADES)
    session.add_all(ObraSocial(nombre=n, codigo_externo=c) for n, c in datos.OBRAS_SOCIALES)
    session.add_all(SnomedConcepto(concept_id=c, termino=t) for c, t in datos.SNOMED.items())
    session.add_all(Feriado(fecha=f, descripcion=d) for f, d in datos.FERIADOS_2026)
    simbolos = [
        g for _, _, _, genes in datos.PATOLOGIAS.values() for g in genes
    ] + datos.GENES_HALLAZGOS_SECUNDARIOS
    session.add_all(Gen(simbolo=s) for s in dict.fromkeys(simbolos))
    await session.flush()

    genes = {g.simbolo: g.id for g in await session.scalars(select(Gen))}
    for nombre, (cardinal, secundarios, es_pompe, simbolos_pat) in datos.PATOLOGIAS.items():
        patologia = Patologia(nombre=nombre, sintoma_cardinal_id=cardinal, es_pompe=es_pompe)
        patologia.secundarios = [PatologiaSintomaSecundario(concept_id=c) for c in secundarios]
        session.add(patologia)
        await session.flush()
        session.add_all(PatologiaGen(patologia_id=patologia.id, gen_id=genes[s]) for s in simbolos_pat)

    provincias = {p.nombre: p.id for p in await session.scalars(select(Provincia))}
    session.add_all(
        CentroExtraccion(
            nombre=n, direccion=d, provincia_id=provincias[p], latitud=Decimal(lat), longitud=Decimal(lon)
        )
        for n, d, p, lat, lon in datos.CENTROS
    )
    await session.flush()


async def _usuarios(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    password_hash = security.hashear_password(datos.PASSWORD_DEMO)
    especialidades = {e.nombre: e.id for e in await session.scalars(select(Especialidad))}
    provincias = {p.nombre: p.id for p in await session.scalars(select(Provincia))}
    usuarios: dict[RolUsuario, Usuario] = {}
    for d in datos.USUARIOS:
        u = Usuario(
            email=d.email,
            password_hash=password_hash,
            rol=d.rol,
            nombre=d.nombre,
            apellido=d.apellido,
            telefono=d.telefono,
        )
        session.add(u)
        await session.flush()
        if d.matricula:
            session.add(ProfesionalMedico(usuario_id=u.id, matricula=d.matricula))
            await session.flush()
            session.add_all(
                ProfesionalEspecialidad(usuario_id=u.id, especialidad_id=especialidades[e])
                for e in d.especialidades
            )
        if d.provincia:
            session.add(Transportista(usuario_id=u.id, provincia_id=provincias[d.provincia]))
        usuarios[d.rol] = u
    await session.flush()
    return usuarios


async def _paciente_demo(session: AsyncSession, usuarios: dict[RolUsuario, Usuario]) -> Paciente:
    cuenta, medico = usuarios[RolUsuario.PACIENTE], usuarios[RolUsuario.MEDICO_TRATANTE]
    d = datos.PACIENTE_DEMO
    paciente = Paciente(
        usuario_id=cuenta.id,
        dni=d.dni,
        nombre=cuenta.nombre,
        apellido=cuenta.apellido,
        fecha_nacimiento=d.fecha_nacimiento,
        telefono=cuenta.telefono,
        email_contacto=cuenta.email,
        es_menor_al_alta=False,
        resumen_historia_clinica=d.resumen_historia_clinica,
        medico_alta_id=medico.id,
    )
    session.add(paciente)
    await session.flush()
    session.add_all(PacienteSintoma(paciente_id=paciente.id, concept_id=c) for c in d.sintomas)
    patologia_id = await session.scalar(select(Patologia.id).where(Patologia.nombre == d.patologia))
    session.add(
        DiagnosticoPresuntivo(
            paciente_id=paciente.id,
            patologia_id=patologia_id,
            tipo_sospecha=TipoSospecha.CLINICA,
            medico_id=medico.id,
        )
    )
    await session.flush()
    return paciente


async def cargar(session: AsyncSession) -> None:
    """Catálogos, un usuario por rol y el Paciente demo. Los 6 Estudios de ejemplo se agregan en la
    etapa 4, cuando estén los servicios que recorren cada Estado (así el historial es real)."""
    await _catalogos(session)
    usuarios = await _usuarios(session)
    await _paciente_demo(session, usuarios)
