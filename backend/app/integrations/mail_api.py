"""Adaptador de la API de Notificaciones por Email (Supabase, REST/JSON).

`POST /avisos` encola el correo (202) y responde «recibido», no «enviado»: el worker de la API lo
manda por Gmail en ~1 minuto. Hace falta `Idempotency-Key` en cada pedido: con la misma clave y el
mismo contenido un reintento no duplica el correo. Usa `requests` en un hilo."""

import asyncio
import uuid
from typing import Any

import requests

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

    def _llamar(
        self, metodo: str, ruta: str, *, clave: str | None = None, cuerpo: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        cabeceras = {"X-API-Key": self._key}
        if clave is not None:
            cabeceras["Idempotency-Key"] = clave
        try:
            r = requests.request(
                metodo, f"{self._base}{ruta}", headers=cabeceras, json=cuerpo, timeout=TIMEOUT_SEG
            )
            r.raise_for_status()
            datos = r.json() if r.content else {}  # 202: encolado · 200: repetido, no se duplica
            return datos if isinstance(datos, dict) else {}
        except requests.HTTPError as e:
            try:
                detalle = str(r.json().get("error", r.reason))
            except (ValueError, AttributeError):
                detalle = str(r.reason)
            raise ErrorMailApi(
                f"API de Notificaciones HTTP {r.status_code}: {detalle}",
                permanente=r.status_code in (400, 409, 413, 415),
            ) from e
        except (requests.RequestException, ValueError) as e:
            raise ErrorMailApi(f"API de Notificaciones sin respuesta ({type(e).__name__})") from e

    async def enviar(
        self, *, destinatario: str, asunto: str, cuerpo: str, clave: str | None = None
    ) -> str | None:
        """Pide el envío (`POST /avisos`). Devuelve el id del aviso, que sirve para consultar su estado
        con `estado()`; `None` si el destinatario es de demo (va a Mailpit, no a la API)."""
        # Los usuarios demo (@lisogen-demo.com.ar) no tienen casilla real: van a Mailpit, no a la cola
        # compartida ni a la cuota diaria de Gmail.
        if self._demo is not None and destinatario.lower().endswith(self._sufijo_demo):
            await self._demo.enviar(destinatario=destinatario, asunto=asunto, cuerpo=cuerpo)
            return None
        clave = (clave or f"lisogen-{uuid.uuid4().hex}")[:MAX_CLAVE]
        datos = {
            "asunto": asunto[:MAX_ASUNTO],
            "mensaje": cuerpo[:MAX_MENSAJE],
            "referencia": clave,
            "destinatarios": [{"canal": "email", "destino": destinatario}],
        }
        r = await asyncio.to_thread(self._llamar, "POST", "/avisos", clave=clave, cuerpo=datos)
        aviso_id = r.get("id")
        return aviso_id if isinstance(aviso_id, str) else None

    async def estado(self, aviso_id: str) -> dict[str, Any]:
        """Estado de un aviso (`GET /avisos/{id}`): `estado` general y el detalle de cada envío en `envios`.
        La API procesa la cola cada minuto: conviene consultar a lo sumo una vez por minuto."""
        aviso_id = str(uuid.UUID(aviso_id))  # la API responde 400 si el id no es un UUID
        return await asyncio.to_thread(self._llamar, "GET", f"/avisos/{aviso_id}")

    async def pendientes(self, limite: int = 25) -> list[dict[str, Any]]:
        """Avisos con envíos sin terminar (GET /avisos/pendientes), del más viejo al más nuevo."""
        limite = max(1, min(limite, 100))
        r = await asyncio.to_thread(self._llamar, "GET", f"/avisos/pendientes?limite={limite}")
        avisos = r.get("avisos", [])
        return avisos if isinstance(avisos, list) else []
