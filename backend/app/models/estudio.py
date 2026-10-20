from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, SmallInteger, event, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.base import NO_VALUE

from app.domain.enums import EstadoEstudio, OrigenGen, TipoEstudio
from app.models.base import Base, pg_enum

_transicion_en_curso: ContextVar[bool] = ContextVar("_transicion_en_curso", default=False)


@contextmanager
def permitir_cambio_de_estado() -> Iterator[None]:
    """Sólo `services.transiciones.transicionar` abre este contexto."""
    token = _transicion_en_curso.set(True)
    try:
        yield
    finally:
        _transicion_en_curso.reset(token)


class Estudio(Base):
    __tablename__ = "estudio"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(unique=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"))
    medico_tratante_id: Mapped[int] = mapped_column(ForeignKey("profesional_medico.usuario_id"))
    tipo: Mapped[TipoEstudio] = mapped_column(pg_enum(TipoEstudio, "tipo_estudio"), default=TipoEstudio.EXOMA)
    estudio_origen_id: Mapped[int | None] = mapped_column(ForeignKey("estudio.id"))
    estado: Mapped[EstadoEstudio] = mapped_column(
        pg_enum(EstadoEstudio, "estado_estudio"), default=EstadoEstudio.CREADO
    )
    evalua_hallazgos_secundarios: Mapped[bool] = mapped_column(default=False)
    urgente: Mapped[bool] = mapped_column(default=False)
    inasistencias: Mapped[int] = mapped_column(SmallInteger, default=0)
    bioinformatico_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    tomado_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finalizado_at: Mapped[datetime | None]

    # Lock optimista (E27): todo UPDATE del Estudio exige `WHERE version = <leída>` y la incrementa.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


@event.listens_for(Estudio.estado, "set", propagate=True)
def _sólo_transicionar_cambia_el_estado(
    target: Estudio, value: EstadoEstudio, oldvalue: Any, initiator: Any
) -> None:
    if value == EstadoEstudio.CREADO and oldvalue in (None, NO_VALUE):
        return  # alta del Estudio
    if not _transicion_en_curso.get():
        raise RuntimeError("estudio.estado sólo se modifica con services.transiciones.transicionar")


class EstudioPatologia(Base):
    __tablename__ = "estudio_patologia"
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id", ondelete="CASCADE"), primary_key=True)
    patologia_id: Mapped[int] = mapped_column(Integer, ForeignKey("patologia.id"), primary_key=True)


class EstudioGen(Base):
    __tablename__ = "estudio_gen"
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id", ondelete="CASCADE"), primary_key=True)
    gen_id: Mapped[int] = mapped_column(Integer, ForeignKey("gen.id"), primary_key=True)
    origen: Mapped[OrigenGen] = mapped_column(pg_enum(OrigenGen, "origen_gen"))
    patologia_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("patologia.id"))


class EstudioEstadoHistorial(Base):
    __tablename__ = "estudio_estado_historial"
    id: Mapped[int] = mapped_column(primary_key=True)
    estudio_id: Mapped[int] = mapped_column(ForeignKey("estudio.id", ondelete="CASCADE"))
    estado_anterior: Mapped[EstadoEstudio | None] = mapped_column(pg_enum(EstadoEstudio, "estado_estudio"))
    estado_nuevo: Mapped[EstadoEstudio] = mapped_column(pg_enum(EstadoEstudio, "estado_estudio"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    motivo: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
