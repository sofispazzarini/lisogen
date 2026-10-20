"""Adaptadores de infraestructura: mail (SMTP → Mailpit) y archivos (MinIO privado)."""

import asyncio
import io
from dataclasses import dataclass, field
from datetime import timedelta
from email.message import EmailMessage
from urllib.parse import quote

import aiosmtplib
from minio import Minio

from app.config import Settings


@dataclass
class MailEnviado:
    destinatario: str
    asunto: str
    cuerpo: str


class MailSmtp:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def enviar(self, *, destinatario: str, asunto: str, cuerpo: str) -> None:
        msg = EmailMessage()
        msg["From"] = self._s.mail_remitente
        msg["To"] = destinatario
        msg["Subject"] = asunto
        msg.set_content(cuerpo)
        await aiosmtplib.send(msg, hostname=self._s.smtp_host, port=self._s.smtp_port, timeout=10)


@dataclass
class MailMemoria:
    enviados: list[MailEnviado] = field(default_factory=list)

    async def enviar(self, *, destinatario: str, asunto: str, cuerpo: str) -> None:
        self.enviados.append(MailEnviado(destinatario, asunto, cuerpo))


class StorageMinio:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._cliente = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            region="us-east-1",
        )
        # Las URLs firmadas se calculan contra el host que ve el navegador (la firma incluye el host).
        self._publico = Minio(
            settings.minio_public_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            region="us-east-1",
        )
        self._bucket_listo = False

    async def _asegurar_bucket(self) -> None:
        if self._bucket_listo:
            return
        existe = await asyncio.to_thread(self._cliente.bucket_exists, self._s.minio_bucket)
        if not existe:
            await asyncio.to_thread(self._cliente.make_bucket, self._s.minio_bucket)
        self._bucket_listo = True

    async def guardar(self, *, clave: str, contenido: bytes, mime: str) -> None:
        await self._asegurar_bucket()
        await asyncio.to_thread(
            self._cliente.put_object,
            self._s.minio_bucket,
            clave,
            io.BytesIO(contenido),
            len(contenido),
            content_type=mime,
        )

    async def leer(self, *, clave: str) -> bytes:
        def _leer() -> bytes:
            r = self._cliente.get_object(self._s.minio_bucket, clave)
            try:
                return r.read()
            finally:
                r.close()
                r.release_conn()

        return await asyncio.to_thread(_leer)

    async def url_firmada(self, *, clave: str, nombre_descarga: str) -> str:
        return await asyncio.to_thread(
            self._publico.presigned_get_object,
            self._s.minio_bucket,
            clave,
            expires=timedelta(seconds=self._s.url_firmada_segundos),
            response_headers={
                "response-content-disposition": f"attachment; filename*=UTF-8''{quote(nombre_descarga)}"
            },
        )


@dataclass
class StorageMemoria:
    objetos: dict[str, tuple[bytes, str]] = field(default_factory=dict)

    async def guardar(self, *, clave: str, contenido: bytes, mime: str) -> None:
        self.objetos[clave] = (contenido, mime)

    async def leer(self, *, clave: str) -> bytes:
        return self.objetos[clave][0]

    async def url_firmada(self, *, clave: str, nombre_descarga: str) -> str:
        return f"memoria://{clave}?firma=test&nombre={quote(nombre_descarga)}"
