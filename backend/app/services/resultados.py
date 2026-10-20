"""E13 Consultar Resultado del Estudio (Paciente) y su lectura por el Médico Tratante. Cada lectura
queda en `auditoria_acceso` (Ley 25.326)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import EstadoEstudio
from app.domain.errores import NoEncontrado
from app.integrations.registro import Integraciones
from app.models import Estudio, Gen, Resultado, ResultadoVariante, Usuario, Variante
from app.schemas.comun import ResultadoSalida, VarianteResultado
from app.services.comun import auditar, url_archivo


async def resultado(
    session: AsyncSession, ints: Integraciones, usuario: Usuario, estudio: Estudio, ip: str | None
) -> ResultadoSalida:
    r = await session.scalar(select(Resultado).where(Resultado.estudio_id == estudio.id))
    if estudio.estado != EstadoEstudio.FINALIZADO or r is None:
        raise NoEncontrado("Resultado")
    auditar(session, usuario.id, "VER_RESULTADO", "resultado", r.id, ip)
    filas = await session.execute(
        select(Gen.simbolo, Variante.nomenclatura, ResultadoVariante)
        .join(Variante, Variante.id == ResultadoVariante.variante_id)
        .join(Gen, Gen.id == Variante.gen_id)
        .where(ResultadoVariante.resultado_id == r.id)
        .order_by(ResultadoVariante.hallazgo_secundario, Gen.simbolo)
    )
    return ResultadoSalida(
        tipo=r.tipo,
        confirmado_at=r.confirmado_at,
        variantes=[
            VarianteResultado(
                gen=gen,
                nomenclatura=nom,
                clasificacion=rv.clasificacion,
                hallazgo_secundario=rv.hallazgo_secundario,
            )
            for gen, nom, rv in filas
        ],
        pdf_url=await url_archivo(session, ints, r.pdf_id),
    )
