from datetime import date

from sqlalchemy import ForeignKey, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Provincia(Base):
    __tablename__ = "provincia"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(unique=True)


class Especialidad(Base):
    __tablename__ = "especialidad"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(unique=True)


class ObraSocial(Base):
    __tablename__ = "obra_social"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(unique=True)
    codigo_externo: Mapped[str | None] = mapped_column(unique=True)


class SnomedConcepto(Base):
    __tablename__ = "snomed_concepto"
    concept_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    termino: Mapped[str]


class Gen(Base):
    __tablename__ = "gen"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    simbolo: Mapped[str] = mapped_column(unique=True)


class Variante(Base):
    __tablename__ = "variante"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gen_id: Mapped[int] = mapped_column(Integer, ForeignKey("gen.id"))
    nomenclatura: Mapped[str]
    id_externo: Mapped[str | None]


class Feriado(Base):
    __tablename__ = "feriado"
    fecha: Mapped[date] = mapped_column(primary_key=True)
    descripcion: Mapped[str]
