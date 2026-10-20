from datetime import datetime

from sqlalchemy import ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import ClasifVariante, TipoResultado
from app.models.base import Base, pg_enum


class DatosCrudos(Base):
    __tablename__ = "datos_crudos"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id"), unique=True)
    muestra_id: Mapped[int] = mapped_column(ForeignKey("muestra.id"))
    archivo_id: Mapped[int] = mapped_column(ForeignKey("archivo.id"))
    cargado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Resultado(Base):
    __tablename__ = "resultado"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id"), unique=True)
    tipo: Mapped[TipoResultado] = mapped_column(pg_enum(TipoResultado, "tipo_resultado"))
    pdf_id: Mapped[int | None] = mapped_column(ForeignKey("archivo.id"))
    confirmado_por: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    confirmado_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ResultadoVariante(Base):
    __tablename__ = "resultado_variante"
    resultado_id: Mapped[int] = mapped_column(
        ForeignKey("resultado.id", ondelete="CASCADE"), primary_key=True
    )
    variante_id: Mapped[int] = mapped_column(Integer, ForeignKey("variante.id"), primary_key=True)
    clasificacion: Mapped[ClasifVariante] = mapped_column(pg_enum(ClasifVariante, "clasif_variante"))
    hallazgo_secundario: Mapped[bool] = mapped_column(default=False)
