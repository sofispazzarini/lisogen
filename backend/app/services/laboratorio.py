"""E21 Cargar datos crudos de Corea y E22 Solicitar nueva extracción."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    EstadoEstudio,
    EstadoLote,
    EstadoMuestra,
    MotivoReextraccion,
    TipoArchivo,
    TipoEstudio,
)
from app.domain.errores import Conflicto, ErrorNegocio
from app.integrations.registro import Integraciones
from app.models import DatosCrudos, Estudio, Lote, Muestra, SolicitudReextraccion, Usuario
from app.services.comun import ahora, guardar_archivo
from app.services.estudios import notificar_bioinformaticos, obtener_estudio
from app.services.transiciones import transicionar, volver_a_habilitante


async def _muestra_en_corea(session: AsyncSession, estudio: Estudio) -> Muestra:
    if estudio.tipo != TipoEstudio.EXOMA or estudio.estado != EstadoEstudio.EN_VIAJE_COREA:
        raise Conflicto("ESTUDIO_SIN_MUESTRA_EN_COREA", "El Estudio no tiene una Muestra en Corea.")
    muestra = await session.scalar(
        select(Muestra)
        .where(Muestra.estudio_id == estudio.id, Muestra.estado == EstadoMuestra.EN_VIAJE_COREA)
        .with_for_update()
    )
    if muestra is None:
        raise Conflicto("ESTUDIO_SIN_MUESTRA_EN_COREA", "El Estudio no tiene una Muestra en Corea.")
    return muestra


async def cargar_datos_crudos(
    session: AsyncSession,
    ints: Integraciones,
    admin: Usuario,
    estudio_id: int,
    nombre_archivo: str,
    contenido: bytes,
) -> Estudio:
    """E21: el archivo llegó por mail desde Corea. Se guarda en MinIO, el Estudio pasa a En análisis por
    bioinformática y se avisa a todos los Bioinformáticos."""
    estudio = await obtener_estudio(session, estudio_id, para_actualizar=True)
    muestra = await _muestra_en_corea(session, estudio)
    if not contenido:
        raise ErrorNegocio("ARCHIVO_VACIO", "El archivo de datos crudos está vacío.")
    archivo = await guardar_archivo(
        session,
        ints,
        tipo=TipoArchivo.DATOS_CRUDOS,
        nombre=nombre_archivo or f"{estudio.codigo}-datos-crudos",
        mime="application/octet-stream",
        contenido=contenido,
        subido_por=admin.id,
    )
    session.add(
        DatosCrudos(estudio_id=estudio.id, muestra_id=muestra.id, archivo_id=archivo.id, cargado_por=admin.id)
    )
    muestra.estado = EstadoMuestra.PROCESADA
    if muestra.lote_id:
        lote = await session.get(Lote, muestra.lote_id)
        if lote is not None and lote.estado == EstadoLote.EN_VIAJE_COREA:
            lote.estado, lote.recibido_at = EstadoLote.RECIBIDO, ahora()  # SUPUESTO S20
    await transicionar(
        session, estudio, EstadoEstudio.EN_ANALISIS_BIOINFORMATICA, admin, "Datos crudos recibidos de Corea"
    )
    await notificar_bioinformaticos(session, estudio)
    return estudio


async def solicitar_reextraccion(
    session: AsyncSession, admin: Usuario, estudio_id: int, detalle: str | None
) -> EstadoEstudio:
    """E22 / SUPUESTO S10: ADN desnaturalizado. Mismo Estudio, sin costo; vuelve a Pagado o Autorizado para
    sacar un nuevo Turno y se avisa al Paciente y al Médico Tratante. (Las de < 2 ml son automáticas, E25.)"""
    estudio = await obtener_estudio(session, estudio_id, para_actualizar=True)
    muestra = await _muestra_en_corea(session, estudio)
    muestra.estado = EstadoMuestra.DESNATURALIZADA
    session.add(
        SolicitudReextraccion(
            estudio_id=estudio.id,
            muestra_id=muestra.id,
            motivo=MotivoReextraccion.DESNATURALIZADA,
            solicitado_por=admin.id,
        )
    )
    motivo = "El ADN de la Muestra se desnaturalizó. Sacá un nuevo Turno: la extracción no tiene costo."
    if detalle:
        motivo = f"{motivo} Detalle: {detalle}"
    return await volver_a_habilitante(session, estudio, admin, motivo)
