"""Adaptador de la API de Obras Sociales (módulo 6, Supabase, REST/JSON).

Autenticación: `x-api-key` con la clave del grupo. La API es un simulador: una solicitud de cobertura queda
`pendiente` hasta que alguien llama a las URLs de simulación que devuelve (`urls_simulacion`). En LisoGen
lo hace el botón del Administrativo (E17/E18) y, para una demanda, tras cargar la decisión judicial (E10).

Los pedidos que modifican datos no se reintentan solos: ante un timeout la operación pudo haberse aplicado
(`ErrorObraSocial.incierto`). Autorizar o rechazar una solicitud que ya está en ese estado se toma como
hecho. Usa `requests` en un hilo."""

import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from app.config import Settings
from app.integrations.ports import ErrorObraSocial, SolicitudExterna

TIMEOUT_SEG = 15
TIMEOUT_DEMANDA_SEG = 30
MAX_DEMANDA_BYTES = 5 * 1024 * 1024


class ObrasSocialesApi:
    def __init__(self, settings: Settings) -> None:
        if not settings.obras_sociales_api_key:
            raise RuntimeError("OBRAS_SOCIALES_MODO=api requiere OBRAS_SOCIALES_API_KEY (la clave del grupo)")
        self._base = settings.obras_sociales_api_url.rstrip("/")
        if not self._base.startswith("https://"):
            raise RuntimeError("OBRAS_SOCIALES_API_URL tiene que ser https:// (la clave va en un encabezado)")
        self._cabeceras = {"x-api-key": settings.obras_sociales_api_key}

    def _llamar(
        self,
        metodo: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        archivos: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = TIMEOUT_SEG,
    ) -> Any:
        """Pedido bloqueante (corre en un hilo). Devuelve el JSON de la respuesta."""
        try:
            r = requests.request(
                metodo,
                url,
                headers=self._cabeceras,
                json=json,
                files=archivos,
                params=params,
                timeout=timeout,
            )
        except requests.RequestException as e:
            raise ErrorObraSocial(
                f"API de Obras Sociales sin respuesta ({type(e).__name__})", incierto=True
            ) from e
        if r.status_code >= 400:
            codigo, mensaje = _error(r)
            raise ErrorObraSocial(
                f"API de Obras Sociales HTTP {r.status_code}: {mensaje}",
                status=r.status_code,
                codigo=codigo,
                incierto=r.status_code >= 500,
            )
        try:
            return r.json()
        except ValueError as e:
            raise ErrorObraSocial("API de Obras Sociales devolvió una respuesta que no es JSON") from e

    async def _buscar(self, codigo: str) -> dict[str, Any]:
        """`GET /obras-sociales?buscar=`: la API busca por nombre, sigla o código RNOS. Se exige coincidencia
        exacta con el código (o la sigla) para no tomar otra Obra Social parecida."""
        datos = await asyncio.to_thread(
            self._llamar, "GET", f"{self._base}/obras-sociales", params={"buscar": codigo, "por_pagina": 100}
        )
        filas = datos.get("datos") if isinstance(datos, dict) else None
        if not isinstance(filas, list):
            raise ErrorObraSocial("API de Obras Sociales devolvió un listado que no se entiende")
        buscado = codigo.strip().lower()
        for fila in filas:
            if not isinstance(fila, dict):
                continue
            claves = {str(fila.get(k) or "").lower() for k in ("rnos_codigo", "sigla", "nombre")}
            if buscado in claves:
                return fila
        raise ErrorObraSocial(f"La API de Obras Sociales no conoce el código {codigo}", status=404)

    async def cobertura(self, *, codigo_obra_social: str, cantidad_genes: int) -> Decimal:
        """Porcentaje por defecto de la Obra Social (`porcentaje_cobertura`)."""
        fila = await self._buscar(codigo_obra_social)
        try:
            pct = Decimal(str(fila["porcentaje_cobertura"]))
        except (KeyError, InvalidOperation) as e:
            raise ErrorObraSocial("API de Obras Sociales devolvió una cobertura inválida") from e
        if not Decimal(0) <= pct <= Decimal(100):
            raise ErrorObraSocial("API de Obras Sociales devolvió una cobertura fuera de 0 a 100")
        return pct

    async def solicitar(
        self, *, codigo_obra_social: str, paciente_nombre: str, fecha: date, referencia: str
    ) -> SolicitudExterna:
        """`POST /solicitudes`: queda `pendiente`."""
        fila = await self._buscar(codigo_obra_social)
        datos = await asyncio.to_thread(
            self._llamar,
            "POST",
            f"{self._base}/solicitudes",
            json={
                "obra_social_id": fila["id"],
                "paciente_nombre": paciente_nombre,
                "fecha": fecha.isoformat(),
                "referencia_externa": referencia,
            },
        )
        return _solicitud(datos)

    async def autorizar(
        self, *, solicitud: SolicitudExterna, porcentaje: Decimal | None = None
    ) -> SolicitudExterna:
        """POST a la URL de simulación `autorizar`. Con una demanda hay que mandar el porcentaje."""
        cuerpo = {"porcentaje": float(porcentaje)} if porcentaje is not None else None
        return await self._resolver(solicitud, solicitud.url_autorizar, "autorizada", cuerpo)

    async def rechazar(self, *, solicitud: SolicitudExterna, motivo: str) -> SolicitudExterna:
        """POST a la URL de simulación `rechazar`, con el motivo."""
        return await self._resolver(solicitud, solicitud.url_rechazar, "rechazada", {"motivo": motivo})

    async def _resolver(
        self, solicitud: SolicitudExterna, url: str | None, estado: str, cuerpo: dict[str, Any] | None
    ) -> SolicitudExterna:
        if not url:
            raise ErrorObraSocial("La solicitud no tiene URL de simulación", status=409, codigo="SIN_URL")
        try:
            datos = await asyncio.to_thread(self._llamar, "POST", url, json=cuerpo)
        except ErrorObraSocial as e:
            # Si el pedido anterior sí se aplicó (timeout) la API responde 409: se confirma el estado.
            if e.status != 409:
                raise
            actual = await self._consultar(solicitud.id)
            if actual.estado != estado:
                raise
            return actual
        return _solicitud(datos)

    async def _consultar(self, solicitud_id: str) -> SolicitudExterna:
        datos = await asyncio.to_thread(self._llamar, "GET", f"{self._base}/solicitudes/{solicitud_id}")
        return _solicitud(datos)

    async def presentar_demanda(
        self, *, solicitud: SolicitudExterna, nombre_archivo: str, contenido: bytes
    ) -> SolicitudExterna:
        """`POST /solicitudes/{id}/demanda`: PDF de hasta 5 MB en el campo `archivo`."""
        if len(contenido) > MAX_DEMANDA_BYTES:
            raise ErrorObraSocial("La demanda supera los 5 MB", status=413)
        datos = await asyncio.to_thread(
            self._llamar,
            "POST",
            f"{self._base}/solicitudes/{solicitud.id}/demanda",
            archivos={"archivo": (nombre_archivo or "decision-judicial.pdf", contenido, "application/pdf")},
            timeout=TIMEOUT_DEMANDA_SEG,
        )
        return _solicitud(datos)


def _solicitud(datos: Any) -> SolicitudExterna:
    if not isinstance(datos, dict) or not datos.get("id") or not datos.get("estado"):
        raise ErrorObraSocial("API de Obras Sociales devolvió una solicitud que no se entiende")
    urls = datos.get("urls_simulacion")
    urls = urls if isinstance(urls, dict) else {}
    return SolicitudExterna(
        id=str(datos["id"]),
        estado=str(datos["estado"]),
        url_autorizar=urls.get("autorizar") if isinstance(urls.get("autorizar"), str) else None,
        url_rechazar=urls.get("rechazar") if isinstance(urls.get("rechazar"), str) else None,
    )


def _error(r: requests.Response) -> tuple[str, str]:
    """`error.codigo` y `error.mensaje` del cuerpo de error (o el texto HTTP si no vienen)."""
    try:
        e = r.json().get("error") or {}
        return str(e.get("codigo") or ""), str(e.get("mensaje") or r.reason)
    except (ValueError, AttributeError):
        return "", str(r.reason)
