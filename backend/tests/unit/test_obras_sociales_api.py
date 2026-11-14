"""Adaptador de la API de Obras Sociales, contra un servidor HTTP local que imita su contrato."""

import json
import threading
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import Settings
from app.integrations.obras_sociales_api import ObrasSocialesApi
from app.integrations.ports import ErrorObraSocial, SolicitudExterna

PEDIDOS: list[dict[str, Any]] = []
# Respuestas en orden por "METODO /ruta"; la última se repite
RESPUESTAS: dict[str, list[dict[str, Any]]] = {}

OSDE = {
    "id": "uuid-osde",
    "rnos_codigo": "DEMO-001",
    "nombre": "OSDE",
    "sigla": "OSDE",
    "porcentaje_cobertura": 80,
}
OSDE_BINARIO = {
    "id": "uuid-otra",
    "rnos_codigo": "DEMO-002",
    "nombre": "OSDE Binario",
    "sigla": None,
    "porcentaje_cobertura": 40,
}


def _solicitud(estado: str = "pendiente") -> dict[str, Any]:
    return {
        "id": "sol-1",
        "estado": estado,
        "urls_simulacion": {
            "autorizar": "__BASE__/simulacion/tok/autorizar",
            "rechazar": "__BASE__/simulacion/tok/rechazar",
        },
    }


class _Falso(BaseHTTPRequestHandler):
    base = ""

    def log_message(self, *args: object) -> None:
        pass

    def _responder(self, metodo: str) -> None:
        largo = int(self.headers.get("Content-Length") or 0)
        crudo = self.rfile.read(largo) if largo else b""
        ruta = urlparse(self.path)
        PEDIDOS.append(
            {
                "metodo": metodo,
                "ruta": ruta.path,
                "query": parse_qs(ruta.query),
                "cabeceras": dict(self.headers),
                "crudo": crudo,
            }
        )
        cola = RESPUESTAS[f"{metodo} {ruta.path}"]
        n = sum(1 for p in PEDIDOS if (p["metodo"], p["ruta"]) == (metodo, ruta.path))
        r = cola[min(n, len(cola)) - 1]
        datos = json.dumps(r["cuerpo"]).replace("__BASE__", self.base).encode()
        self.send_response(r["status"])
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_GET(self) -> None:
        self._responder("GET")

    def do_POST(self) -> None:
        self._responder("POST")


@pytest.fixture
def servidor() -> Iterator[str]:
    PEDIDOS.clear()
    RESPUESTAS.clear()
    srv = HTTPServer(("127.0.0.1", 0), _Falso)
    _Falso.base = f"http://127.0.0.1:{srv.server_port}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield _Falso.base
    srv.shutdown()


def _api(url: str) -> ObrasSocialesApi:
    api = ObrasSocialesApi(Settings(obras_sociales_api_key="osk_clave-secreta"))
    api._base = url  # el servidor local es http; el constructor exige https
    return api


def _ok(cuerpo: Any, status: int = 200) -> list[dict[str, Any]]:
    return [{"status": status, "cuerpo": cuerpo}]


def _listado(*filas: dict[str, Any]) -> list[dict[str, Any]]:
    return _ok(
        {"datos": list(filas), "pagina": 1, "por_pagina": 100, "total": len(filas), "total_paginas": 1}
    )


def _externa(estado: str = "pendiente") -> SolicitudExterna:
    return SolicitudExterna(
        id="sol-1",
        estado=estado,
        url_autorizar=f"{_Falso.base}/simulacion/tok/autorizar",
        url_rechazar=f"{_Falso.base}/simulacion/tok/rechazar",
    )


async def test_cobertura_busca_por_codigo_y_manda_la_clave(servidor: str) -> None:
    RESPUESTAS["GET /obras-sociales"] = _listado(OSDE_BINARIO, OSDE)  # la API también devuelve parecidas
    pct = await _api(servidor).cobertura(codigo_obra_social="demo-001", cantidad_genes=5)
    assert pct == Decimal(80)  # coincidencia exacta con el código, no la primera fila
    pedido = PEDIDOS[0]
    assert pedido["cabeceras"]["x-api-key"] == "osk_clave-secreta"
    assert pedido["query"]["buscar"] == ["demo-001"]


async def test_cobertura_tambien_encuentra_por_sigla(servidor: str) -> None:
    RESPUESTAS["GET /obras-sociales"] = _listado(OSDE)
    assert await _api(servidor).cobertura(codigo_obra_social="OSDE", cantidad_genes=5) == Decimal(80)


async def test_cobertura_de_una_obra_social_desconocida(servidor: str) -> None:
    RESPUESTAS["GET /obras-sociales"] = _listado(OSDE_BINARIO)
    with pytest.raises(ErrorObraSocial) as e:
        await _api(servidor).cobertura(codigo_obra_social="DEMO-001", cantidad_genes=5)
    assert e.value.status == 404


@pytest.mark.parametrize("pct", [-1, 101, "abc", None])
async def test_cobertura_invalida(servidor: str, pct: Any) -> None:
    RESPUESTAS["GET /obras-sociales"] = _listado({**OSDE, "porcentaje_cobertura": pct})
    with pytest.raises(ErrorObraSocial):
        await _api(servidor).cobertura(codigo_obra_social="DEMO-001", cantidad_genes=5)


async def test_solicitar_arma_el_pedido_y_devuelve_las_urls(servidor: str) -> None:
    RESPUESTAS["GET /obras-sociales"] = _listado(OSDE)
    RESPUESTAS["POST /solicitudes"] = _ok(_solicitud(), 201)
    sol = await _api(servidor).solicitar(
        codigo_obra_social="DEMO-001",
        paciente_nombre="Ana Pérez",
        fecha=date(2026, 11, 2),
        referencia="EST-1",
    )
    assert (sol.id, sol.estado) == ("sol-1", "pendiente")
    assert sol.url_autorizar == f"{servidor}/simulacion/tok/autorizar"
    cuerpo = json.loads(PEDIDOS[-1]["crudo"])
    assert cuerpo == {
        "obra_social_id": "uuid-osde",
        "paciente_nombre": "Ana Pérez",
        "fecha": "2026-11-02",
        "referencia_externa": "EST-1",
    }


async def test_autorizar_sin_demanda_no_manda_porcentaje(servidor: str) -> None:
    RESPUESTAS["POST /simulacion/tok/autorizar"] = _ok(_solicitud("autorizada"))
    res = await _api(servidor).autorizar(solicitud=_externa())
    assert res.estado == "autorizada"
    assert PEDIDOS[0]["crudo"] == b""
    assert PEDIDOS[0]["cabeceras"]["x-api-key"] == "osk_clave-secreta"


async def test_autorizar_una_demanda_manda_el_porcentaje(servidor: str) -> None:
    RESPUESTAS["POST /simulacion/tok/autorizar"] = _ok(_solicitud("autorizada"))
    await _api(servidor).autorizar(solicitud=_externa("demanda_en_curso"), porcentaje=Decimal("60.00"))
    assert json.loads(PEDIDOS[0]["crudo"]) == {"porcentaje": 60.0}


async def test_rechazar_manda_el_motivo(servidor: str) -> None:
    RESPUESTAS["POST /simulacion/tok/rechazar"] = _ok(_solicitud("rechazada"))
    res = await _api(servidor).rechazar(solicitud=_externa(), motivo="No cubre el estudio")
    assert res.estado == "rechazada"
    assert json.loads(PEDIDOS[0]["crudo"]) == {"motivo": "No cubre el estudio"}


async def test_autorizar_dos_veces_se_toma_como_hecho(servidor: str) -> None:
    """Si un timeout dejó la solicitud ya autorizada, repetir devuelve 409 y se confirma con el estado."""
    RESPUESTAS["POST /simulacion/tok/autorizar"] = _ok(
        {"error": {"codigo": "ESTADO_INVALIDO", "mensaje": "La solicitud ya fue autorizada"}}, 409
    )
    RESPUESTAS["GET /solicitudes/sol-1"] = _ok(_solicitud("autorizada"))
    res = await _api(servidor).autorizar(solicitud=_externa())
    assert res.estado == "autorizada"


async def test_autorizar_una_solicitud_rechazada_sigue_siendo_error(servidor: str) -> None:
    RESPUESTAS["POST /simulacion/tok/autorizar"] = _ok(
        {"error": {"codigo": "ESTADO_INVALIDO", "mensaje": "La solicitud ya fue rechazada"}}, 409
    )
    RESPUESTAS["GET /solicitudes/sol-1"] = _ok(_solicitud("rechazada"))
    with pytest.raises(ErrorObraSocial) as e:
        await _api(servidor).autorizar(solicitud=_externa())
    assert e.value.status == 409 and e.value.codigo == "ESTADO_INVALIDO"


async def test_resolver_sin_url_de_simulacion() -> None:
    api = ObrasSocialesApi(Settings(obras_sociales_api_key="osk_x"))
    with pytest.raises(ErrorObraSocial):
        await api.autorizar(solicitud=SolicitudExterna("sol-1", "pendiente", None, None))


async def test_presentar_demanda_sube_el_pdf_en_el_campo_archivo(servidor: str) -> None:
    RESPUESTAS["POST /solicitudes/sol-1/demanda"] = _ok(_solicitud("demanda_en_curso"), 201)
    res = await _api(servidor).presentar_demanda(
        solicitud=_externa("rechazada"), nombre_archivo="sentencia.pdf", contenido=b"%PDF-1.4 sentencia"
    )
    assert res.estado == "demanda_en_curso"
    pedido = PEDIDOS[0]
    assert pedido["cabeceras"]["Content-Type"].startswith("multipart/form-data")
    assert b'name="archivo"; filename="sentencia.pdf"' in pedido["crudo"]
    assert b"%PDF-1.4 sentencia" in pedido["crudo"]


async def test_presentar_demanda_de_mas_de_5_mb_no_llega_a_la_api(servidor: str) -> None:
    grande = b"%PDF-" + b"0" * (5 * 1024 * 1024)
    with pytest.raises(ErrorObraSocial) as e:
        await _api(servidor).presentar_demanda(solicitud=_externa(), nombre_archivo="s.pdf", contenido=grande)
    assert e.value.status == 413 and PEDIDOS == []


async def test_error_de_la_api_trae_codigo_y_mensaje(servidor: str) -> None:
    RESPUESTAS["GET /obras-sociales"] = _ok(
        {"error": {"codigo": "API_KEY_INVALIDA", "mensaje": "Falta la API key o no es válida"}}, 401
    )
    with pytest.raises(ErrorObraSocial) as e:
        await _api(servidor).cobertura(codigo_obra_social="OSDE", cantidad_genes=5)
    assert (e.value.status, e.value.codigo, e.value.incierto) == (401, "API_KEY_INVALIDA", False)
    assert "osk_clave-secreta" not in str(e.value)


async def test_un_error_del_servidor_es_incierto(servidor: str) -> None:
    RESPUESTAS["POST /simulacion/tok/rechazar"] = _ok({"error": {"codigo": "ERROR", "mensaje": "x"}}, 500)
    with pytest.raises(ErrorObraSocial) as e:
        await _api(servidor).rechazar(solicitud=_externa(), motivo="No cubre")
    assert e.value.status == 500 and e.value.incierto


async def test_sin_conexion_es_incierto() -> None:
    api = ObrasSocialesApi(Settings(obras_sociales_api_key="osk_x"))
    api._base = "http://127.0.0.1:1"  # puerto cerrado
    with pytest.raises(ErrorObraSocial) as e:
        await api.cobertura(codigo_obra_social="OSDE", cantidad_genes=5)
    assert e.value.status == 0 and e.value.incierto


@pytest.mark.parametrize("cuerpo", [[], {"id": "x"}, {"estado": "pendiente"}])
async def test_solicitud_mal_formada(servidor: str, cuerpo: Any) -> None:
    RESPUESTAS["GET /obras-sociales"] = _listado(OSDE)
    RESPUESTAS["POST /solicitudes"] = _ok(cuerpo, 201)
    with pytest.raises(ErrorObraSocial):
        await _api(servidor).solicitar(
            codigo_obra_social="DEMO-001", paciente_nombre="Ana", fecha=date(2026, 11, 2), referencia="E"
        )


def test_exige_clave_y_https() -> None:
    with pytest.raises(RuntimeError, match="OBRAS_SOCIALES_API_KEY"):
        ObrasSocialesApi(Settings(obras_sociales_api_key=""))
    with pytest.raises(RuntimeError, match="https"):
        ObrasSocialesApi(Settings(obras_sociales_api_key="k", obras_sociales_api_url="http://x"))
