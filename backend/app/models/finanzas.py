from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ConceptoMov, EstadoReaut, ModalidadPago, ResultadoOS
from app.models.base import Base, pg_enum


class Presupuesto(Base):
    __tablename__ = "presupuesto"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id"), unique=True)
    cantidad_genes: Mapped[int] = mapped_column(SmallInteger)
    monto_base_usd: Mapped[Decimal]
    modalidad: Mapped[ModalidadPago] = mapped_column(pg_enum(ModalidadPago, "modalidad_pago"))
    obra_social_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("obra_social.id"))
    cobertura_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal(0))
    cupon_id: Mapped[int | None] = mapped_column(ForeignKey("cupon.id"), unique=True)
    descuento_cupon_usd: Mapped[Decimal] = mapped_column(default=Decimal(0))
    monto_a_pagar_usd: Mapped[Decimal]
    emitido_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    emitido_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Pago(Base):
    """Pago simulado. `anulado_at` lo agrega la migración 0002 (DECISIONES D1)."""

    __tablename__ = "pago"
    id: Mapped[int] = mapped_column(primary_key=True)
    presupuesto_id: Mapped[int] = mapped_column(ForeignKey("presupuesto.id"))
    monto_usd: Mapped[Decimal]
    referencia_sim: Mapped[str]
    pagado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    anulado_at: Mapped[datetime | None]


class MovimientoFinanciero(Base):
    __tablename__ = "movimiento_financiero"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id"))
    concepto: Mapped[ConceptoMov] = mapped_column(pg_enum(ConceptoMov, "concepto_mov"))
    monto_usd: Mapped[Decimal]
    obra_social_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("obra_social.id"))
    pago_id: Mapped[int | None] = mapped_column(ForeignKey("pago.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AutorizacionObraSocial(Base):
    __tablename__ = "autorizacion_obra_social"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id"))
    obra_social_id: Mapped[int] = mapped_column(Integer, ForeignKey("obra_social.id"))
    resultado: Mapped[ResultadoOS] = mapped_column(pg_enum(ResultadoOS, "resultado_os"))
    motivo: Mapped[str | None]
    registrado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SolicitudReautorizacion(Base):
    __tablename__ = "solicitud_reautorizacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id"))
    rechazo_id: Mapped[int] = mapped_column(ForeignKey("autorizacion_obra_social.id"))
    decision_judicial: Mapped[int] = mapped_column(ForeignKey("archivo.id"))
    estado: Mapped[EstadoReaut] = mapped_column(
        pg_enum(EstadoReaut, "estado_reaut"), default=EstadoReaut.PENDIENTE
    )
    solicitado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resuelto_at: Mapped[datetime | None]
