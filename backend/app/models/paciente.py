from datetime import date, datetime
from typing import Any

from sqlalchemy import FetchedValue, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import LadoFamiliar, Parentesco, TipoSospecha
from app.models.base import Base, pg_enum


class Paciente(Base):
    __tablename__ = "paciente"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), unique=True)
    dni: Mapped[str] = mapped_column(unique=True)
    nombre: Mapped[str]
    apellido: Mapped[str]
    fecha_nacimiento: Mapped[date]
    telefono: Mapped[str]
    email_contacto: Mapped[str] = mapped_column(CITEXT)
    es_menor_al_alta: Mapped[bool]
    obra_social_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("obra_social.id"))
    nro_afiliado: Mapped[str | None]
    resumen_historia_clinica: Mapped[str]
    familiograma_archivo_id: Mapped[int | None] = mapped_column(ForeignKey("archivo.id"))
    # Número de familia (FAM-000123): agrupa Pacientes para el historial familiar (migración 0006)
    familia_codigo: Mapped[str] = mapped_column(server_default=FetchedValue())  # DEFAULT con familia_seq
    # Avisos del último Familiograma generado: [{codigo, mensaje}] (migración 0004)
    familiograma_advertencias: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    medico_alta_id: Mapped[int] = mapped_column(ForeignKey("profesional_medico.usuario_id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # Trae familia_codigo (lo genera la base) en el mismo INSERT ... RETURNING
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}"


class PacienteSintoma(Base):
    __tablename__ = "paciente_sintoma"
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id", ondelete="CASCADE"), primary_key=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("snomed_concepto.concept_id"), primary_key=True)


class DiagnosticoPresuntivo(Base):
    __tablename__ = "diagnostico_presuntivo"
    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id", ondelete="CASCADE"))
    patologia_id: Mapped[int] = mapped_column(Integer, ForeignKey("patologia.id"))
    tipo_sospecha: Mapped[TipoSospecha] = mapped_column(pg_enum(TipoSospecha, "tipo_sospecha"))
    medico_id: Mapped[int] = mapped_column(ForeignKey("profesional_medico.usuario_id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Familiar(Base):
    __tablename__ = "familiar"
    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id", ondelete="CASCADE"))
    parentesco: Mapped[Parentesco] = mapped_column(pg_enum(Parentesco, "parentesco"))
    nombre: Mapped[str]
    # Migración 0004: la API de familiograma exige apellido y el lado de abuelos, tíos y primos.
    # Son nullable porque los familiares cargados antes no los tienen.
    apellido: Mapped[str | None]
    lado: Mapped[LadoFamiliar | None] = mapped_column(pg_enum(LadoFamiliar, "lado_familiar"))
    sintomas: Mapped[str | None]
    patologia_diagnosticada: Mapped[int | None] = mapped_column(Integer, ForeignKey("patologia.id"))
