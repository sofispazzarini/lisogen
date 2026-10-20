"""E23 Consultar Orden del Día, E24 Recolectar Muestras, posición del Transportista y E19 Seguir Muestra."""

from datetime import date, datetime
from decimal import Decimal
from typing import Final

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.domain.enums import EstadoEstudio, EstadoMuestra, EstadoParada
from app.domain.errores import Conflicto, ErrorNegocio, NoEncontrado
from app.domain.reglas import TZ_AR, es_dia_habil
from app.integrations.ports import Parada, Punto
from app.integrations.registro import Integraciones
from app.models import (
    CentroExtraccion,
    Estudio,
    Lote,
    Muestra,
    OrdenDelDia,
    OrdenDelDiaParada,
    Paciente,
    PosicionTransportista,
    Provincia,
    Transportista,
    Turno,
    Usuario,
)
from app.schemas.comun import CentroSalida
from app.schemas.roles import MuestraSalida, OrdenDelDiaSalida, ParadaSalida, UbicacionMuestra
from app.services.comun import ahora, feriados
from app.services.transiciones import transicionar

COREA: Final = (Decimal("37.566500"), Decimal("126.978000"))  # Seúl: secuenciación del exoma


def hoy() -> date:
    return ahora().astimezone(TZ_AR).date()


def lab_central() -> Punto:
    s = get_settings()
    return Punto(s.lab_central_lat, s.lab_central_lon)


async def _transportista(session: AsyncSession, usuario: Usuario) -> Transportista:
    t = await session.get(Transportista, usuario.id)
    if t is None:
        raise ErrorNegocio("TRANSPORTISTA_SIN_PROVINCIA", "Tu usuario no tiene una provincia asignada.", 403)
    return t


def _muestras_listas_en(centro_id: int):  # type: ignore[no-untyped-def]
    return (
        select(Muestra)
        .join(Turno, Turno.id == Muestra.turno_id)
        .where(Turno.centro_id == centro_id, Muestra.estado == EstadoMuestra.LISTO_PARA_RETIRAR)
    )


# --- Generación (la dispara el job de las 06:00, etapa 5) -------------------------------------


async def crear_orden(
    session: AsyncSession, ints: Integraciones, transportista: Transportista, fecha: date
) -> OrdenDelDia | None:
    """Orden del Día de un Transportista: Centros de su provincia con Muestras Listas para Retirar,
    en el orden que devuelve el módulo de optimización. No se regenera si ya existe (S8)."""
    existente = await session.scalar(
        select(OrdenDelDia).where(
            OrdenDelDia.transportista_id == transportista.usuario_id, OrdenDelDia.fecha == fecha
        )
    )
    if existente is not None:
        return None
    centros = list(
        await session.scalars(
            select(CentroExtraccion)
            .where(
                CentroExtraccion.provincia_id == transportista.provincia_id,
                CentroExtraccion.id.in_(
                    select(Turno.centro_id)
                    .join(Muestra, Muestra.turno_id == Turno.id)
                    .where(Muestra.estado == EstadoMuestra.LISTO_PARA_RETIRAR)
                ),
            )
            .order_by(CentroExtraccion.id)
        )
    )
    if not centros:
        return None
    orden_ids = await ints.rutas.ordenar_paradas(
        origen=lab_central(), paradas=[Parada(c.id, Punto(c.latitud, c.longitud)) for c in centros]
    )
    orden = OrdenDelDia(transportista_id=transportista.usuario_id, fecha=fecha)
    session.add(orden)
    await session.flush()
    session.add_all(
        OrdenDelDiaParada(orden_id=orden.id, centro_id=cid, posicion=pos)
        for pos, cid in enumerate(orden_ids, start=1)
    )
    await session.flush()
    return orden


async def generar_ordenes_del_dia(
    session: AsyncSession, ints: Integraciones, fecha: date
) -> list[OrdenDelDia]:
    """E23 ep. 1–2. Si el día es feriado o fin de semana no se genera Orden del Día (excepción)."""
    if not es_dia_habil(fecha, await feriados(session, fecha, fecha)):
        return []
    ordenes = []
    for t in await session.scalars(select(Transportista).order_by(Transportista.usuario_id)):
        orden = await crear_orden(session, ints, t, fecha)
        if orden is not None:
            ordenes.append(orden)
    return ordenes


# --- E23 Consultar Orden del Día --------------------------------------------------------------


async def orden_de(session: AsyncSession, usuario: Usuario, fecha: date) -> OrdenDelDia:
    await _transportista(session, usuario)
    orden = await session.scalar(
        select(OrdenDelDia).where(OrdenDelDia.transportista_id == usuario.id, OrdenDelDia.fecha == fecha)
    )
    if orden is None:
        raise ErrorNegocio(
            "SIN_ORDEN_DEL_DIA",
            "Hoy no tenés Orden del Día: es feriado o no hay Muestras para retirar en tu provincia.",
            404,
        )
    return orden


async def orden_del_dia(
    session: AsyncSession, usuario: Usuario, fecha: date | None = None
) -> OrdenDelDiaSalida:
    fecha = fecha or hoy()
    t = await _transportista(session, usuario)
    orden = await orden_de(session, usuario, fecha)
    provincia = await session.get(Provincia, t.provincia_id)
    assert provincia is not None
    filas = await session.execute(
        select(OrdenDelDiaParada, CentroExtraccion)
        .join(CentroExtraccion, CentroExtraccion.id == OrdenDelDiaParada.centro_id)
        .where(OrdenDelDiaParada.orden_id == orden.id)
        .order_by(OrdenDelDiaParada.posicion)
    )
    paradas = []
    for parada, centro in filas:
        listas = await session.scalar(
            select(func.count()).select_from(_muestras_listas_en(centro.id).subquery())
        )
        paradas.append(
            ParadaSalida(
                id=parada.id,
                posicion=parada.posicion,
                estado=parada.estado,
                centro=CentroSalida(
                    id=centro.id,
                    nombre=centro.nombre,
                    direccion=centro.direccion,
                    provincia=provincia.nombre,
                    latitud=centro.latitud,
                    longitud=centro.longitud,
                ),
                muestras_listas=int(listas or 0),
                recogido_at=parada.recogido_at,
            )
        )
    en_camino = await session.scalar(
        select(func.count())
        .select_from(Muestra)
        .join(OrdenDelDiaParada, OrdenDelDiaParada.id == Muestra.parada_id)
        .where(OrdenDelDiaParada.orden_id == orden.id, Muestra.estado == EstadoMuestra.EN_CAMINO_LAB_CENTRAL)
    )
    return OrdenDelDiaSalida(
        id=orden.id,
        fecha=orden.fecha,
        provincia=provincia.nombre,
        paradas=paradas,
        muestras_en_camino=int(en_camino or 0),
        llegada_lab_at=orden.llegada_lab_at,
    )


# --- E24 Recolectar Muestras ------------------------------------------------------------------


async def registrar_posicion(
    session: AsyncSession, usuario: Usuario, latitud: Decimal, longitud: Decimal
) -> None:
    await _transportista(session, usuario)
    session.add(PosicionTransportista(transportista_id=usuario.id, latitud=latitud, longitud=longitud))


async def recolectar(
    session: AsyncSession, usuario: Usuario, parada_id: int, fecha: date | None = None
) -> int:
    """Marca el Centro como recogido y pasa sus Muestras a En camino al Laboratorio Central.
    El recorrido es fijo (S8): las paradas se recolectan en el orden de la Orden del Día."""
    orden = await orden_de(session, usuario, fecha or hoy())
    parada = await session.get(OrdenDelDiaParada, parada_id, with_for_update=True)
    if parada is None or parada.orden_id != orden.id:
        raise NoEncontrado("parada", "la")
    if parada.estado == EstadoParada.RECOGIDO:
        raise Conflicto("PARADA_RECOGIDA", "Ese Centro ya está marcado como recogido.")
    siguiente = await session.scalar(
        select(func.min(OrdenDelDiaParada.posicion)).where(
            OrdenDelDiaParada.orden_id == orden.id, OrdenDelDiaParada.estado == EstadoParada.PENDIENTE
        )
    )
    if parada.posicion != siguiente:
        raise Conflicto(
            "PARADA_FUERA_DE_ORDEN", "El recorrido es fijo: recolectá los Centros en el orden indicado."
        )
    momento = ahora()
    parada.estado, parada.recogido_at = EstadoParada.RECOGIDO, momento
    muestras = list(await session.scalars(_muestras_listas_en(parada.centro_id).with_for_update()))
    for m in muestras:
        m.estado, m.parada_id, m.recolectada_at = EstadoMuestra.EN_CAMINO_LAB_CENTRAL, parada.id, momento
        estudio = await session.get(Estudio, m.estudio_id)
        assert estudio is not None
        await transicionar(
            session, estudio, EstadoEstudio.EN_CAMINO_LAB_CENTRAL, usuario, "Muestra recolectada"
        )
    centro = await session.get(CentroExtraccion, parada.centro_id)
    assert centro is not None
    session.add(
        PosicionTransportista(transportista_id=usuario.id, latitud=centro.latitud, longitud=centro.longitud)
    )
    return len(muestras)


# --- E19 Seguir Muestra en mapa ---------------------------------------------------------------


async def buscar_muestras(session: AsyncSession, texto: str) -> list[MuestraSalida]:
    """Búsqueda por Paciente (apellido, nombre o DNI) o por código de Estudio."""
    consulta = (
        select(Muestra, Estudio.codigo, Paciente, CentroExtraccion.nombre, Lote.codigo)
        .join(Estudio, Estudio.id == Muestra.estudio_id)
        .join(Paciente, Paciente.id == Estudio.paciente_id)
        .join(Turno, Turno.id == Muestra.turno_id)
        .join(CentroExtraccion, CentroExtraccion.id == Turno.centro_id)
        .outerjoin(Lote, Lote.id == Muestra.lote_id)
        .order_by(Muestra.tomada_at.desc())
        .limit(100)
    )
    texto = texto.strip()
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.where(
            or_(
                Paciente.apellido.ilike(patron),
                Paciente.nombre.ilike(patron),
                Paciente.dni.ilike(patron),
                Estudio.codigo.ilike(patron),
            )
        )
    return [
        MuestraSalida(
            id=m.id,
            estudio_id=m.estudio_id,
            estudio_codigo=codigo,
            paciente=p.nombre_completo,
            nro_extraccion=m.nro_extraccion,
            volumen_ml=m.volumen_ml,
            estado=m.estado,
            centro=centro,
            tomada_at=m.tomada_at,
            lote_codigo=lote,
        )
        for m, codigo, p, centro, lote in await session.execute(consulta)
    ]


async def ubicar_muestra(session: AsyncSession, muestra_id: int) -> UbicacionMuestra:
    """E19: dónde está la Muestra y qué Transportista la lleva."""
    muestra = await session.get(Muestra, muestra_id)
    if muestra is None:
        raise NoEncontrado("Muestra", "la")
    turno = await session.get(Turno, muestra.turno_id)
    assert turno is not None
    centro = await session.get(CentroExtraccion, turno.centro_id)
    assert centro is not None
    lab = lab_central()

    def salida(
        lat: Decimal, lon: Decimal, desc: str, transp: str | None = None, cuando: datetime | None = None
    ) -> UbicacionMuestra:
        return UbicacionMuestra(
            muestra_id=muestra.id,
            estado=muestra.estado,
            latitud=lat,
            longitud=lon,
            descripcion=desc,
            transportista=transp,
            actualizada_at=cuando,
        )

    match muestra.estado:
        case EstadoMuestra.LISTO_PARA_RETIRAR:
            return salida(
                centro.latitud,
                centro.longitud,
                f"Esperando al Transportista en {centro.nombre}",
                None,
                muestra.tomada_at,
            )
        case EstadoMuestra.EN_CAMINO_LAB_CENTRAL:
            parada = await session.get(OrdenDelDiaParada, muestra.parada_id)
            orden = await session.get(OrdenDelDia, parada.orden_id) if parada else None
            transportista = await session.get(Usuario, orden.transportista_id) if orden else None
            pos = (
                await session.scalar(
                    select(PosicionTransportista)
                    .where(PosicionTransportista.transportista_id == transportista.id)
                    .order_by(PosicionTransportista.registrada_at.desc(), PosicionTransportista.id.desc())
                    .limit(1)
                )
                if transportista
                else None
            )
            nombre = transportista.nombre_completo if transportista else None
            if pos is None:
                return salida(
                    centro.latitud,
                    centro.longitud,
                    "En camino al Laboratorio Central",
                    nombre,
                    muestra.recolectada_at,
                )
            return salida(
                pos.latitud, pos.longitud, "En camino al Laboratorio Central", nombre, pos.registrada_at
            )
        case EstadoMuestra.EN_VIAJE_COREA | EstadoMuestra.PROCESADA | EstadoMuestra.DESNATURALIZADA:
            return salida(COREA[0], COREA[1], "En Corea para la secuenciación", None, None)
        case _:
            return salida(
                lab.latitud, lab.longitud, "En el Laboratorio Central", None, muestra.llegada_lab_at
            )
