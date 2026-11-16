"""Adaptador de la API de síntomas SNOMED CT (Supabase, REST/JSON, Edición Argentina).

`GET .../terminologia/sintomas?q=texto&limite=n` con la clave del grupo en `X-API-Key`. Busca en tres capas
(exacta y prefijo, léxica con tolerancia a errores de tipeo y semántica por significado) y devuelve
*sugerencias*: el Médico elige. Un 200 con lista vacía no es un error. Se llama sólo desde el backend.
`x-region: us-east-1` baja la respuesta de unos 8 s a unos 1,2 s. Usa `requests` en un hilo."""

import asyncio
from typing import Any

import requests

from app.config import Settings
from app.integrations.ports import ConceptoSnomed, ErrorSnomed

TIMEOUT_SEG = 15
MIN_LETRAS = 3  # la API responde 400 con menos
MAX_LIMITE = 50


class SnomedApi:
    def __init__(self, settings: Settings) -> None:
        if not settings.snomed_api_key:
            raise RuntimeError("SNOMED_MODO=api requiere SNOMED_API_KEY (la clave del grupo)")
        self._url = settings.snomed_api_url
        if not self._url.startswith("https://"):
            raise RuntimeError("SNOMED_API_URL tiene que ser https:// (la clave viaja en un encabezado)")
        self._cabeceras = {"X-API-Key": settings.snomed_api_key, "x-region": "us-east-1"}

    def _llamar(self, texto: str, limite: int) -> Any:
        """GET bloqueante (corre en un hilo). Devuelve el JSON de la respuesta."""
        try:
            r = requests.get(
                self._url,
                headers=self._cabeceras,
                params={"q": texto, "limite": str(limite)},
                timeout=TIMEOUT_SEG,
            )
        except requests.RequestException as e:
            raise ErrorSnomed(f"API de SNOMED sin respuesta ({type(e).__name__})") from e
        if r.status_code != 200:
            raise ErrorSnomed(f"API de SNOMED HTTP {r.status_code}: {_detalle(r)}", status=r.status_code)
        try:
            return r.json()
        except ValueError as e:
            raise ErrorSnomed("API de SNOMED devolvió una respuesta que no es JSON") from e

    async def buscar(self, *, texto: str, limite: int = 20) -> list[ConceptoSnomed]:
        texto = texto.strip()
        if len(texto) < MIN_LETRAS:
            return []
        datos = await asyncio.to_thread(self._llamar, texto, max(1, min(limite, MAX_LIMITE)))
        filas = datos.get("resultados") if isinstance(datos, dict) else None
        if not isinstance(filas, list):
            raise ErrorSnomed("API de SNOMED devolvió una respuesta que no se entiende")
        conceptos: dict[int, ConceptoSnomed] = {}
        for fila in filas:
            if not isinstance(fila, dict):
                continue
            sctid, termino = str(fila.get("sctid") or ""), str(fila.get("termino_preferido") or "").strip()
            if sctid.isdigit() and termino:  # el SCTID viaja como texto; en LisoGen es bigint
                conceptos.setdefault(int(sctid), ConceptoSnomed(int(sctid), termino))
        return list(conceptos.values())


def _detalle(r: requests.Response) -> str:
    """`detalle` del cuerpo de error (o el texto HTTP si no viene)."""
    try:
        return str(r.json().get("detalle") or r.reason)
    except (ValueError, AttributeError):
        return str(r.reason)
