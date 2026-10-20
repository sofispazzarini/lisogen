"""Utilidades compartidas por los casos de uso."""

import hashlib
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CanalNotif, TipoArchivo
from app.domain.errores import NoEncontrado
from app.integrations.registro import Integraciones
from app.models import Archivo, AuditoriaAcceso, Base, Feriado, Notificacion


def ahora() -> datetime:
    """Reloj del sistema (los tests lo reemplazan con monkeypatch)."""
    return datetime.now(UTC)


async def obtener[M: Base](
    session: AsyncSession, modelo: type[M], id_: int, entidad: str, articulo: Literal["el", "la"] = "el"
) -> M:
    obj = await session.get(modelo, id_)
    if obj is None:
        raise NoEncontrado(entidad, articulo)
    return obj


async def siguiente_codigo(session: AsyncSession, secuencia: str, prefijo: str) -> tuple[int, str]:
    """Reserva el próximo id de la secuencia y arma el código legible (EST-2026-000123)."""
    nuevo_id = int((await session.execute(text(f"SELECT nextval('{secuencia}')"))).scalar_one())
    return nuevo_id, f"{prefijo}-{ahora().year}-{nuevo_id:06d}"


async def feriados(session: AsyncSession, desde: date, hasta: date) -> set[date]:
    filas = await session.scalars(select(Feriado.fecha).where(Feriado.fecha.between(desde, hasta)))
    return set(filas)


async def guardar_archivo(
    session: AsyncSession,
    ints: Integraciones,
    *,
    tipo: TipoArchivo,
    nombre: str,
    mime: str,
    contenido: bytes,
    subido_por: int | None,
) -> Archivo:
    clave = f"{tipo.value.lower()}/{uuid.uuid4()}"
    await ints.storage.guardar(clave=clave, contenido=contenido, mime=mime)
    archivo = Archivo(
        tipo=tipo,
        nombre=nombre,
        mime=mime,
        tamano_bytes=len(contenido),
        storage_key=clave,
        sha256=hashlib.sha256(contenido).hexdigest(),
        subido_por=subido_por,
    )
    session.add(archivo)
    await session.flush()
    return archivo


async def url_archivo(session: AsyncSession, ints: Integraciones, archivo_id: int | None) -> str | None:
    if archivo_id is None:
        return None
    archivo = await obtener(session, Archivo, archivo_id, "archivo")
    return await ints.storage.url_firmada(clave=archivo.storage_key, nombre_descarga=archivo.nombre)


def auditar(
    session: AsyncSession, usuario_id: int | None, accion: str, entidad: str, entidad_id: int, ip: str | None
) -> None:
    """Ley 25.326: cada lectura de Resultado o ficha clínica queda registrada."""
    session.add(
        AuditoriaAcceso(usuario_id=usuario_id, accion=accion, entidad=entidad, entidad_id=entidad_id, ip=ip)
    )


def notificar(
    session: AsyncSession, usuario_id: int, asunto: str, cuerpo: str, estudio_id: int | None = None
) -> None:
    """Aviso en la bandeja (APP) + mail en la bandeja de salida (lo despacha el job de mails)."""
    for canal in (CanalNotif.APP, CanalNotif.MAIL):
        session.add(
            Notificacion(
                usuario_id=usuario_id, estudio_id=estudio_id, canal=canal, asunto=asunto, cuerpo=cuerpo
            )
        )
