from datetime import date, datetime

from sqlalchemy import ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import Parentesco, TipoSospecha
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
    medico_alta_id: Mapped[int] = mapped_column(ForeignKey("profesional_medico.usuario_id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

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
    sintomas: Mapped[str | None]
    patologia_diagnosticada: Mapped[int | None] = mapped_column(Integer, ForeignKey("patologia.id"))
