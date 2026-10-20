"""E30 Dar de alta Patología, E31 Modificar Patología."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado
from app.models import Gen, Patologia, PatologiaGen, PatologiaSintomaSecundario, SnomedConcepto
from app.schemas.comun import Concepto
from app.schemas.roles import PatologiaEntrada, PatologiaSalida
from app.services.comun import ahora


async def listar(session: AsyncSession) -> list[PatologiaSalida]:
    patologias = list(await session.scalars(select(Patologia).order_by(Patologia.nombre)))
    conceptos = {c.concept_id: c.termino for c in await session.scalars(select(SnomedConcepto))}
    genes: dict[int, list[str]] = {}
    for pid, simbolo in await session.execute(
        select(PatologiaGen.patologia_id, Gen.simbolo)
        .join(Gen, Gen.id == PatologiaGen.gen_id)
        .order_by(Gen.simbolo)
    ):
        genes.setdefault(pid, []).append(simbolo)

    def concepto(cid: int) -> Concepto:
        return Concepto(concept_id=cid, termino=conceptos.get(cid, str(cid)))

    return [
        PatologiaSalida(
            id=p.id,
            nombre=p.nombre,
            es_pompe=p.es_pompe,
            sintoma_cardinal=concepto(p.sintoma_cardinal_id),
            secundarios=sorted((concepto(s.concept_id) for s in p.secundarios), key=lambda c: c.termino),
            genes=genes.get(p.id, []),
        )
        for p in patologias
    ]


async def _validar(
    session: AsyncSession, datos: PatologiaEntrada, excluir_id: int | None = None
) -> list[int]:
    secundarios = sorted(set(datos.secundarios_ids))
    if datos.sintoma_cardinal_id in secundarios:
        raise ErrorNegocio("SINTOMA_REPETIDO", "El síntoma cardinal no puede ser también secundario.")
    if len(secundarios) < 2:
        raise ErrorNegocio("SECUNDARIOS_INSUFICIENTES", "Elegí al menos dos síntomas secundarios distintos.")
    todos = {datos.sintoma_cardinal_id, *secundarios}
    conocidos = set(
        await session.scalars(select(SnomedConcepto.concept_id).where(SnomedConcepto.concept_id.in_(todos)))
    )
    if conocidos != todos:
        raise ErrorNegocio("SINTOMA_DESCONOCIDO", "Algún síntoma no está en el catálogo SNOMED.")
    repetida = await session.scalar(
        select(Patologia.id).where(
            func.lower(Patologia.nombre) == datos.nombre.lower(), Patologia.id != (excluir_id or 0)
        )
    )
    if repetida is not None:
        raise Conflicto("PATOLOGIA_EXISTENTE", "Ya existe una Patología con ese nombre.")
    return secundarios


async def dar_de_alta(session: AsyncSession, datos: PatologiaEntrada) -> Patologia:
    secundarios = await _validar(session, datos)
    patologia = Patologia(
        nombre=datos.nombre, sintoma_cardinal_id=datos.sintoma_cardinal_id, es_pompe=datos.es_pompe
    )
    patologia.secundarios = [PatologiaSintomaSecundario(concept_id=c) for c in secundarios]
    session.add(patologia)
    await session.flush()
    return patologia


async def modificar(session: AsyncSession, patologia_id: int, datos: PatologiaEntrada) -> Patologia:
    """E31: los cambios valen para las próximas altas de Paciente (Validar Diagnóstico)."""
    patologia = await session.get(Patologia, patologia_id)
    if patologia is None:
        raise NoEncontrado("Patología", "la")
    secundarios = await _validar(session, datos, excluir_id=patologia.id)
    patologia.nombre = datos.nombre
    patologia.sintoma_cardinal_id = datos.sintoma_cardinal_id
    patologia.es_pompe = datos.es_pompe
    patologia.secundarios = [PatologiaSintomaSecundario(concept_id=c) for c in secundarios]
    patologia.updated_at = ahora()
    await session.flush()
    return patologia
