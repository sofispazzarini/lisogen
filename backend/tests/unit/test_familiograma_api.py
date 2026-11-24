"""Adaptador de la API de familiograma contra un servidor HTTP local que imita su contrato."""

import base64
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from app.config import Settings
from app.integrations.familiograma_api import FamiliogramaApi
from app.integrations.ports import Advertencia, ErrorFamiliograma, ParentescoCatalogo, PersonaFamiliograma
from app.integrations.svg import SvgInvalido, sanear

CLAVE = "clave-de-prueba"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><circle r="4"/></svg>'
PERSONAS = [
    PersonaFamiliograma(0, "Lucía", "Rivas", edad=34.0),
    PersonaFamiliograma(1, "Marta", "Rivas", "mujer"),
]

PEDIDOS: list[dict[str, Any]] = []
RESPUESTAS: list[tuple[int, Any]] = []  # una por pedido; la última se repite


def _imagen_ok(svg: bytes = SVG, advertencias: list[dict[str, str]] | None = None) -> tuple[int, Any]:
    return 200, {
        "advertencias": advertencias or [],
        "imagen": {"tipo": "image/svg+xml", "base64": base64.b64encode(svg).decode()},
    }


def _error(status: int, codigo: str, detalles: list[dict[str, str]] | None = None) -> tuple[int, Any]:
    return status, {"error": {"codigo": codigo, "mensaje": "rechazado", "detalles": detalles or []}}


class _Falso(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def _responder(self) -> None:
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo) if largo else b""
        PEDIDOS.append(
            {
                "metodo": self.command,
                "ruta": self.path,
                "cabeceras": {k.lower(): v for k, v in self.headers.items()},
                "cuerpo": json.loads(cuerpo) if cuerpo else None,
            }
        )
        status, datos = RESPUESTAS.pop(0) if len(RESPUESTAS) > 1 else RESPUESTAS[0]
        crudo = datos if isinstance(datos, bytes) else json.dumps(datos).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    do_GET = _responder
    do_POST = _responder


@pytest.fixture
def servidor() -> Iterator[str]:
    PEDIDOS.clear()
    RESPUESTAS[:] = [_imagen_ok()]
    srv = HTTPServer(("127.0.0.1", 0), _Falso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/functions/v1/familiograma"
    srv.shutdown()


def _api(url: str) -> FamiliogramaApi:
    api = FamiliogramaApi(Settings(familiograma_api_key=CLAVE))
    api._base = url  # el servidor local es http; el constructor exige https
    api.backoff_seg = 0
    return api


def test_exige_clave_y_https() -> None:
    with pytest.raises(RuntimeError, match="FAMILIOGRAMA_API_KEY"):
        FamiliogramaApi(Settings(familiograma_api_key=""))
    with pytest.raises(RuntimeError, match="https"):
        FamiliogramaApi(Settings(familiograma_api_key=CLAVE, familiograma_api_url="http://x"))


async def test_post_con_headers_y_body(servidor: str) -> None:
    imagen = await _api(servidor).generar(personas=PERSONAS)
    pedido = PEDIDOS[0]
    assert (pedido["metodo"], pedido["ruta"]) == ("POST", "/functions/v1/familiograma")
    assert pedido["cabeceras"]["x-api-key"] == CLAVE
    assert pedido["cabeceras"]["content-type"] == "application/json"
    assert pedido["cuerpo"] == {
        "personas": [
            {
                "parentesco": 0,
                "nombre": "Lucía",
                "apellido": "Rivas",
                "sexo": "no_identificado",
                "fallecido": False,
                "sintomas": [],
                "diagnosticos": [],
                "edad": 34.0,
            },
            {
                "parentesco": 1,
                "nombre": "Marta",
                "apellido": "Rivas",
                "sexo": "mujer",
                "fallecido": False,
                "sintomas": [],
                "diagnosticos": [],
            },
        ],
        "opciones": {"reglaSospecha": "desactivada"},
    }
    assert imagen.mime == "image/svg+xml" and imagen.advertencias == ()
    assert b"<circle" in imagen.contenido


async def test_decodifica_el_base64_de_la_imagen_y_devuelve_las_advertencias(servidor: str) -> None:
    aviso = {"codigo": "EVALUACION_SINTOMAS_NO_DISPONIBLE", "mensaje": "sin evaluador"}
    RESPUESTAS[:] = [_imagen_ok(advertencias=[aviso])]
    imagen = await _api(servidor).generar(personas=PERSONAS, regla_sospecha="un_cardinal_o_dos_secundarios")
    assert PEDIDOS[0]["cuerpo"]["opciones"] == {"reglaSospecha": "un_cardinal_o_dos_secundarios"}
    assert imagen.advertencias == (Advertencia(**aviso),)
    # El SVG guardado equivale al que viajó en base64 (el data URI de la API: data:<tipo>;base64,<base64>)
    assert sanear(SVG) == imagen.contenido


async def test_no_llama_si_no_hay_exactamente_un_paciente(servidor: str) -> None:
    from app.integrations.familiograma_mapeo import ErrorMapeo

    with pytest.raises(ErrorMapeo):
        await _api(servidor).generar(personas=[PersonaFamiliograma(1, "Marta", "Rivas")])
    assert PEDIDOS == []


@pytest.mark.parametrize(
    ("status", "codigo"),
    [
        (400, "JSON_INVALIDO"),
        (401, "NO_AUTORIZADO"),
        (413, "ENTRADA_DEMASIADO_GRANDE"),
        (415, "TIPO_NO_ADMITIDO"),
    ],
)
async def test_4xx_no_se_reintenta(servidor: str, status: int, codigo: str) -> None:
    RESPUESTAS[:] = [_error(status, codigo)]
    with pytest.raises(ErrorFamiliograma) as e:
        await _api(servidor).generar(personas=PERSONAS)
    assert (e.value.status, e.value.codigo) == (status, codigo)
    assert len(PEDIDOS) == 1
    assert CLAVE not in str(e.value) and "Lucía" not in str(e.value)


async def test_422_trae_los_detalles(servidor: str) -> None:
    detalle = {"ruta": "personas.1.parentesco", "mensaje": "FALTA_PERSONA_DE_REFERENCIA: falta el progenitor"}
    RESPUESTAS[:] = [_error(422, "DATOS_INVALIDOS", [detalle])]
    with pytest.raises(ErrorFamiliograma) as e:
        await _api(servidor).generar(personas=PERSONAS)
    assert e.value.status == 422 and len(PEDIDOS) == 1
    assert [(d.ruta, d.mensaje) for d in e.value.detalles] == [(detalle["ruta"], detalle["mensaje"])]
    assert "falta el progenitor" not in str(e.value)  # el texto de la API no va al mensaje de la excepción


@pytest.mark.parametrize("status", [500, 502])
async def test_5xx_se_reintenta_una_vez(servidor: str, status: int) -> None:
    RESPUESTAS[:] = [_error(status, "ERROR_INTERNO"), _imagen_ok()]
    imagen = await _api(servidor).generar(personas=PERSONAS)
    assert len(PEDIDOS) == 2 and b"<circle" in imagen.contenido


async def test_5xx_dos_veces_falla(servidor: str) -> None:
    RESPUESTAS[:] = [_error(502, "EVALUADOR_NO_DISPONIBLE")]
    with pytest.raises(ErrorFamiliograma) as e:
        await _api(servidor).generar(personas=PERSONAS)
    assert e.value.status == 502 and len(PEDIDOS) == 2


async def test_sin_respuesta() -> None:
    api = _api("http://127.0.0.1:9/functions/v1/familiograma")  # puerto cerrado
    with pytest.raises(ErrorFamiliograma) as e:
        await api.generar(personas=PERSONAS)
    assert e.value.status == 0


@pytest.mark.parametrize(
    "datos",
    [
        {"advertencias": [], "imagen": {"tipo": "image/png", "base64": "AAAA"}},
        {"advertencias": [], "imagen": {"tipo": "image/svg+xml", "base64": "no es base64!"}},
        {
            "advertencias": [],
            "imagen": {"tipo": "image/svg+xml", "base64": base64.b64encode(b"<html/>").decode()},
        },
        b"no es json",
    ],
)
async def test_respuesta_que_no_se_entiende(servidor: str, datos: Any) -> None:
    RESPUESTAS[:] = [(200, datos)]
    with pytest.raises(ErrorFamiliograma):
        await _api(servidor).generar(personas=PERSONAS)


async def test_parentescos_se_cachean(servidor: str) -> None:
    RESPUESTAS[:] = [(200, [{"id": 0, "parentesco": "paciente"}, {"id": 1, "parentesco": "progenitor"}])]
    api = _api(servidor)
    assert await api.parentescos() == [ParentescoCatalogo(0, "paciente"), ParentescoCatalogo(1, "progenitor")]
    assert await api.parentescos() == await api.parentescos()
    assert len(PEDIDOS) == 1
    assert (PEDIDOS[0]["metodo"], PEDIDOS[0]["ruta"]) == ("GET", "/functions/v1/familiograma/parentescos")
    assert PEDIDOS[0]["cabeceras"]["x-api-key"] == CLAVE
    assert "content-type" not in PEDIDOS[0]["cabeceras"]


# --- Saneado del SVG ----------------------------------------------------------------------------


def test_sanear_quita_contenido_activo() -> None:
    sucio = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" onload="x()">'
        b"<script>alert(1)</script>"
        b'<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">hola</div></foreignObject>'
        b'<a href="javascript:alert(1)"><text onclick="x()">Ana</text></a>'
        b'<use xlink:href="https://otro.sitio/x.svg#a"/><use href="#simbolo"/>'
        b"<style>@import url(https://otro.sitio/a.css);</style>"
        b'<rect style="fill:url(#rayado)"/>'
        b"</svg>"
    )
    limpio = sanear(sucio).decode()
    for prohibido in ("script", "foreignObject", "onload", "onclick", "javascript:", "otro.sitio", "@import"):
        assert prohibido not in limpio
    assert 'href="#simbolo"' in limpio and "url(#rayado)" in limpio and ">Ana</text>" in limpio


@pytest.mark.parametrize(
    "contenido",
    [
        b'<!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>',
        b"<svg",
        b"<html/>",
    ],
)
def test_sanear_rechaza(contenido: bytes) -> None:
    with pytest.raises(SvgInvalido):
        sanear(contenido)
