from datetime import datetime

from sqlalchemy import ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Patologia(Base):
    __tablename__ = "patologia"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(unique=True)
    sintoma_cardinal_id: Mapped[int] = mapped_column(ForeignKey("snomed_concepto.concept_id"))
    es_pompe: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    secundarios: Mapped[list["PatologiaSintomaSecundario"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class PatologiaSintomaSecundario(Base):
    __tablename__ = "patologia_sintoma_secundario"
    patologia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patologia.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[int] = mapped_column(ForeignKey("snomed_concepto.concept_id"), primary_key=True)


class PatologiaGen(Base):
    __tablename__ = "patologia_gen"
    patologia_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("patologia.id", ondelete="CASCADE"), primary_key=True
    )
    gen_id: Mapped[int] = mapped_column(Integer, ForeignKey("gen.id"), primary_key=True)
