from datetime import datetime

from sqlalchemy import ForeignKey, Integer, SmallInteger, func
from sqlalchemy.dialects.postgresql import CITEXT, INET
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import RolUsuario
from app.models.base import Base, pg_enum


class Usuario(Base):
    __tablename__ = "usuario"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str]
    rol: Mapped[RolUsuario] = mapped_column(pg_enum(RolUsuario, "rol_usuario"))
    nombre: Mapped[str]
    apellido: Mapped[str]
    telefono: Mapped[str]
    debe_cambiar_password: Mapped[bool] = mapped_column(default=False)
    activo: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}"


class ProfesionalMedico(Base):
    """Datos profesionales compartidos por Médico Tratante y Gerente Médico (E29)."""

    __tablename__ = "profesional_medico"
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True)
    matricula: Mapped[str] = mapped_column(unique=True)


class ProfesionalEspecialidad(Base):
    __tablename__ = "profesional_especialidad"
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("profesional_medico.usuario_id", ondelete="CASCADE"), primary_key=True
    )
    especialidad_id: Mapped[int] = mapped_column(Integer, ForeignKey("especialidad.id"), primary_key=True)


class Transportista(Base):
    __tablename__ = "transportista"
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True)
    provincia_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("provincia.id"), unique=True)


class DispositivoConfiable(Base):
    __tablename__ = "dispositivo_confiable"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    huella: Mapped[str]
    ultima_ip: Mapped[str | None] = mapped_column(INET)
    ultimo_uso: Mapped[datetime] = mapped_column(server_default=func.now())


class CodigoVerificacion(Base):
    __tablename__ = "codigo_verificacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    codigo_hash: Mapped[str]
    expira_at: Mapped[datetime]
    usado_at: Mapped[datetime | None]
    intentos: Mapped[int] = mapped_column(SmallInteger, default=0)
