from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, SmallInteger, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import CanalNotif, ServicioExterno
from app.models.base import Base, pg_enum


class Notificacion(Base):
    """Aviso al usuario. Canal APP = bandeja de Avisos; canal MAIL = bandeja de salida (enviada_at)."""

    __tablename__ = "notificacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    estudio_id: Mapped[int | None] = mapped_column(ForeignKey("estudio.id"))
    canal: Mapped[CanalNotif] = mapped_column(pg_enum(CanalNotif, "canal_notif"))
    asunto: Mapped[str]
    cuerpo: Mapped[str]
    leida_at: Mapped[datetime | None]
    enviada_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ChatbotMensaje(Base):
    __tablename__ = "chatbot_mensaje"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id", ondelete="CASCADE"))
    pregunta: Mapped[str]
    respuesta: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IntegracionLog(Base):
    __tablename__ = "integracion_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    servicio: Mapped[ServicioExterno] = mapped_column(pg_enum(ServicioExterno, "servicio_externo"))
    operacion: Mapped[str]
    estudio_id: Mapped[int | None] = mapped_column(ForeignKey("estudio.id"))
    request: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    ok: Mapped[bool]
    duracion_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AuditoriaAcceso(Base):
    __tablename__ = "auditoria_acceso"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    accion: Mapped[str]
    entidad: Mapped[str]
    entidad_id: Mapped[int]
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
