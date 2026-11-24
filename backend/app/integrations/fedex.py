"""Adaptador HTTP de la API de FedEx. Las credenciales sólo se usan desde acá y nunca se registran."""

import logging
from datetime import datetime
from typing import Any, get_args

import httpx

from app.config import Settings
from app.domain.errores import ErrorNegocio, NoEncontrado
from app.domain.reglas import TZ_AR
from app.integrations.ports import EstadoRetiroFedex, RetiroFedex

log = logging.getLogger("lisogen.integraciones")

TIMEOUT_SEG = 10


def _no_disponible() -> ErrorNegocio:
    return ErrorNegocio("FEDEX_NO_DISPONIBLE", "No pudimos comunicarnos con FedEx. Probá de nuevo.", 502)


class FedexHttp:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base = settings.fedex_api_url.rstrip("/")
        self._auth = httpx.BasicAuth(settings.fedex_usuario, settings.fedex_password)
        self._transport = transport

    async def _pedir(self, metodo: str, ruta: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_SEG) as cliente:
                return await cliente.request(metodo, f"{self._base}{ruta}", **kwargs)
        except httpx.HTTPError as e:
            log.warning("FedEx no respondió a %s %s: %s", metodo, ruta, type(e).__name__)
            raise _no_disponible() from e

    async def programar_retiro(self, *, fecha_hora: datetime, lugar: str) -> RetiroFedex:
        # La API pide hora argentina sin zona horaria: con offset responde 400.
        fecha = fecha_hora.astimezone(TZ_AR).strftime("%Y-%m-%dT%H:%M:%S")
        r = await self._pedir(
            "POST", "/retiros", json={"lugar": lugar, "fecha_programada": fecha}, auth=self._auth
        )
        if r.status_code == 400:
            log.warning("FedEx rechazó el retiro: %s", r.text[:200])
            raise ErrorNegocio("FEDEX_RECHAZO", "FedEx rechazó los datos del retiro.", 422)
        if r.status_code != 201:
            log.warning("FedEx respondió %s al programar un retiro", r.status_code)
            raise _no_disponible()
        try:
            retiro = r.json()["retiro"]
            id_retiro, url = str(retiro["id"]), str(retiro["url_seguimiento"])
        except (ValueError, KeyError, TypeError) as e:
            log.warning("FedEx devolvió una respuesta inesperada al programar un retiro")
            raise _no_disponible() from e
        if not url.startswith("https://"):  # se muestra como enlace en el front
            log.warning("FedEx devolvió una URL de seguimiento inesperada")
            raise _no_disponible()
        return RetiroFedex(id=id_retiro, url_seguimiento=url)

    async def consultar_retiro(self, *, retiro_id: str) -> EstadoRetiroFedex:
        r = await self._pedir("GET", f"/retiros/{retiro_id}")
        if r.status_code == 404:
            raise NoEncontrado("retiro de FedEx")
        if r.status_code != 200:
            log.warning("FedEx respondió %s al consultar un retiro", r.status_code)
            raise _no_disponible()
        try:
            estado = r.json()["estado"]
        except (ValueError, KeyError, TypeError) as e:
            log.warning("FedEx devolvió una respuesta inesperada al consultar un retiro")
            raise _no_disponible() from e
        if estado not in get_args(EstadoRetiroFedex):
            log.warning("FedEx devolvió un estado desconocido: %s", estado)
            raise _no_disponible()
        return estado
