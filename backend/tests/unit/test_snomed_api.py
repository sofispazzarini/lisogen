"""Adaptador de la API de síntomas SNOMED CT, contra un servidor HTTP local que imita su contrato."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import Settings
from app.integrations.ports import ConceptoSnomed, ErrorSnomed
from app.integrations.snomed_api import SnomedApi

PEDIDOS: list[dict[str, Any]] = []
RESPUESTA: dict[str, Any] = {"status": 200, "cuerpo": {"resultados": []}}


class _Falso(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        ruta = urlparse(self.path)
        PEDIDOS.append({"ruta": ruta.path, "query": parse_qs(ruta.query), "cabeceras": dict(self.headers)})
        datos = json.dumps(RESPUESTA["cuerpo"]).encode()
        self.send_response(RESPUESTA["status"])
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)


@pytest.fixture
def servidor() -> Iterator[str]:
    PEDIDOS.clear()
    RESPUESTA.update(status=200, cuerpo={"resultados": []})
    srv = HTTPServer(("127.0.0.1", 0), _Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/terminologia/sintomas"
    srv.shutdown()


def _api(url: str) -> SnomedApi:
    api = SnomedApi(Settings(snomed_api_key="clave-secreta"))
    api._url = url  # el servidor local es http; el constructor exige https
    return api


def _fila(sctid: str, termino: str, estrategia: str = "exacta") -> dict[str, Any]:
    return {"sctid": sctid, "termino_preferido": termino, "estrategia": estrategia, "similitud": 0.9}


async def test_arma_el_pedido_y_devuelve_los_conceptos(servidor: str) -> None:
    RESPUESTA["cuerpo"] = {"resultados": [_fila("386661006", "fiebre"), _fila("304213008", "fiebre baja")]}
    conceptos = await _api(servidor).buscar(texto="  fiebre ", limite=5)
    assert conceptos == [ConceptoSnomed(386661006, "fiebre"), ConceptoSnomed(304213008, "fiebre baja")]
    pedido = PEDIDOS[0]
    assert pedido["query"] == {"q": ["fiebre"], "limite": ["5"]}
    assert pedido["cabeceras"]["X-API-Key"] == "clave-secreta"
    assert pedido["cabeceras"]["x-region"] == "us-east-1"


async def test_sin_coincidencias_es_una_lista_vacia_y_no_un_error(servidor: str) -> None:
    assert await _api(servidor).buscar(texto="dolor de muela") == []


async def test_con_menos_de_3_letras_no_llama_a_la_api(servidor: str) -> None:
    assert await _api(servidor).buscar(texto="ab") == []
    assert await _api(servidor).buscar(texto="  a ") == []
    assert PEDIDOS == []


async def test_el_limite_se_acota_a_lo_que_acepta_la_api(servidor: str) -> None:
    await _api(servidor).buscar(texto="fiebre", limite=500)
    await _api(servidor).buscar(texto="fiebre", limite=0)
    assert [p["query"]["limite"] for p in PEDIDOS] == [["50"], ["1"]]


async def test_descarta_repetidos_y_filas_invalidas(servidor: str) -> None:
    RESPUESTA["cuerpo"] = {
        "resultados": [
            _fila("267036007", "disnea", "semantica"),
            _fila("267036007", "disnea", "lexica"),  # el mismo síntoma por otra capa
            _fila("no-es-un-numero", "raro"),
            _fila("230145002", "  "),
            "basura",
            {"termino_preferido": "sin código"},
        ]
    }
    assert await _api(servidor).buscar(texto="falta el aire") == [ConceptoSnomed(267036007, "disnea")]


@pytest.mark.parametrize("status", [400, 401, 500, 503])
async def test_errores_de_la_api(servidor: str, status: int) -> None:
    RESPUESTA.update(status=status, cuerpo={"detalle": "algo falló"})
    with pytest.raises(ErrorSnomed) as e:
        await _api(servidor).buscar(texto="fiebre")
    assert e.value.status == status and "algo falló" in str(e.value)
    assert "clave-secreta" not in str(e.value)


@pytest.mark.parametrize("cuerpo", [[], {"resultados": "x"}, {"otra": 1}])
async def test_respuesta_mal_formada(servidor: str, cuerpo: Any) -> None:
    RESPUESTA["cuerpo"] = cuerpo
    with pytest.raises(ErrorSnomed):
        await _api(servidor).buscar(texto="fiebre")


async def test_sin_conexion() -> None:
    api = SnomedApi(Settings(snomed_api_key="k"))
    api._url = "http://127.0.0.1:1/terminologia/sintomas"  # puerto cerrado
    with pytest.raises(ErrorSnomed) as e:
        await api.buscar(texto="fiebre")
    assert e.value.status == 0


def test_exige_clave_y_https() -> None:
    with pytest.raises(RuntimeError, match="SNOMED_API_KEY"):
        SnomedApi(Settings(snomed_api_key=""))
    with pytest.raises(RuntimeError, match="https"):
        SnomedApi(Settings(snomed_api_key="k", snomed_api_url="http://x"))
