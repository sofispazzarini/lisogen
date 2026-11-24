"""Adaptador de la API de familiograma del Laboratorio (Supabase, REST/JSON).

- `POST {base}` con `{"personas": [...], "opciones": {...}}` → `{"advertencias": [...], "imagen":
  {"tipo": "image/svg+xml", "base64": "..."}}`. El payload lo arma sólo `familiograma_mapeo`.
- `GET {base}/parentescos` → catálogo de 16 `{id, parentesco}` (se cachea en memoria).
- Clave en `x-api-key` (variable `FAMILIOGRAMA_API_KEY`); se usa sólo desde el backend y nunca se
  escribe en logs ni en mensajes de error.
- 500/502 se reintentan una sola vez con un backoff corto; los 4xx y los timeouts no se reintentan.

Usa `requests` en un hilo, como el resto de los adaptadores."""

import asyncio
import base64
import binascii
from typing import Any, Final

import requests

from app.config import Settings
from app.integrations import familiograma_mapeo as mapeo
from app.integrations.ports import (
    Advertencia,
    DetalleError,
    ErrorFamiliograma,
    Familiograma,
    ParentescoCatalogo,
    PersonaFamiliograma,
    ReglaSospecha,
)
from app.integrations.svg import SvgInvalido, sanear

TIMEOUT_SEG: Final = 15
REINTENTABLES: Final = frozenset({500, 502})
BACKOFF_SEG: Final = 0.5
MIME_SVG: Final = "image/svg+xml"


class FamiliogramaApi:
    def __init__(self, settings: Settings) -> None:
        if not settings.familiograma_api_key:
            raise RuntimeError("FAMILIOGRAMA_MODO=api requiere FAMILIOGRAMA_API_KEY")
        self._base = settings.familiograma_api_url.rstrip("/")
        if not self._base.startswith("https://"):
            raise RuntimeError(
                "FAMILIOGRAMA_API_URL tiene que ser https:// (la clave viaja en un encabezado)"
            )
        self._key = settings.familiograma_api_key
        self._catalogo: list[ParentescoCatalogo] | None = None
        self.backoff_seg = BACKOFF_SEG

    # --- HTTP (bloqueante, corre en un hilo) ---------------------------------------------------

    def _pedir(self, metodo: str, ruta: str, cuerpo: bytes | None = None) -> requests.Response:
        cabeceras = {"x-api-key": self._key}
        if cuerpo is not None:
            cabeceras["Content-Type"] = "application/json"
        try:
            return requests.request(
                metodo, f"{self._base}{ruta}", headers=cabeceras, data=cuerpo, timeout=TIMEOUT_SEG
            )
        except requests.Timeout as e:
            raise ErrorFamiliograma("API de familiograma sin respuesta (timeout)") from e
        except requests.RequestException as e:
            raise ErrorFamiliograma(f"API de familiograma sin respuesta ({type(e).__name__})") from e

    async def _llamar(self, metodo: str, ruta: str, cuerpo: bytes | None = None) -> Any:
        r = await asyncio.to_thread(self._pedir, metodo, ruta, cuerpo)
        if r.status_code in REINTENTABLES:
            await asyncio.sleep(self.backoff_seg)
            r = await asyncio.to_thread(self._pedir, metodo, ruta, cuerpo)
        if r.status_code >= 400:
            raise _error(r)
        try:
            return r.json()
        except ValueError as e:
            raise ErrorFamiliograma("API de familiograma devolvió una respuesta que no es JSON") from e

    # --- Puerto --------------------------------------------------------------------------------

    async def generar(
        self, *, personas: list[PersonaFamiliograma], regla_sospecha: ReglaSospecha = "desactivada"
    ) -> Familiograma:
        cuerpo = mapeo.serializar(mapeo.a_payload(personas, regla_sospecha))
        datos = await self._llamar("POST", "", cuerpo)
        return _imagen(datos)

    async def parentescos(self) -> list[ParentescoCatalogo]:
        if self._catalogo is None:
            datos = await self._llamar("GET", "/parentescos")
            if not isinstance(datos, list):
                raise ErrorFamiliograma("API de familiograma devolvió un catálogo que no se entiende")
            self._catalogo = [
                ParentescoCatalogo(int(f["id"]), str(f["parentesco"]))
                for f in datos
                if isinstance(f, dict) and "id" in f and "parentesco" in f
            ]
        return list(self._catalogo)


def _imagen(datos: Any) -> Familiograma:
    imagen = datos.get("imagen") if isinstance(datos, dict) else None
    if (
        not isinstance(imagen, dict)
        or imagen.get("tipo") != MIME_SVG
        or not isinstance(imagen.get("base64"), str)
    ):
        raise ErrorFamiliograma("API de familiograma devolvió una imagen que no se entiende")
    try:
        svg = base64.b64decode(imagen["base64"], validate=True)
    except (binascii.Error, ValueError) as e:
        raise ErrorFamiliograma("API de familiograma devolvió un base64 inválido") from e
    try:
        svg = sanear(svg)
    except SvgInvalido as e:
        raise ErrorFamiliograma(f"API de familiograma devolvió un SVG inválido ({e})") from e
    advertencias = tuple(
        Advertencia(str(a.get("codigo") or ""), str(a.get("mensaje") or ""))
        for a in (datos.get("advertencias") or [])
        if isinstance(a, dict)
    )
    return Familiograma(contenido=svg, mime=MIME_SVG, advertencias=advertencias)


def _error(r: requests.Response) -> ErrorFamiliograma:
    """Traduce `{"error": {codigo, mensaje, detalles}}`. El mensaje de la excepción sólo lleva el status y
    el código estable: el texto de la API puede repetir datos enviados, así que queda en `detalles`."""
    codigo, detalles = "", tuple[DetalleError, ...]()
    try:
        err = r.json().get("error") or {}
        codigo = str(err.get("codigo") or "")
        detalles = tuple(
            DetalleError(str(d.get("ruta") or ""), str(d.get("mensaje") or ""))
            for d in (err.get("detalles") or [])
            if isinstance(d, dict)
        )
        if not detalles and err.get("mensaje"):
            detalles = (DetalleError("cuerpo", str(err["mensaje"])),)
    except (ValueError, AttributeError):
        pass
    sufijo = f" ({codigo})" if codigo else ""
    return ErrorFamiliograma(
        f"API de familiograma HTTP {r.status_code}{sufijo}",
        status=r.status_code,
        codigo=codigo,
        detalles=detalles,
    )
