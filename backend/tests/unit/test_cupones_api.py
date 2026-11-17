"""Adaptador de la API de Cupones de Exoma Care, contra un servidor HTTP local que imita su contrato."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from app.config import Settings
from app.integrations.cupones_api import CuponesApi
from app.integrations.ports import ErrorCupones

PEDIDOS: list[dict[str, Any]] = []
RESPUESTA: dict[str, Any] = {"status": 200, "cuerpo": True}


class _Falso(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        PEDIDOS.append({"ruta": self.path, "cabeceras": dict(self.headers), "cuerpo": cuerpo})
        datos = json.dumps(RESPUESTA["cuerpo"]).encode()
        self.send_response(RESPUESTA["status"])
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)


@pytest.fixture
def servidor() -> Iterator[str]:
    PEDIDOS.clear()
    RESPUESTA.update(status=200, cuerpo=True)
    srv = HTTPServer(("127.0.0.1", 0), _Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _api(url: str) -> CuponesApi:
    api = CuponesApi(Settings(cupones_api_key="ecg_clave-secreta"))
    api._base = url  # el servidor local es http; el constructor exige https
    return api


async def test_generar_arma_el_pedido_y_devuelve_los_codigos(servidor: str) -> None:
    RESPUESTA["cuerpo"] = [
        {"codigo_cupon": "53399388", "porcentaje": 20},
        {"codigo_cupon": "2ded2dc3", "porcentaje": 20},
    ]
    cupones = await _api(servidor).generar(gerente_id=7, descuento_pct=20, cantidad=2)
    assert [c.codigo for c in cupones] == ["53399388", "2ded2dc3"]
    pedido = PEDIDOS[0]
    assert pedido["ruta"] == "/generar_cupones_gerencia"
    assert pedido["cabeceras"]["X-API-Key"] == "ecg_clave-secreta"
    assert "Authorization" not in pedido["cabeceras"]
    assert pedido["cuerpo"] == {"p_gerente_id": "7", "p_cantidad": 2, "p_porcentaje_descuento": 20}


async def test_asignar_a_medico(servidor: str) -> None:
    await _api(servidor).asignar_a_medico(gerente_id=7, medico_id=12, codigo="53399388")
    assert PEDIDOS[0]["ruta"] == "/asignar_cupon_a_medico"
    assert PEDIDOS[0]["cuerpo"] == {"p_gerente_id": "7", "p_medico_id": "12", "p_codigo": "53399388"}


async def test_asignar_a_paciente(servidor: str) -> None:
    await _api(servidor).asignar_a_paciente(medico_id=12, paciente_id=3, codigo="53399388")
    assert PEDIDOS[0]["ruta"] == "/asignar_cupon_a_paciente"
    assert PEDIDOS[0]["cuerpo"] == {"p_medico_id": "12", "p_paciente_id": "3", "p_codigo": "53399388"}


async def test_canjear(servidor: str) -> None:
    await _api(servidor).canjear(paciente_id=3, codigo="53399388")
    assert PEDIDOS[0]["ruta"] == "/canjear_cupon"
    assert PEDIDOS[0]["cuerpo"] == {"p_paciente_id": "3", "p_codigo": "53399388"}


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 413, 415])
async def test_rechazos_de_negocio_no_son_inciertos(servidor: str, status: int) -> None:
    RESPUESTA.update(status=status, cuerpo={"code": "X", "message": "no"})
    with pytest.raises(ErrorCupones) as e:
        await _api(servidor).canjear(paciente_id=3, codigo="53399388")
    assert e.value.status == status and not e.value.incierto


@pytest.mark.parametrize("status", [500, 503])
async def test_error_del_servidor_es_incierto(servidor: str, status: int) -> None:
    RESPUESTA.update(status=status, cuerpo={"message": "caído"})
    with pytest.raises(ErrorCupones) as e:
        await _api(servidor).canjear(paciente_id=3, codigo="53399388")
    assert e.value.status == status and e.value.incierto


async def test_sin_conexion_es_incierto() -> None:
    with pytest.raises(ErrorCupones) as e:
        await _api("http://127.0.0.1:9").canjear(paciente_id=3, codigo="53399388")
    assert e.value.incierto and e.value.status == 0


async def test_respuesta_que_no_confirma_es_error(servidor: str) -> None:
    RESPUESTA["cuerpo"] = False
    with pytest.raises(ErrorCupones):
        await _api(servidor).canjear(paciente_id=3, codigo="53399388")


@pytest.mark.parametrize(
    "lote",
    [[], [{"codigo_cupon": "aa"}], [{"codigo_cupon": ""}, {"codigo_cupon": "bb"}], "no es lista"],
)
async def test_lote_que_no_coincide_con_lo_pedido_es_error(servidor: str, lote: Any) -> None:
    RESPUESTA["cuerpo"] = lote
    with pytest.raises(ErrorCupones):
        await _api(servidor).generar(gerente_id=7, descuento_pct=20, cantidad=2)


def test_exige_clave_y_https() -> None:
    with pytest.raises(RuntimeError, match="CUPONES_API_KEY"):
        CuponesApi(Settings(cupones_api_key=""))
    with pytest.raises(RuntimeError, match="https"):
        CuponesApi(Settings(cupones_api_key="ecg_x", cupones_api_url="http://x"))
