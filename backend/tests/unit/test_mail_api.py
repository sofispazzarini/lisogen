"""Adaptador de la API de Notificaciones por Email, contra un servidor HTTP local que imita su contrato."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from app.config import Settings
from app.integrations.mail_api import ErrorMailApi, MailApi

AVISO = "696a0cfc-4925-4ee1-8426-41eb5040a0ea"
PEDIDOS: list[dict[str, Any]] = []
RESPUESTA: dict[str, Any] = {"status": 202, "cuerpo": {"id": AVISO}}


class _Falso(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def _responder(self) -> None:
        datos = json.dumps(RESPUESTA["cuerpo"]).encode()
        self.send_response(RESPUESTA["status"])
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def do_POST(self) -> None:
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        PEDIDOS.append({"ruta": self.path, "cabeceras": dict(self.headers), "cuerpo": cuerpo})
        self._responder()

    def do_GET(self) -> None:
        PEDIDOS.append({"ruta": self.path, "cabeceras": dict(self.headers), "cuerpo": None})
        self._responder()


@pytest.fixture
def servidor() -> Iterator[str]:
    PEDIDOS.clear()
    RESPUESTA.update(status=202, cuerpo={"id": AVISO})
    srv = HTTPServer(("127.0.0.1", 0), _Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _mail(url: str) -> MailApi:
    m = MailApi(Settings(mail_api_url="https://x", mail_api_key="clave-secreta"))
    m._base = url  # el servidor local es http; el constructor exige https
    return m


async def test_enviar_arma_el_aviso_con_clave_de_idempotencia(servidor: str) -> None:
    await _mail(servidor).enviar(
        destinatario="paciente@correo.com", asunto="Hola", cuerpo="Texto", clave="lisogen-notif-7"
    )
    pedido = PEDIDOS[0]
    assert pedido["ruta"] == "/avisos"
    assert pedido["cabeceras"]["X-API-Key"] == "clave-secreta"
    assert pedido["cabeceras"]["Idempotency-Key"] == "lisogen-notif-7"
    assert pedido["cuerpo"] == {
        "asunto": "Hola",
        "mensaje": "Texto",
        "referencia": "lisogen-notif-7",
        "destinatarios": [{"canal": "email", "destino": "paciente@correo.com"}],
    }


async def test_enviar_devuelve_el_id_del_aviso(servidor: str) -> None:
    aviso = await _mail(servidor).enviar(destinatario="a@b.com", asunto="x", cuerpo="y")
    assert aviso == AVISO


async def test_estado_consulta_el_aviso_por_id(servidor: str) -> None:
    RESPUESTA.update(status=200, cuerpo={"id": AVISO, "estado": "parcial", "envios": []})
    r = await _mail(servidor).estado(AVISO)
    assert r["estado"] == "parcial"
    assert PEDIDOS[0]["ruta"] == f"/avisos/{AVISO}"
    assert PEDIDOS[0]["cabeceras"]["X-API-Key"] == "clave-secreta"


async def test_estado_rechaza_un_id_que_no_es_uuid(servidor: str) -> None:
    with pytest.raises(ValueError):
        await _mail(servidor).estado("../avisos")
    assert PEDIDOS == []


async def test_pendientes_lista_los_avisos_sin_terminar(servidor: str) -> None:
    RESPUESTA.update(status=200, cuerpo={"total": 1, "avisos": [{"id": 5, "envios_pendientes": 1}]})
    avisos = await _mail(servidor).pendientes(limite=500)
    assert avisos == [{"id": 5, "envios_pendientes": 1}]
    assert PEDIDOS[0]["ruta"] == "/avisos/pendientes?limite=100"  # el máximo de la API es 100
    assert PEDIDOS[0]["cabeceras"]["X-API-Key"] == "clave-secreta"


@pytest.mark.parametrize("status", [400, 409, 413, 415])
async def test_error_de_datos_es_permanente(servidor: str, status: int) -> None:
    RESPUESTA.update(status=status, cuerpo={"error": "dato inválido"})
    with pytest.raises(ErrorMailApi, match="dato inválido") as e:
        await _mail(servidor).enviar(destinatario="a@b.com", asunto="x", cuerpo="y")
    assert e.value.permanente


@pytest.mark.parametrize("status", [401, 500, 503])
async def test_otros_errores_se_pueden_reintentar(servidor: str, status: int) -> None:
    RESPUESTA.update(status=status, cuerpo={"error": "x"})
    with pytest.raises(ErrorMailApi, match=str(status)) as e:
        await _mail(servidor).pendientes()
    assert not e.value.permanente


async def test_sin_conexion_es_error_reintentable() -> None:
    m = MailApi(Settings(mail_api_url="https://x", mail_api_key="k"))
    m._base = "http://127.0.0.1:1"  # puerto cerrado
    with pytest.raises(ErrorMailApi, match="sin respuesta") as e:
        await m.pendientes()
    assert not e.value.permanente


def test_exige_https_y_clave() -> None:
    with pytest.raises(RuntimeError):
        MailApi(Settings(mail_api_url="http://x", mail_api_key="k"))
    with pytest.raises(RuntimeError):
        MailApi(Settings(mail_api_url="", mail_api_key=""))
