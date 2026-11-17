"""Adaptador del Chatbot de GenLab (Supabase Edge Function, REST/JSON).

Autenticación: `apikey` (clave publishable, igual para todos los grupos) y `x-chatbot-token` (del grupo).
Sólo se llama desde el backend: el token no puede viajar al navegador. Siempre con timeout.

429: se espera lo que indica `Retry-After` (con tope) y se reintenta una sola vez. 503: el servicio está
apagado; se informa su `detail` y no se reintenta. Usa `requests` en un hilo."""

import asyncio
import time
from collections.abc import Callable
from typing import Any

import requests

from app.config import Settings
from app.integrations.ports import ErrorChatbot, RespuestaChat

TIMEOUT_SEG = 20
ESPERA_POR_DEFECTO_SEG = 5
ESPERA_MAXIMA_SEG = 10


class ChatbotApi:
    def __init__(self, settings: Settings) -> None:
        if not settings.chatbot_apikey or not settings.chatbot_token:
            raise RuntimeError("CHATBOT_MODO=api requiere CHATBOT_APIKEY y CHATBOT_TOKEN")
        self._url = settings.chatbot_url
        if not self._url.startswith("https://"):
            raise RuntimeError("CHATBOT_URL tiene que ser https:// (el token viaja en un encabezado)")
        self._cabeceras = {"apikey": settings.chatbot_apikey, "x-chatbot-token": settings.chatbot_token}
        self._dormir: Callable[[float], None] = time.sleep

    def _post(self, cuerpo: dict[str, Any]) -> requests.Response:
        try:
            return requests.post(self._url, headers=self._cabeceras, json=cuerpo, timeout=TIMEOUT_SEG)
        except requests.RequestException as e:
            raise ErrorChatbot(f"Chatbot sin respuesta ({type(e).__name__})") from e

    def _llamar(self, cuerpo: dict[str, Any]) -> Any:
        """POST bloqueante (corre en un hilo). Devuelve el JSON de la respuesta."""
        r = self._post(cuerpo)
        if r.status_code == 429:
            self._dormir(_espera(r))
            r = self._post(cuerpo)  # un solo reintento
        if r.status_code >= 400:
            raise ErrorChatbot(
                f"Chatbot HTTP {r.status_code}",
                status=r.status_code,
                detalle=_detalle(r),
                reintentar_en=_espera(r) if r.status_code == 429 else None,
            )
        try:
            return r.json()
        except ValueError as e:
            raise ErrorChatbot("Chatbot devolvió una respuesta que no es JSON") from e

    async def responder(self, *, pregunta: str, conversacion_id: str | None = None) -> RespuestaChat:
        datos = await asyncio.to_thread(
            self._llamar, {"mensaje": pregunta, "conversacion_id": conversacion_id}
        )
        texto = datos.get("respuesta") if isinstance(datos, dict) else None
        if not isinstance(texto, str) or not texto.strip():
            raise ErrorChatbot("Chatbot devolvió una respuesta sin texto")
        nuevo = datos.get("conversacion_id")
        tipo = datos.get("tipo")
        return RespuestaChat(
            respuesta=texto,
            conversacion_id=nuevo if isinstance(nuevo, str) else conversacion_id,
            tipo=tipo if isinstance(tipo, str) else "respuesta",
        )


def _espera(r: requests.Response) -> int:
    try:
        segundos = int(r.headers.get("Retry-After", ""))
    except ValueError:
        segundos = ESPERA_POR_DEFECTO_SEG
    return max(1, min(segundos, ESPERA_MAXIMA_SEG))


def _detalle(r: requests.Response) -> str:
    """`detail` del cuerpo de error cuando es un texto (en 422 es una lista y no se muestra)."""
    try:
        detalle = r.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    return detalle if isinstance(detalle, str) else ""
