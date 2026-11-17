"""E2, E30 y E31: búsqueda de síntomas SNOMED CT.

Con `SNOMED_MODO=api` las sugerencias vienen de la API de terminología y cada concepto sugerido se copia a
la caché local `snomed_concepto`, que es a lo que apuntan los síntomas de los Pacientes y de las Patologías.
Si la API falla, la búsqueda sigue con lo que ya está en la caché: no se frena el alta del Paciente."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import mock
from app.integrations.ports import ConceptoSnomed, ErrorSnomed
from app.integrations.registro import Integraciones
from app.models import SnomedConcepto


async def _guardar_en_cache(session: AsyncSession, conceptos: list[ConceptoSnomed]) -> None:
    """Copia los conceptos nuevos. Si ya estaba, se conserva el término que ya tenía."""
    if not conceptos:
        return
    await session.execute(
        insert(SnomedConcepto)
        .values([{"concept_id": c.concept_id, "termino": c.termino} for c in conceptos])
        .on_conflict_do_nothing(index_elements=["concept_id"])
    )


async def buscar(session: AsyncSession, ints: Integraciones, texto: str) -> list[ConceptoSnomed]:
    try:
        conceptos = await ints.snomed.buscar(texto=texto)
    except ErrorSnomed:  # queda en integracion_log; el Médico sigue con la caché local
        return await mock.SnomedCacheLocal(session).buscar(texto=texto)
    await _guardar_en_cache(session, conceptos)
    return conceptos
