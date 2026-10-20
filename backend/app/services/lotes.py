"""E25 Confirmar llegada al Laboratorio Central (armado y sellado de Lotes) y E20 Programar
retiro con FedEx."""

import csv
import io
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import get_settings
from app.domain.enums import (
    EstadoEstudio,
    EstadoLote,
    EstadoMuestra,
    MotivoReextraccion,
    RolUsuario,
    TipoArchivo,
)
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado
from app.domain.reglas import TZ_AR, MuestraParaLote, armar_lotes, validar_horario_retiro, volumen_suficiente
from app.integrations.registro import Integraciones
from app.models import (
    Estudio,
    EstudioPatologia,
    Lote,
    Muestra,
    OrdenDelDiaParada,
    Patologia,
    SolicitudReextraccion,
    Usuario,
)
from app.schemas.roles import LlegadaSalida, LoteSalida
from app.services.comun import ahora, feriados, guardar_archivo, notificar, siguiente_codigo, url_archivo
from app.services.logistica import hoy, orden_de
from app.services.transiciones import transicionar, volver_a_habilitante


async def _lote_en_formacion(session: AsyncSession) -> Lote:
    lote = await session.scalar(select(Lote).where(Lote.estado == EstadoLote.EN_FORMACION).with_for_update())
    if lote is None:
        nuevo_id, codigo = await siguiente_codigo(session, "lote_id_seq", "LOTE")
        lote = Lote(id=nuevo_id, codigo=codigo)
        session.add(lote)
        await session.flush()
    return lote


async def _csv_ministerio(session: AsyncSession, lote: Lote) -> bytes:
    """CSV para el Ministerio de Salud: sólo códigos, sin datos personales del Paciente."""
    filas = await session.execute(
        select(Muestra, Estudio)
        .join(Estudio, Estudio.id == Muestra.estudio_id)
        .where(Muestra.lote_id == lote.id)
        .order_by(Muestra.id)
    )
    salida = io.StringIO()
    w = csv.writer(salida, lineterminator="\n")
    w.writerow(["lote", "estudio", "nro_extraccion", "volumen_ml", "urgente", "patologias"])
    for m, e in filas:
        patologias = await session.scalars(
            select(Patologia.nombre)
            .join(EstudioPatologia, EstudioPatologia.patologia_id == Patologia.id)
            .where(EstudioPatologia.estudio_id == e.id)
            .order_by(Patologia.nombre)
        )
        w.writerow(
            [
                lote.codigo,
                e.codigo,
                m.nro_extraccion,
                m.volumen_ml,
                "SI" if e.urgente else "NO",
                "|".join(patologias),
            ]
        )
    return salida.getvalue().encode("utf-8")


async def sellar(session: AsyncSession, ints: Integraciones, lote: Lote) -> None:
    """E25 ep. 4–5: CSV al Ministerio, PDF de autorización asociado, Lote sellado En Espera de Retiro."""
    csv_bytes = await _csv_ministerio(session, lote)
    pdf = await ints.ministerio.autorizar_lote(codigo_lote=lote.codigo, csv=csv_bytes)
    lote.csv_ministerio_id = (
        await guardar_archivo(
            session,
            ints,
            tipo=TipoArchivo.CSV_MINISTERIO,
            nombre=f"{lote.codigo}.csv",
            mime="text/csv",
            contenido=csv_bytes,
            subido_por=None,
        )
    ).id
    lote.autorizacion_ministerio_id = (
        await guardar_archivo(
            session,
            ints,
            tipo=TipoArchivo.AUTORIZACION_MINISTERIO_PDF,
            nombre=f"{lote.codigo}-autorizacion.pdf",
            mime="application/pdf",
            contenido=pdf,
            subido_por=None,
        )
    ).id
    lote.sellado_at = ahora()
    lote.estado = EstadoLote.EN_ESPERA_RETIRO
    await session.flush()
    for estudio in await session.scalars(
        select(Estudio).join(Muestra, Muestra.estudio_id == Estudio.id).where(Muestra.lote_id == lote.id)
    ):
        await transicionar(
            session, estudio, EstadoEstudio.EN_ESPERA_RETIRO, None, f"Lote {lote.codigo} sellado"
        )
    urgente = " con un Estudio Urgente" if lote.incluye_urgente else ""
    for admin_id in await session.scalars(
        select(Usuario.id).where(Usuario.rol == RolUsuario.ADMINISTRATIVO, Usuario.activo.is_(True))
    ):
        notificar(
            session,
            admin_id,
            f"Lote {lote.codigo} sellado{urgente}",
            "El Ministerio de Salud autorizó el envío. Programá el retiro con FedEx.",
        )


async def confirmar_llegada(
    session: AsyncSession, ints: Integraciones, usuario: Usuario, fecha: date | None = None
) -> LlegadaSalida:
    """E25: las Muestras de < 2 ml no entran al Lote y piden nueva extracción; el resto entra al Lote
    en formación, que se sella con 10 Muestras o con un Urgente (el excedente va al siguiente)."""
    orden = await orden_de(session, usuario, fecha or hoy())
    if orden.llegada_lab_at is not None:
        raise Conflicto("LLEGADA_CONFIRMADA", "Ya confirmaste la llegada de hoy.")
    muestras = list(
        await session.scalars(
            select(Muestra)
            .join(OrdenDelDiaParada, OrdenDelDiaParada.id == Muestra.parada_id)
            .where(
                OrdenDelDiaParada.orden_id == orden.id, Muestra.estado == EstadoMuestra.EN_CAMINO_LAB_CENTRAL
            )
            .order_by(Muestra.id)
            .with_for_update()
        )
    )
    if not muestras:
        raise ErrorNegocio("SIN_MUESTRAS_EN_CAMINO", "No llevás Muestras recolectadas para entregar.")
    momento = ahora()
    orden.llegada_lab_at = momento
    insuficientes: list[str] = []
    para_lote: list[MuestraParaLote] = []
    estudios: dict[int, Estudio] = {}
    for m in muestras:
        m.llegada_lab_at = momento
        estudio = await session.get(Estudio, m.estudio_id)
        assert estudio is not None
        estudios[m.id] = estudio
        if not volumen_suficiente(m.volumen_ml):
            m.estado = EstadoMuestra.VOLUMEN_INSUFICIENTE
            session.add(
                SolicitudReextraccion(
                    estudio_id=estudio.id,
                    muestra_id=m.id,
                    motivo=MotivoReextraccion.VOLUMEN_INSUFICIENTE,
                    solicitado_por=None,
                )
            )
            await volver_a_habilitante(
                session,
                estudio,
                None,
                f"La Muestra llegó con {m.volumen_ml} ml (mínimo 2 ml). "
                "Sacá un nuevo Turno: la extracción no tiene costo.",
            )
            insuficientes.append(estudio.codigo)
            continue
        m.estado = EstadoMuestra.EN_LAB_CENTRAL
        await transicionar(
            session,
            estudio,
            EstadoEstudio.EN_LAB_CENTRAL,
            usuario,
            "Muestra entregada en el Laboratorio Central",
        )
        para_lote.append(MuestraParaLote(m.id, estudio.urgente))

    sellados: list[str] = []
    abierto: Lote | None = None
    if para_lote:
        actual = await _lote_en_formacion(session)
        cantidad = int(await session.scalar(select(func.count()).where(Muestra.lote_id == actual.id)) or 0)
        por_id = {m.id: m for m in muestras}
        for grupo in armar_lotes(cantidad, actual.incluye_urgente, para_lote):
            lote = actual if grupo.continua_actual else await _lote_en_formacion(session)
            for mid in grupo.muestras:
                por_id[mid].lote_id, por_id[mid].estado = lote.id, EstadoMuestra.EN_LOTE
            lote.incluye_urgente = lote.incluye_urgente or grupo.incluye_urgente
            await session.flush()
            if grupo.sellar:
                await sellar(session, ints, lote)
                sellados.append(lote.codigo)
            else:
                abierto = lote
    return LlegadaSalida(
        recibidas=len(muestras),
        volumen_insuficiente=insuficientes,
        lotes_sellados=sellados,
        lote_en_formacion=abierto.codigo if abierto else None,
    )


# --- E20 Programar retiro con FedEx -----------------------------------------------------------


async def _salida(session: AsyncSession, ints: Integraciones, lote: Lote) -> LoteSalida:
    estudios = list(
        await session.scalars(
            select(Estudio.codigo)
            .join(Muestra, Muestra.estudio_id == Estudio.id)
            .where(Muestra.lote_id == lote.id)
            .order_by(Estudio.codigo)
        )
    )
    return LoteSalida(
        id=lote.id,
        codigo=lote.codigo,
        estado=lote.estado,
        incluye_urgente=lote.incluye_urgente,
        cantidad_muestras=len(estudios),
        estudios=estudios,
        sellado_at=lote.sellado_at,
        retiro_programado_at=lote.retiro_programado_at,
        fedex_confirmado_at=lote.fedex_confirmado_at,
        csv_url=await url_archivo(session, ints, lote.csv_ministerio_id),
        autorizacion_url=await url_archivo(session, ints, lote.autorizacion_ministerio_id),
    )


async def listar(session: AsyncSession, ints: Integraciones) -> list[LoteSalida]:
    lotes = await session.scalars(
        select(Lote).order_by(Lote.incluye_urgente.desc(), Lote.created_at.desc()).limit(100)
    )
    return [await _salida(session, ints, lote) for lote in lotes]


def url_webhook(lote: Lote) -> str:
    """URL que FedEx usa para confirmar el retiro. Lleva un token HMAC: no es adivinable y no tiene
    datos personales."""
    base = get_settings().api_public_url.rstrip("/")
    return f"{base}/integraciones/fedex/lotes/{lote.id}/{security.token_webhook('lote', lote.id)}"


async def programar_retiro(
    session: AsyncSession, ints: Integraciones, lote_id: int, momento: datetime
) -> LoteSalida:
    """E20 ep. 1–3: envía a FedEx día, hora y URL del Lote. L–V 9 a 18 sin feriados, también con Urgentes."""
    lote = await session.get(Lote, lote_id, with_for_update=True)
    if lote is None:
        raise NoEncontrado("Lote")
    if lote.estado != EstadoLote.EN_ESPERA_RETIRO:
        raise Conflicto("LOTE_NO_SELLADO", "Sólo se programa el retiro de un Lote En Espera de Retiro.")
    dia = momento.astimezone(TZ_AR).date()
    validar_horario_retiro(momento, await feriados(session, dia, dia), ahora())
    lote.fedex_url = url_webhook(lote)
    await ints.fedex.programar_retiro(fecha_hora=momento, url_lote=lote.fedex_url)
    lote.retiro_programado_at = momento
    return await _salida(session, ints, lote)


async def confirmar_retiro_fedex(session: AsyncSession, lote_id: int, token: str) -> None:
    """E20 ep. 4–5: FedEx confirma el retiro en la URL; el Lote y sus Muestras viajan a Corea. Idempotente."""
    if not security.verificar_token_webhook("lote", lote_id, token):
        raise NoEncontrado("Lote")
    lote = await session.get(Lote, lote_id, with_for_update=True)
    if lote is None:
        raise NoEncontrado("Lote")
    if lote.estado == EstadoLote.EN_VIAJE_COREA:
        return
    if lote.estado != EstadoLote.EN_ESPERA_RETIRO or lote.retiro_programado_at is None:
        raise Conflicto("RETIRO_NO_PROGRAMADO", "El Lote no tiene un retiro programado.")
    lote.estado, lote.fedex_confirmado_at = EstadoLote.EN_VIAJE_COREA, ahora()
    for m in await session.scalars(
        select(Muestra).where(Muestra.lote_id == lote.id, Muestra.estado == EstadoMuestra.EN_LOTE)
    ):
        m.estado = EstadoMuestra.EN_VIAJE_COREA
        estudio = await session.get(Estudio, m.estudio_id)
        assert estudio is not None
        await transicionar(
            session, estudio, EstadoEstudio.EN_VIAJE_COREA, None, f"FedEx retiró el Lote {lote.codigo}"
        )
