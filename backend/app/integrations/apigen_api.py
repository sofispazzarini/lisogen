"""Consultas del catálogo de bioinformática de Apigen."""

import asyncio
import re
from typing import Any

import requests

from app.config import Settings
from app.domain.errores import ErrorNegocio
from app.integrations.ports import VarianteExterna

CODIGOS_PATOLOGIA = {
    "asmd": "ASMD",
    "fabry": "FABRY",
    "gaucher": "GAUCHER",
    "mps 1": "MPS1",
    "pompe": "POMPE",
}


class ApigenNoDisponible(ErrorNegocio):
    def __init__(self) -> None:
        super().__init__(
            "APIGEN_NO_DISPONIBLE", "El catálogo de Apigen no está disponible. Intentá de nuevo.", 502
        )


class ApigenApi:
    def __init__(self, settings: Settings) -> None:
        if not settings.apigen_api_key:
            raise RuntimeError("APIGEN_MODO=api requiere APIGEN_API_KEY")
        if not settings.apigen_api_url.startswith("https://"):
            raise RuntimeError("APIGEN_API_URL tiene que usar https://")
        self._url = settings.apigen_api_url.rstrip("/")
        self._cabeceras = {"apikey": settings.apigen_api_key}

    def _llamar(
        self,
        metodo: str,
        ruta: str,
        *,
        params: dict[str, str | int] | None = None,
        cuerpo: dict[str, str] | None = None,
    ) -> list[Any]:
        try:
            respuesta = requests.request(
                metodo,
                f"{self._url}/{ruta}",
                headers=self._cabeceras,
                params=params,
                json=cuerpo,
                timeout=5,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ApigenNoDisponible() from exc
        if respuesta.status_code != 200:
            raise ApigenNoDisponible()
        try:
            filas = respuesta.json()
        except ValueError as exc:
            raise ApigenNoDisponible() from exc
        if not isinstance(filas, list):
            raise ApigenNoDisponible()
        return filas

    async def genes_por_patologia(self, *, patologia: str) -> list[str]:
        codigo = CODIGOS_PATOLOGIA.get(patologia.strip().casefold())
        if codigo is None:
            return []  # Las patologías locales pueden usar los genes cargados a mano.
        filas = await asyncio.to_thread(
            self._llamar,
            "POST",
            "rpc/genes_por_patologia",
            cuerpo={
                "p_patologia": codigo,
            },
        )
        if not all(isinstance(gen, str) and gen for gen in filas):
            raise ApigenNoDisponible()
        return filas

    async def genes_hallazgos_secundarios(self) -> list[str]:
        filas = await asyncio.to_thread(
            self._llamar, "GET", "genes_hallazgos_secundarios", params={"select": "gen"}
        )
        if not all(
            isinstance(fila, dict) and isinstance(fila.get("gen"), str) and fila["gen"] for fila in filas
        ):
            raise ApigenNoDisponible()
        return [fila["gen"] for fila in filas]

    async def _variantes(self, gen: str, limite: int, offset: int, filtro: str = "") -> list[VarianteExterna]:
        params: dict[str, str | int] = {
            "gen": f"eq.{gen}",
            "select": "id,hgvs_c",
            "order": "id",
            "limit": limite,
            "offset": offset,
        }
        if filtro:
            params["hgvs_c"] = filtro
        filas = await asyncio.to_thread(self._llamar, "GET", "variantes", params=params)
        variantes = []
        for fila in filas:
            if not isinstance(fila, dict):
                raise ApigenNoDisponible()
            id_externo, nomenclatura = fila.get("id"), fila.get("hgvs_c")
            if not isinstance(id_externo, str) or not id_externo:
                raise ApigenNoDisponible()
            if not isinstance(nomenclatura, str) or not nomenclatura:
                raise ApigenNoDisponible()
            variantes.append(VarianteExterna(nomenclatura, id_externo))
        return variantes

    async def variantes_por_gen(
        self, *, gen: str, texto: str = "", limite: int = 50, offset: int = 0
    ) -> list[VarianteExterna]:
        # imatch permite buscar literalmente signos de HGVS como "_" y "*".
        filtro = f"imatch.{re.escape(texto)}" if texto else ""
        return await self._variantes(gen, limite, offset, filtro)

    async def variante_exacta(self, *, gen: str, nomenclatura: str) -> VarianteExterna | None:
        filtro = f"eq.{nomenclatura}"
        variantes = await self._variantes(gen, 1, 0, filtro)
        return next((v for v in variantes if v.nomenclatura == nomenclatura), None)
