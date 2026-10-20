"""E4 Dar de alta Estudio, E6 Solicitar Reanálisis, E21 Cargar datos crudos de Corea."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    EstadoEstudio,
    OrigenGen,
    RolUsuario,
    TipoEstudio,
)
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado
from app.domain.reglas import es_urgente
from app.integrations.registro import Integraciones
from app.models import (
    DatosCrudos,
    Estudio,
    EstudioGen,
    EstudioPatologia,
    Gen,
    Paciente,
    Patologia,
    PatologiaGen,
    Usuario,
)
from app.schemas.roles import EstudioAlta, ReanalisisEntrada
from app.services.comun import ahora, notificar, siguiente_codigo
from app.services.pacientes import paciente_del_medico
from app.services.transiciones import registrar_alta, transicionar

# --- Acceso por dueño -------------------------------------------------------------------------


async def estudio_del_medico(session: AsyncSession, medico: Usuario, estudio_id: int) -> Estudio:
    estudio = await session.get(Estudio, estudio_id)
    if estudio is None or estudio.medico_tratante_id != medico.id:
        raise NoEncontrado("Estudio")
    return estudio


async def estudio_del_paciente(session: AsyncSession, usuario: Usuario, estudio_id: int) -> Estudio:
    """Un Paciente sólo ve sus Estudios (404 para no revelar la existencia de otros)."""
    estudio = await session.get(Estudio, estudio_id)
    if estudio is None:
        raise NoEncontrado("Estudio")
    paciente = await session.get(Paciente, estudio.paciente_id)
    if paciente is None or paciente.usuario_id != usuario.id:
        raise NoEncontrado("Estudio")
    return estudio


async def obtener_estudio(
    session: AsyncSession, estudio_id: int, *, para_actualizar: bool = False
) -> Estudio:
    consulta = select(Estudio).where(Estudio.id == estudio_id)
    if para_actualizar:
        consulta = consulta.with_for_update()
    estudio = await session.scalar(consulta)
    if estudio is None:
        raise NoEncontrado("Estudio")
    return estudio


# --- Genes ------------------------------------------------------------------------------------


async def gen_por_simbolo(session: AsyncSession, simbolo: str) -> Gen:
    gen = await session.scalar(select(Gen).where(Gen.simbolo == simbolo))
    if gen is None:
        gen = Gen(simbolo=simbolo)
        session.add(gen)
        await session.flush()
    return gen


async def genes_de_patologia(session: AsyncSession, ints: Integraciones, patologia: Patologia) -> list[Gen]:
    """E4 ep. 2: consulta la API de bioinformática y cachea el resultado en patologia_gen."""
    simbolos = await ints.bioinformatica.genes_por_patologia(patologia=patologia.nombre)
    genes = [await gen_por_simbolo(session, s.upper()) for s in simbolos]
    cacheados = set(
        await session.scalars(select(PatologiaGen.gen_id).where(PatologiaGen.patologia_id == patologia.id))
    )
    session.add_all(
        PatologiaGen(patologia_id=patologia.id, gen_id=g.id) for g in genes if g.id not in cacheados
    )
    return genes


async def _armar_genes(
    session: AsyncSession,
    ints: Integraciones,
    estudio: Estudio,
    patologias: list[Patologia],
    manuales: list[str],
    hallazgos: bool,
    excluir: set[int] | None = None,
) -> int:
    """Registra los genes del Estudio y devuelve cuántos cuentan para el Presupuesto."""
    excluir = excluir or set()
    vistos: dict[int, EstudioGen] = {}
    for p in patologias:
        for g in await genes_de_patologia(session, ints, p):
            if g.id not in vistos and g.id not in excluir:
                vistos[g.id] = EstudioGen(
                    estudio_id=estudio.id, gen_id=g.id, origen=OrigenGen.API_PATOLOGIA, patologia_id=p.id
                )
    for simbolo in dict.fromkeys(manuales):
        g = await gen_por_simbolo(session, simbolo)
        if g.id not in vistos and g.id not in excluir:
            vistos[g.id] = EstudioGen(estudio_id=estudio.id, gen_id=g.id, origen=OrigenGen.MANUAL)
    a_presupuestar = len(vistos)
    if a_presupuestar == 0:
        raise ErrorNegocio("ESTUDIO_SIN_GENES", "El Estudio tiene que analizar al menos un gen.")
    if hallazgos:
        for simbolo in await ints.bioinformatica.genes_hallazgos_secundarios():
            g = await gen_por_simbolo(session, simbolo.upper())
            if g.id not in vistos:
                vistos[g.id] = EstudioGen(
                    estudio_id=estudio.id, gen_id=g.id, origen=OrigenGen.HALLAZGO_SECUNDARIO
                )
    session.add_all(vistos.values())
    return a_presupuestar


async def _patologias(session: AsyncSession, ids: list[int]) -> list[Patologia]:
    patologias = list(
        await session.scalars(select(Patologia).where(Patologia.id.in_(ids)).order_by(Patologia.id))
    )
    if len(patologias) != len(set(ids)):
        raise ErrorNegocio("PATOLOGIA_INVALIDA", "Alguna Patología no existe.")
    return patologias


async def _nuevo_estudio(session: AsyncSession, **campos: object) -> Estudio:
    nuevo_id, codigo = await siguiente_codigo(session, "estudio_id_seq", "EST")
    estudio = Estudio(id=nuevo_id, codigo=codigo, estado=EstadoEstudio.CREADO, **campos)
    session.add(estudio)
    await session.flush()
    return estudio


# --- E4 ---------------------------------------------------------------------------------------


async def dar_de_alta_estudio(
    session: AsyncSession, ints: Integraciones, medico: Usuario, datos: EstudioAlta
) -> Estudio:
    paciente = await paciente_del_medico(session, medico, datos.paciente_id)
    patologias = await _patologias(session, datos.patologia_ids)
    urgente = es_urgente(any(p.es_pompe for p in patologias), paciente.fecha_nacimiento, ahora().date())
    estudio = await _nuevo_estudio(
        session,
        paciente_id=paciente.id,
        medico_tratante_id=medico.id,
        tipo=TipoEstudio.EXOMA,
        evalua_hallazgos_secundarios=datos.evalua_hallazgos_secundarios,
        urgente=urgente,
    )
    session.add_all(EstudioPatologia(estudio_id=estudio.id, patologia_id=p.id) for p in patologias)
    await _armar_genes(
        session,
        ints.para_estudio(estudio.id),
        estudio,
        patologias,
        datos.genes_manuales,
        datos.evalua_hallazgos_secundarios,
    )
    await registrar_alta(session, estudio, medico)
    return estudio


# --- E6 ---------------------------------------------------------------------------------------


async def notificar_bioinformaticos(session: AsyncSession, estudio: Estudio) -> None:
    """E21 ep. 4: aviso a todos los Bioinformáticos (Urgente primero en el asunto)."""
    ids = await session.scalars(
        select(Usuario.id).where(Usuario.rol == RolUsuario.BIOINFORMATICO, Usuario.activo.is_(True))
    )
    prefijo = "URGENTE · " if estudio.urgente else ""
    for uid in ids:
        notificar(
            session,
            uid,
            f"{prefijo}Estudio {estudio.codigo} listo para análisis",
            "Hay datos crudos disponibles. Tomá el Estudio desde la lista de Pendientes.",
            estudio.id,
        )


async def solicitar_reanalisis(
    session: AsyncSession, ints: Integraciones, medico: Usuario, estudio_id: int, datos: ReanalisisEntrada
) -> Estudio:
    """SUPUESTO S3: sólo sobre un exoma FINALIZADO; reutiliza sus datos crudos, sin Turno ni logística."""
    previo = await estudio_del_medico(session, medico, estudio_id)
    exoma = await session.get(Estudio, previo.estudio_origen_id) if previo.estudio_origen_id else previo
    assert exoma is not None
    if previo.estado != EstadoEstudio.FINALIZADO:
        raise Conflicto("ESTUDIO_NO_FINALIZADO", "Sólo se puede reanalizar un Estudio Finalizado.")
    if await session.scalar(select(DatosCrudos.id).where(DatosCrudos.estudio_id == exoma.id)) is None:
        raise Conflicto("SIN_DATOS_CRUDOS", "El exoma original no tiene datos crudos para reanalizar.")
    if not datos.patologia_ids and not datos.genes_manuales:
        raise ErrorNegocio("ESTUDIO_SIN_GENES", "Indicá una Patología o genes nuevos para el Reanálisis.")
    paciente = await session.get(Paciente, exoma.paciente_id)
    assert paciente is not None
    patologias = await _patologias(session, datos.patologia_ids)
    ya_analizados = set(
        await session.scalars(
            select(EstudioGen.gen_id)
            .join(Estudio, Estudio.id == EstudioGen.estudio_id)
            .where((Estudio.id == exoma.id) | (Estudio.estudio_origen_id == exoma.id))
            .where(EstudioGen.origen != OrigenGen.HALLAZGO_SECUNDARIO)
        )
    )
    estudio = await _nuevo_estudio(
        session,
        paciente_id=exoma.paciente_id,
        medico_tratante_id=medico.id,
        tipo=TipoEstudio.REANALISIS,
        estudio_origen_id=exoma.id,
        evalua_hallazgos_secundarios=False,
        urgente=es_urgente(any(p.es_pompe for p in patologias), paciente.fecha_nacimiento, ahora().date()),
    )
    session.add_all(EstudioPatologia(estudio_id=estudio.id, patologia_id=p.id) for p in patologias)
    try:
        await _armar_genes(
            session,
            ints.para_estudio(estudio.id),
            estudio,
            patologias,
            datos.genes_manuales,
            False,
            ya_analizados,
        )
    except ErrorNegocio as e:
        raise ErrorNegocio(
            "SIN_GENES_NUEVOS", "Todos los genes indicados ya se analizaron en este exoma."
        ) from e
    await registrar_alta(session, estudio, medico)
    await transicionar(
        session,
        estudio,
        EstadoEstudio.EN_ANALISIS_BIOINFORMATICA,
        None,
        f"Reanálisis del exoma {exoma.codigo}",
    )
    await notificar_bioinformaticos(session, estudio)
    return estudio
