"""Adaptador de la API de Optimización de Recorridos, contra un servidor HTTP local que imita su contrato."""

import json
import threading
from collections.abc import Iterator
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from app.config import Settings
from app.integrations import mock
from app.integrations.ports import Parada, Punto
from app.integrations.rutas_api import ErrorRutasApi, RutasApi

PEDIDOS: list[dict[str, Any]] = []
RESPUESTA: dict[str, Any] = {"status": 200, "invertir_medio": True, "cuerpo": None}


class _Falso(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        pedido = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        PEDIDOS.append(pedido)
        coords = pedido["coordenadas"]
        if RESPUESTA["cuerpo"] is not None:
            cuerpo = RESPUESTA["cuerpo"]
        elif RESPUESTA["invertir_medio"]:  # "optimiza": deja fijas las puntas y da vuelta las del medio
            cuerpo = {"coordenadas": [coords[0], *reversed(coords[1:-1]), coords[-1]]}
        else:
            cuerpo = {"coordenadas": coords}
        datos = json.dumps(cuerpo).encode()
        self.send_response(RESPUESTA["status"])
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)


@pytest.fixture
def servidor() -> Iterator[str]:
    PEDIDOS.clear()
    RESPUESTA.update(status=200, invertir_medio=True, cuerpo=None)
    srv = HTTPServer(("127.0.0.1", 0), _Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/api/optimizacion"
    srv.shutdown()


def _punto(lat: str, lon: str) -> Punto:
    return Punto(Decimal(lat), Decimal(lon))


def _rutas(url: str, respaldo: mock.OptimizacionRutasMock | None = None) -> RutasApi:
    r = RutasApi(Settings(rutas_api_url="https://x/api"), respaldo=respaldo)
    r._url = url  # el servidor local es http; el constructor exige https
    return r


LAB = _punto("-34.919223", "-57.942838")
INICIO = _punto("-34.6", "-58.4")
A, B, C = (
    Parada(1, _punto("-34.7", "-58.1")),
    Parada(2, _punto("-34.8", "-58.0")),
    Parada(3, _punto("-34.75", "-58.05")),
)


async def test_arma_el_pedido_con_origen_y_destino_fijos(servidor: str) -> None:
    await _rutas(servidor).ordenar_paradas(origen=INICIO, paradas=[A, B, C], destino=LAB)
    coords = PEDIDOS[0]["coordenadas"]
    assert coords[0] == {"lat": -34.6, "lon": -58.4}
    assert coords[-1] == {"lat": -34.919223, "lon": -57.942838}
    assert len(coords) == 5


async def test_traduce_las_coordenadas_devueltas_a_ids(servidor: str) -> None:
    orden = await _rutas(servidor).ordenar_paradas(origen=INICIO, paradas=[A, B, C], destino=LAB)
    assert orden == [3, 2, 1]  # el servidor falso da vuelta las del medio


async def test_sin_destino_vuelve_al_origen(servidor: str) -> None:
    await _rutas(servidor).ordenar_paradas(origen=INICIO, paradas=[A, B])
    assert PEDIDOS[0]["coordenadas"][-1] == PEDIDOS[0]["coordenadas"][0]


async def test_con_una_parada_o_ninguna_no_llama_a_la_api(servidor: str) -> None:
    r = _rutas(servidor)
    assert await r.ordenar_paradas(origen=INICIO, paradas=[A], destino=LAB) == [1]
    assert await r.ordenar_paradas(origen=INICIO, paradas=[], destino=LAB) == []
    assert PEDIDOS == []


async def test_coordenadas_repetidas_se_asignan_por_id(servidor: str) -> None:
    gemela = Parada(9, A.punto)
    orden = await _rutas(servidor).ordenar_paradas(origen=INICIO, paradas=[gemela, A, B], destino=LAB)
    assert sorted(orden) == [1, 2, 9] and len(orden) == 3


async def test_tolera_coordenadas_redondeadas(servidor: str) -> None:
    RESPUESTA["cuerpo"] = {
        "coordenadas": [
            {"lat": -34.6, "lon": -58.4},
            {"lat": -34.8000001, "lon": -58.0},
            {"lat": -34.7, "lon": -58.1000002},
            {"lat": -34.919223, "lon": -57.942838},
        ]
    }
    assert await _rutas(servidor).ordenar_paradas(origen=INICIO, paradas=[A, B], destino=LAB) == [2, 1]


@pytest.mark.parametrize("status", [400, 500])
async def test_error_de_la_api_sin_respaldo(servidor: str, status: int) -> None:
    RESPUESTA.update(status=status, cuerpo={"error": "x"})
    with pytest.raises(ErrorRutasApi, match=str(status)):
        await _rutas(servidor).ordenar_paradas(origen=INICIO, paradas=[A, B], destino=LAB)


async def test_respuesta_con_otra_cantidad_de_puntos(servidor: str) -> None:
    RESPUESTA["cuerpo"] = {"coordenadas": [{"lat": -34.6, "lon": -58.4}]}
    with pytest.raises(ErrorRutasApi):
        await _rutas(servidor).ordenar_paradas(origen=INICIO, paradas=[A, B], destino=LAB)


async def test_si_la_api_falla_usa_el_orden_del_mock(servidor: str) -> None:
    RESPUESTA.update(status=500, cuerpo={"error": "x"})
    r = _rutas(servidor, respaldo=mock.OptimizacionRutasMock())
    orden = await r.ordenar_paradas(origen=INICIO, paradas=[A, B, C], destino=LAB)
    assert sorted(orden) == [1, 2, 3]


def test_exige_https() -> None:
    with pytest.raises(RuntimeError):
        RutasApi(Settings(rutas_api_url="http://x"))
