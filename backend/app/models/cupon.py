from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import EstadoCupon
from app.models.base import Base, pg_enum


class Cupon(Base):
    __tablename__ = "cupon"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    qr_archivo_id: Mapped[int | None] = mapped_column(ForeignKey("archivo.id"))
    descuento_pct: Mapped[int] = mapped_column(SmallInteger)
    estado: Mapped[EstadoCupon] = mapped_column(
        pg_enum(EstadoCupon, "estado_cupon"), default=EstadoCupon.DISPONIBLE
    )
    generado_por: Mapped[int] = mapped_column(ForeignKey("profesional_medico.usuario_id"))
    medico_asignado_id: Mapped[int | None] = mapped_column(ForeignKey("profesional_medico.usuario_id"))
    paciente_asignado_id: Mapped[int | None] = mapped_column(ForeignKey("paciente.id"))
    vence_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    asignado_medico_at: Mapped[datetime | None]
    asignado_paciente_at: Mapped[datetime | None]
    usado_at: Mapped[datetime | None]
