"""Adaptador del Chatbot de GenLab, contra un servidor HTTP local que imita su contrato."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from app.config import Settings
from app.integrations.chatbot_api import ChatbotApi
from app.integrations.ports import ErrorChatbot

PEDIDOS: list[dict[str, Any]] = []
# Respuestas que da el servidor, en orden; la última se repite
RESPUESTAS: list[dict[str, Any]] = []


class _Falso(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        PEDIDOS.append({"cabeceras": dict(self.headers), "cuerpo": cuerpo})
        r = RESPUESTAS[min(len(PEDIDOS), len(RESPUESTAS)) - 1]
        datos = r["cuerpo"] if isinstance(r["cuerpo"], bytes) else json.dumps(r["cuerpo"]).encode()
        self.send_response(r["status"])
        for k, v in r.get("cabeceras", {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)


def _ok(**extra: Any) -> dict[str, Any]:
    return {
        "status": 200,
        "cuerpo": {"respuesta": "El exoma es...", "conversacion_id": "c-1", "tipo": "respuesta", **extra},
    }


@pytest.fixture
def servidor() -> Iterator[str]:
    PEDIDOS.clear()
    RESPUESTAS[:] = [_ok()]
    srv = HTTPServer(("127.0.0.1", 0), _Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _api(url: str) -> tuple[ChatbotApi, list[float]]:
    api = ChatbotApi(Settings(chatbot_apikey="sb_publishable_x", chatbot_token="token-secreto"))
    api._url = url  # el servidor local es http; el constructor exige https
    esperas: list[float] = []
    api._dormir = esperas.append
    return api, esperas


async def test_arma_el_pedido_y_devuelve_la_respuesta(servidor: str) -> None:
    api, _ = _api(servidor)
    r = await api.responder(pregunta="¿Qué es un exoma clínico?")
    assert (r.respuesta, r.conversacion_id, r.tipo) == ("El exoma es...", "c-1", "respuesta")
    pedido = PEDIDOS[0]
    assert pedido["cabeceras"]["apikey"] == "sb_publishable_x"
    assert pedido["cabeceras"]["x-chatbot-token"] == "token-secreto"
    assert pedido["cuerpo"] == {"mensaje": "¿Qué es un exoma clínico?", "conversacion_id": None}


async def test_manda_la_conversacion_anterior(servidor: str) -> None:
    api, _ = _api(servidor)
    await api.responder(pregunta="¿y cómo se hereda?", conversacion_id="c-1")
    assert PEDIDOS[0]["cuerpo"]["conversacion_id"] == "c-1"


@pytest.mark.parametrize("tipo", ["fuera_de_alcance", "derivar_medico", "sin_informacion"])
async def test_los_cuatro_tipos_se_devuelven_tal_cual(servidor: str, tipo: str) -> None:
    RESPUESTAS[:] = [_ok(tipo=tipo, respuesta="Texto del servicio.")]
    r = await _api(servidor)[0].responder(pregunta="Hola")
    assert (r.tipo, r.respuesta) == (tipo, "Texto del servicio.")


async def test_429_espera_retry_after_y_reintenta_una_vez(servidor: str) -> None:
    RESPUESTAS[:] = [
        {"status": 429, "cuerpo": {"detail": "límite"}, "cabeceras": {"Retry-After": "3"}},
        _ok(),
    ]
    api, esperas = _api(servidor)
    r = await api.responder(pregunta="Hola")
    assert r.respuesta == "El exoma es..." and esperas == [3] and len(PEDIDOS) == 2


async def test_429_dos_veces_no_reintenta_en_bucle(servidor: str) -> None:
    RESPUESTAS[:] = [{"status": 429, "cuerpo": {"detail": "límite"}, "cabeceras": {"Retry-After": "99"}}]
    api, esperas = _api(servidor)
    with pytest.raises(ErrorChatbot) as e:
        await api.responder(pregunta="Hola")
    assert e.value.status == 429 and e.value.reintentar_en == 10  # tope de espera
    assert esperas == [10] and len(PEDIDOS) == 2


async def test_429_sin_retry_after_usa_el_valor_por_defecto(servidor: str) -> None:
    RESPUESTAS[:] = [{"status": 429, "cuerpo": {"detail": "límite"}}, _ok()]
    api, esperas = _api(servidor)
    await api.responder(pregunta="Hola")
    assert esperas == [5]


async def test_503_informa_el_detalle_y_no_reintenta(servidor: str) -> None:
    RESPUESTAS[:] = [{"status": 503, "cuerpo": {"detail": "Chatbot apagado por el momento."}}]
    with pytest.raises(ErrorChatbot) as e:
        await _api(servidor)[0].responder(pregunta="Hola")
    assert e.value.status == 503 and e.value.detalle == "Chatbot apagado por el momento."
    assert len(PEDIDOS) == 1


@pytest.mark.parametrize("status", [401, 405, 500])
async def test_otros_errores_no_se_reintentan(servidor: str, status: int) -> None:
    RESPUESTAS[:] = [{"status": status, "cuerpo": {"detail": "x"}}]
    with pytest.raises(ErrorChatbot) as e:
        await _api(servidor)[0].responder(pregunta="Hola")
    assert e.value.status == status and len(PEDIDOS) == 1


async def test_422_no_expone_la_lista_de_errores(servidor: str) -> None:
    RESPUESTAS[:] = [{"status": 422, "cuerpo": {"detail": [{"loc": ["mensaje"], "msg": "vacío"}]}}]
    with pytest.raises(ErrorChatbot) as e:
        await _api(servidor)[0].responder(pregunta="Hola")
    assert e.value.status == 422 and e.value.detalle == ""


@pytest.mark.parametrize(
    "cuerpo", [b"no es json", {"conversacion_id": "c-1"}, {"respuesta": "   "}, {"respuesta": 3}, []]
)
async def test_respuesta_mal_formada(servidor: str, cuerpo: Any) -> None:
    RESPUESTAS[:] = [{"status": 200, "cuerpo": cuerpo}]
    with pytest.raises(ErrorChatbot):
        await _api(servidor)[0].responder(pregunta="Hola")


async def test_sin_conexion_es_un_error_del_chatbot() -> None:
    api, _ = _api("http://127.0.0.1:1")  # puerto cerrado
    with pytest.raises(ErrorChatbot) as e:
        await api.responder(pregunta="Hola")
    assert e.value.status == 0


def test_exige_apikey_token_y_https() -> None:
    with pytest.raises(RuntimeError, match="CHATBOT_APIKEY"):
        ChatbotApi(Settings(chatbot_apikey="", chatbot_token="t"))
    with pytest.raises(RuntimeError, match="CHATBOT_APIKEY"):
        ChatbotApi(Settings(chatbot_apikey="k", chatbot_token=""))
    with pytest.raises(RuntimeError, match="https"):
        ChatbotApi(Settings(chatbot_apikey="k", chatbot_token="t", chatbot_url="http://x"))
