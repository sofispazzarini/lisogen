"""Adaptador HTTP de FedEx contra respuestas con el formato real de la API, sin red."""

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.config import Settings
from app.domain.errores import ErrorNegocio, NoEncontrado
from app.integrations.fedex import FedexHttp

BASE = "https://fedex.test/fedex"
RETIRO_ID = "6eaa59d9-a57d-4d4b-ab1f-60b9648eee3e"
CUANDO = datetime(2026, 11, 5, 18, 0, tzinfo=UTC)  # 15:00 en Argentina
CREADO = {
    "mensaje": "Retiro programado correctamente",
    "retiro": {
        "id": RETIRO_ID,
        "lugar": "La Plata, Buenos Aires",
        "fecha_programada": "2026-11-05T15:00:00-03:00",
        "url_seguimiento": f"{BASE}/retiros/{RETIRO_ID}",
    },
}


def _fedex(responder: Callable[[httpx.Request], httpx.Response]) -> FedexHttp:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        fedex_modo="api",
        fedex_api_url=f"{BASE}/",
        fedex_usuario="grupo",
        fedex_password="clave",
    )
    return FedexHttp(settings, transport=httpx.MockTransport(responder))


async def test_programar_envia_hora_argentina_sin_zona_y_basic_auth() -> None:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(201, json=CREADO)

    retiro = await _fedex(responder).programar_retiro(fecha_hora=CUANDO, lugar="La Plata, Buenos Aires")

    assert retiro.id == RETIRO_ID and retiro.url_seguimiento == f"{BASE}/retiros/{RETIRO_ID}"
    pedido = pedidos[0]
    assert pedido.method == "POST" and str(pedido.url) == f"{BASE}/retiros"
    assert json.loads(pedido.content) == {
        "lugar": "La Plata, Buenos Aires",
        "fecha_programada": "2026-11-05T15:00:00",
    }
    assert pedido.headers["authorization"] == "Basic " + base64.b64encode(b"grupo:clave").decode()


@pytest.mark.parametrize(
    ("status", "cuerpo", "code", "http"),
    [
        (400, {"error": "Datos inválidos"}, "FEDEX_RECHAZO", 422),
        (401, {"error": "Credenciales inválidas o faltantes"}, "FEDEX_NO_DISPONIBLE", 502),
        (500, {"error": "Error interno"}, "FEDEX_NO_DISPONIBLE", 502),
        (201, {"mensaje": "sin retiro"}, "FEDEX_NO_DISPONIBLE", 502),
        (201, {"retiro": {"id": RETIRO_ID, "url_seguimiento": "javascript:x"}}, "FEDEX_NO_DISPONIBLE", 502),
    ],
)
async def test_programar_traduce_errores(
    status: int, cuerpo: dict[str, object], code: str, http: int
) -> None:
    fedex = _fedex(lambda _: httpx.Response(status, json=cuerpo))
    with pytest.raises(ErrorNegocio) as e:
        await fedex.programar_retiro(fecha_hora=CUANDO, lugar="x")
    assert e.value.code == code and e.value.status == http


async def test_el_error_no_expone_las_credenciales() -> None:
    def caido(pedido: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=pedido)

    with pytest.raises(ErrorNegocio) as e:
        await _fedex(caido).programar_retiro(fecha_hora=CUANDO, lugar="x")
    assert e.value.code == "FEDEX_NO_DISPONIBLE" and "clave" not in e.value.message


@pytest.mark.parametrize("estado", ["PROGRAMADO", "RETIRADO"])
async def test_consultar_sin_auth(estado: str) -> None:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(200, json={"id": RETIRO_ID, "estado": estado})

    assert await _fedex(responder).consultar_retiro(retiro_id=RETIRO_ID) == estado
    assert str(pedidos[0].url) == f"{BASE}/retiros/{RETIRO_ID}"
    assert "authorization" not in pedidos[0].headers


async def test_consultar_inexistente() -> None:
    fedex = _fedex(lambda _: httpx.Response(404, json={"error": "No existe"}))
    with pytest.raises(NoEncontrado):
        await fedex.consultar_retiro(retiro_id=RETIRO_ID)


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.Response(500, json={"error": "x"}),
        httpx.Response(200, json={"estado": "OTRO"}),
        httpx.Response(200),
    ],
)
async def test_consultar_respuesta_invalida(respuesta: httpx.Response) -> None:
    with pytest.raises(ErrorNegocio) as e:
        await _fedex(lambda _: respuesta).consultar_retiro(retiro_id=RETIRO_ID)
    assert e.value.code == "FEDEX_NO_DISPONIBLE"


def test_modo_real_exige_configuracion_sin_mostrar_la_clave() -> None:
    with pytest.raises(ValueError, match="FEDEX_API_URL") as e:
        Settings(_env_file=None, fedex_modo="api", fedex_password="clave-secreta")  # type: ignore[call-arg]
    assert "clave-secreta" not in str(e.value)
