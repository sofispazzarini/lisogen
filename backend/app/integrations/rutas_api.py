"""Adaptador de la API de Optimización de Recorridos (OSRM, REST/JSON).

`POST /api/optimizacion` recibe `{"coordenadas": [{"lat", "lon"}, ...]}` y devuelve la misma lista
reordenada: la primera coordenada es el punto de partida y la última el destino (no se mueven); sólo
ordena las del medio. La API no conoce ids, así que se traducen de vuelta por coordenada.
Si la API falla, se usa el orden del mock para que el Transportista no se quede sin Orden del Día.
`requests` en un hilo."""

import asyncio
import logging
from collections import defaultdict, deque
from typing import Any

import requests

from app.config import Settings
from app.integrations.ports import OptimizacionRutasPort, Parada, Punto

log = logging.getLogger(__name__)

TIMEOUT_SEG = 30  # corre en Vercel: la primera llamada puede tardar (arranque en frío)
DECIMALES = 5  # ~1 m: tolerancia para reconocer una coordenada que la API devuelve redondeada


class ErrorRutasApi(Exception):
    """La API de Optimización no respondió o devolvió algo que no se puede usar."""


def _coord(p: Punto) -> dict[str, float]:
    """Punto del dominio (latitud/longitud) → coordenada de la API (`lat`/`lon`)."""
    return {"lat": float(p.latitud), "lon": float(p.longitud)}


def _clave(lat: float, lon: float) -> tuple[float, float]:
    """Coordenada redondeada, para reconocer una parada aunque la API la devuelva con otro redondeo."""
    return round(lat, DECIMALES), round(lon, DECIMALES)


class RutasApi:
    """Ordena las paradas de una Orden del Día con la API de Optimización (puerto `OptimizacionRutasPort`)."""

    def __init__(self, settings: Settings, respaldo: OptimizacionRutasPort | None = None) -> None:
        """`respaldo`: adaptador que se usa si la API falla (el mock); sin él, el error se propaga."""
        self._url = settings.rutas_api_url
        if not self._url.startswith("https://"):
            raise RuntimeError("RUTAS_API_URL tiene que ser https://")
        self._respaldo = respaldo

    def _post(self, coordenadas: list[dict[str, float]]) -> list[dict[str, Any]]:
        """POST bloqueante (corre en un hilo). Devuelve las coordenadas reordenadas por la API."""
        try:
            r = requests.post(self._url, json={"coordenadas": coordenadas}, timeout=TIMEOUT_SEG)
            r.raise_for_status()
            datos = r.json()
        except requests.HTTPError as e:
            raise ErrorRutasApi(f"API de Optimización HTTP {r.status_code}") from e
        except (requests.RequestException, ValueError) as e:
            raise ErrorRutasApi(f"API de Optimización sin respuesta ({type(e).__name__})") from e
        lista = datos.get("coordenadas") if isinstance(datos, dict) else None
        if not isinstance(lista, list):
            raise ErrorRutasApi("La API de Optimización no devolvió 'coordenadas'")
        return lista

    async def _ordenar(self, origen: Punto, paradas: list[Parada], destino: Punto) -> list[int]:
        """Pide el orden a la API y traduce las coordenadas devueltas a ids de parada."""
        respuesta = await asyncio.to_thread(
            self._post, [_coord(origen), *(_coord(p.punto) for p in paradas), _coord(destino)]
        )
        medio = respuesta[1:-1]  # el primero y el último son el origen y el destino
        if len(medio) != len(paradas):
            raise ErrorRutasApi("La API de Optimización devolvió otra cantidad de coordenadas")
        pendientes: dict[tuple[float, float], deque[int]] = defaultdict(deque)
        for p in sorted(paradas, key=lambda p: p.id):  # coordenadas repetidas: se asignan por id
            pendientes[_clave(float(p.punto.latitud), float(p.punto.longitud))].append(p.id)
        orden = []
        for c in medio:
            try:
                ids = pendientes[_clave(float(c["lat"]), float(c["lon"]))]
            except (KeyError, TypeError, ValueError) as e:
                raise ErrorRutasApi("Coordenada inválida en la respuesta de la API de Optimización") from e
            if not ids:
                raise ErrorRutasApi("La API de Optimización devolvió una coordenada que no se envió")
            orden.append(ids.popleft())
        return orden

    async def ordenar_paradas(
        self, *, origen: Punto, paradas: list[Parada], destino: Punto | None = None
    ) -> list[int]:
        """Ids de las paradas en orden de visita. `origen` y `destino` quedan fijos (sin destino, se vuelve
        al origen). Con menos de 2 paradas no hay nada que ordenar y no se llama a la API."""
        if len(paradas) < 2:  # con 0 o 1 parada no hay nada que ordenar
            return [p.id for p in paradas]
        try:
            return await self._ordenar(origen, paradas, destino or origen)
        except ErrorRutasApi as e:
            if self._respaldo is None:
                raise
            log.warning("API de Optimización no disponible, se usa el orden del mock: %s", e)
            return await self._respaldo.ordenar_paradas(origen=origen, paradas=paradas, destino=destino)
