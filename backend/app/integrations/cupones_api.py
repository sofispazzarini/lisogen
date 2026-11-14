"""Adaptador de la API de Cupones de Exoma Care (Supabase, REST/JSON).

Autenticación: `X-API-Key` con la clave del grupo (no se envía `p_grupo_id` ni `Authorization`). Los IDs
de médicos, pacientes y gerente son los de LisoGen, pasados como texto: la API sólo los guarda.

Los pedidos que modifican datos no se reintentan solos: ante un timeout el Cupón pudo haberse procesado
igual (`ErrorCupones.incierto`), así que quien llama consulta el estado antes de repetir. Usa `requests`
en un hilo."""

import asyncio
from typing import Any

import requests

from app.config import Settings
from app.integrations.ports import CuponExterno, ErrorCupones

TIMEOUT_SEG = 15


class CuponesApi:
    def __init__(self, settings: Settings) -> None:
        if not settings.cupones_api_key:
            raise RuntimeError("CUPONES_MODO=api requiere CUPONES_API_KEY (la clave del grupo)")
        self._base = settings.cupones_api_url.rstrip("/")
        if not self._base.startswith("https://"):
            raise RuntimeError("CUPONES_API_URL tiene que ser https:// (la clave viaja en un encabezado)")
        self._key = settings.cupones_api_key

    def _llamar(self, ruta: str, cuerpo: dict[str, Any]) -> Any:
        """POST bloqueante (corre en un hilo). Devuelve el JSON de la respuesta."""
        try:
            r = requests.post(
                f"{self._base}{ruta}",
                headers={"X-API-Key": self._key},
                json=cuerpo,
                timeout=TIMEOUT_SEG,
            )
        except requests.RequestException as e:
            raise ErrorCupones(f"API de Cupones sin respuesta ({type(e).__name__})", incierto=True) from e
        if r.status_code >= 400:
            raise ErrorCupones(
                f"API de Cupones HTTP {r.status_code}: {_detalle(r)}",
                status=r.status_code,
                incierto=r.status_code >= 500,
            )
        try:
            return r.json()
        except ValueError as e:
            raise ErrorCupones("API de Cupones devolvió una respuesta que no es JSON") from e

    async def generar(self, *, gerente_id: int, descuento_pct: int, cantidad: int) -> list[CuponExterno]:
        """`POST /generar_cupones_gerencia`: crea el lote (vencen a los 30 días; un gerente por grupo)."""
        datos = await asyncio.to_thread(
            self._llamar,
            "/generar_cupones_gerencia",
            {
                "p_gerente_id": str(gerente_id),
                "p_cantidad": cantidad,
                "p_porcentaje_descuento": descuento_pct,
            },
        )
        if not isinstance(datos, list) or len(datos) != cantidad:
            raise ErrorCupones("API de Cupones devolvió un lote que no coincide con lo pedido")
        cupones = []
        for fila in datos:
            codigo = str(fila.get("codigo_cupon") or "") if isinstance(fila, dict) else ""
            if not codigo:
                raise ErrorCupones("API de Cupones devolvió un Cupón sin código")
            cupones.append(CuponExterno(codigo))
        return cupones

    async def asignar_a_medico(self, *, gerente_id: int, medico_id: int, codigo: str) -> None:
        """`POST /asignar_cupon_a_medico`: el Cupón debe ser del gerente y estar disponible."""
        await self._confirmar(
            "/asignar_cupon_a_medico",
            {"p_gerente_id": str(gerente_id), "p_medico_id": str(medico_id), "p_codigo": codigo},
        )

    async def asignar_a_paciente(self, *, medico_id: int, paciente_id: int, codigo: str) -> None:
        """`POST /asignar_cupon_a_paciente`: un solo Cupón por Paciente en el grupo (409 si ya tuvo uno)."""
        await self._confirmar(
            "/asignar_cupon_a_paciente",
            {"p_medico_id": str(medico_id), "p_paciente_id": str(paciente_id), "p_codigo": codigo},
        )

    async def canjear(self, *, paciente_id: int, codigo: str) -> None:
        """`POST /canjear_cupon`: valida grupo, Paciente, estado y vencimiento, y lo marca usado."""
        await self._confirmar("/canjear_cupon", {"p_paciente_id": str(paciente_id), "p_codigo": codigo})

    async def _confirmar(self, ruta: str, cuerpo: dict[str, Any]) -> None:
        if await asyncio.to_thread(self._llamar, ruta, cuerpo) is not True:
            raise ErrorCupones(f"API de Cupones no confirmó la operación ({ruta})")


def _detalle(r: requests.Response) -> str:
    """`message` del cuerpo de error de la API (o el texto HTTP si no viene)."""
    try:
        datos = r.json()
        return str(datos.get("message") or datos.get("code") or r.reason)
    except (ValueError, AttributeError):
        return str(r.reason)