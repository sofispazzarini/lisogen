from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import EstadoLote, EstadoMuestra, EstadoParada, MotivoReextraccion
from app.models.base import Base, pg_enum


class OrdenDelDia(Base):
    __tablename__ = "orden_del_dia"
    id: Mapped[int] = mapped_column(primary_key=True)
    transportista_id: Mapped[int] = mapped_column(ForeignKey("transportista.usuario_id"))
    fecha: Mapped[date]
    generada_at: Mapped[datetime] = mapped_column(server_default=func.now())
    llegada_lab_at: Mapped[datetime | None]


class OrdenDelDiaParada(Base):
    __tablename__ = "orden_del_dia_parada"
    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("orden_del_dia.id", ondelete="CASCADE"))
    centro_id: Mapped[int] = mapped_column(Integer, ForeignKey("centro_extraccion.id"))
    posicion: Mapped[int] = mapped_column(SmallInteger)
    estado: Mapped[EstadoParada] = mapped_column(
        pg_enum(EstadoParada, "estado_parada"), default=EstadoParada.PENDIENTE
    )
    recogido_at: Mapped[datetime | None]


class Lote(Base):
    __tablename__ = "lote"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    estado: Mapped[EstadoLote] = mapped_column(
        pg_enum(EstadoLote, "estado_lote"), default=EstadoLote.EN_FORMACION
    )
    incluye_urgente: Mapped[bool] = mapped_column(default=False)
    csv_ministerio_id: Mapped[int | None] = mapped_column(ForeignKey("archivo.id"))
    autorizacion_ministerio_id: Mapped[int | None] = mapped_column(ForeignKey("archivo.id"))
    sellado_at: Mapped[datetime | None]
    retiro_programado_at: Mapped[datetime | None]
    fedex_url: Mapped[str | None]
    fedex_confirmado_at: Mapped[datetime | None]
    recibido_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Muestra(Base):
    __tablename__ = "muestra"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id"))
    turno_id: Mapped[int] = mapped_column(ForeignKey("turno.id"), unique=True)
    nro_extraccion: Mapped[int] = mapped_column(SmallInteger, default=1)
    volumen_ml: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    estado: Mapped[EstadoMuestra] = mapped_column(
        pg_enum(EstadoMuestra, "estado_muestra"), default=EstadoMuestra.LISTO_PARA_RETIRAR
    )
    tomada_at: Mapped[datetime] = mapped_column(server_default=func.now())
    parada_id: Mapped[int | None] = mapped_column(ForeignKey("orden_del_dia_parada.id"))
    recolectada_at: Mapped[datetime | None]
    llegada_lab_at: Mapped[datetime | None]
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lote.id"))


class PosicionTransportista(Base):
    __tablename__ = "posicion_transportista"
    id: Mapped[int] = mapped_column(primary_key=True)
    transportista_id: Mapped[int] = mapped_column(ForeignKey("transportista.usuario_id"))
    latitud: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitud: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    registrada_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SolicitudReextraccion(Base):
    __tablename__ = "solicitud_reextraccion"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id"))
    muestra_id: Mapped[int] = mapped_column(ForeignKey("muestra.id"))
    motivo: Mapped[MotivoReextraccion] = mapped_column(pg_enum(MotivoReextraccion, "motivo_reextraccion"))
    solicitado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
