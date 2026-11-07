"""Adaptador de la API de Notificaciones por Email (Supabase, REST/JSON).

`POST /avisos` encola el correo (202) y responde «recibido», no «enviado»: el worker de la API lo
manda por Gmail en ~1 minuto. Hace falta `Idempotency-Key` en cada pedido: con la misma clave y el
mismo contenido un reintento no duplica el correo. Sin dependencias nuevas: `urllib` en un hilo."""

import asyncio
import json
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings
from app.integrations.infra import MailSmtp

TIMEOUT_SEG = 15
MAX_ASUNTO, MAX_MENSAJE, MAX_CLAVE = 200, 10_000, 200


class ErrorMailApi(Exception):
    """`permanente`: la API rechazó el pedido por sus datos (400/409/413/415); reintentar no sirve."""

    def __init__(self, mensaje: str, *, permanente: bool = False) -> None:
        super().__init__(mensaje)
        self.permanente = permanente


class MailApi:
    def __init__(self, settings: Settings, demo: MailSmtp | None = None) -> None:
        if not (settings.mail_api_url and settings.mail_api_key):
            raise RuntimeError("MAIL_MODO=api requiere MAIL_API_URL y MAIL_API_KEY")
        self._base = settings.mail_api_url.rstrip("/")
        if not self._base.startswith("https://"):
            raise RuntimeError("MAIL_API_URL tiene que ser https:// (la API Key viaja en un encabezado)")
        self._key = settings.mail_api_key
        self._sufijo_demo = f"@{settings.mail_dominio_demo.lower()}"
        self._demo = demo

    def _post(self, clave: str, cuerpo: dict[str, Any]) -> None:
        pedido = Request(  # noqa: S310 (https verificado en el constructor)
            f"{self._base}/avisos",
            data=json.dumps(cuerpo).encode(),
            headers={"X-API-Key": self._key, "Idempotency-Key": clave, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(pedido, timeout=TIMEOUT_SEG):  # noqa: S310
                return  # 202: encolado · 200: pedido repetido, no se duplica
        except HTTPError as e:
            try:
                detalle = str(json.loads(e.read()).get("error", e.reason))
            except (ValueError, AttributeError):
                detalle = str(e.reason)
            raise ErrorMailApi(
                f"API de Notificaciones HTTP {e.code}: {detalle}", permanente=e.code in (400, 409, 413, 415)
            ) from e
        except (URLError, TimeoutError) as e:
            raise ErrorMailApi(f"API de Notificaciones sin respuesta ({type(e).__name__})") from e

    async def enviar(
        self, *, destinatario: str, asunto: str, cuerpo: str, clave: str | None = None
    ) -> None:
        # Los usuarios demo (@lisogen-demo.com.ar) no tienen casilla real: van a Mailpit, no a la cola
        # compartida ni a la cuota diaria de Gmail.
        if self._demo is not None and destinatario.lower().endswith(self._sufijo_demo):
            await self._demo.enviar(destinatario=destinatario, asunto=asunto, cuerpo=cuerpo)
            return
        clave = (clave or f"lisogen-{uuid.uuid4().hex}")[:MAX_CLAVE]
        datos = {
            "asunto": asunto[:MAX_ASUNTO],
            "mensaje": cuerpo[:MAX_MENSAJE],
            "referencia": clave,
            "destinatarios": [{"canal": "email", "destino": destinatario}],
        }
        await asyncio.to_thread(self._post, clave, datos)
        