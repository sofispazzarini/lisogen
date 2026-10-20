from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import EstadoTurno
from app.models.base import Base, pg_enum


class CentroExtraccion(Base):
    __tablename__ = "centro_extraccion"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str]
    direccion: Mapped[str]
    provincia_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("provincia.id"))
    latitud: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitud: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    activo: Mapped[bool] = mapped_column(default=True)


class Turno(Base):
    __tablename__ = "turno"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id"))
    centro_id: Mapped[int] = mapped_column(Integer, ForeignKey("centro_extraccion.id"))
    inicio: Mapped[datetime]
    estado: Mapped[EstadoTurno] = mapped_column(
        pg_enum(EstadoTurno, "estado_turno"), default=EstadoTurno.RESERVADO
    )
    orden_archivo_id: Mapped[int | None] = mapped_column(ForeignKey("archivo.id"))
    consentimiento_id: Mapped[int | None] = mapped_column(ForeignKey("archivo.id"))
    recordatorio_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    cancelado_at: Mapped[datetime | None]
