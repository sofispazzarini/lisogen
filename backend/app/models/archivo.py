from datetime import datetime

from sqlalchemy import CHAR, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import TipoArchivo
from app.models.base import Base, pg_enum


class Archivo(Base):
    """Metadatos de un archivo en MinIO. `storage_key` nunca se expone: se entregan URLs firmadas."""

    __tablename__ = "archivo"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoArchivo] = mapped_column(pg_enum(TipoArchivo, "tipo_archivo"))
    nombre: Mapped[str]
    mime: Mapped[str]
    tamano_bytes: Mapped[int]
    storage_key: Mapped[str] = mapped_column(unique=True)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    subido_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
