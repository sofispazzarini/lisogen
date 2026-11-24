"""Contrato HTTP del catálogo de Apigen, sin depender del servicio externo."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from app.config import Settings
from app.integrations.apigen_api import ApigenApi, ApigenNoDisponible
from app.integrations.ports import VarianteExterna


@pytest.fixture
def servidor() -> Iterator[tuple[ApigenApi, list[dict[str, Any]], list[tuple[int, Any]]]]:
    pedidos: list[dict[str, Any]] = []
    respuestas: list[tuple[int, Any]] = []

    class Falso(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def _responder(self) -> None:
            url = urlsplit(self.path)
            longitud = int(self.headers.get("Content-Length", 0))
            pedidos.append(
                {
                    "metodo": self.command,
                    "ruta": url.path,
                    "query": parse_qs(url.query),
                    "apikey": self.headers.get("apikey"),
                    "cuerpo": json.loads(self.rfile.read(longitud)) if longitud else None,
                }
            )
            status, cuerpo = respuestas.pop(0)
            datos = json.dumps(cuerpo).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        do_GET = _responder
        do_POST = _responder

    api = ApigenApi(Settings(apigen_api_key="clave-prueba"))
    with HTTPServer(("127.0.0.1", 0), Falso) as srv:
        hilo = threading.Thread(target=srv.serve_forever, daemon=True)
        hilo.start()
        try:
            api._url = f"http://127.0.0.1:{srv.server_port}/rest/v1"
            yield api, pedidos, respuestas
        finally:
            srv.shutdown()
            hilo.join()


async def test_genes_por_patologia_y_hallazgos(servidor) -> None:
    api, pedidos, respuestas = servidor
    respuestas.extend([(200, ["IDUA"]), (200, [{"gen": "BRCA1"}, {"gen": "BRCA2"}])])
    assert await api.genes_por_patologia(patologia="MPS 1") == ["IDUA"]
    assert await api.genes_hallazgos_secundarios() == ["BRCA1", "BRCA2"]
    assert await api.genes_por_patologia(patologia="Patología local") == []
    assert pedidos == [
        {
            "metodo": "POST",
            "ruta": "/rest/v1/rpc/genes_por_patologia",
            "query": {},
            "apikey": "clave-prueba",
            "cuerpo": {"p_patologia": "MPS1"},
        },
        {
            "metodo": "GET",
            "ruta": "/rest/v1/genes_hallazgos_secundarios",
            "query": {"select": ["gen"]},
            "apikey": "clave-prueba",
            "cuerpo": None,
        },
    ]


async def test_busqueda_literal_paginada_y_reintento(servidor) -> None:
    api, pedidos, respuestas = servidor
    fila = {"id": "GLA:c.*2_3del", "hgvs_c": "c.*2_3del"}
    respuestas.extend([(200, [fila]), (503, {}), (200, [])])
    assert await api.variantes_por_gen(gen="GLA", texto="c.*2_3", limite=1) == [
        VarianteExterna("c.*2_3del", "GLA:c.*2_3del")
    ]
    with pytest.raises(ApigenNoDisponible):
        await api.variantes_por_gen(gen="GLA", texto="c.*2_3", limite=1, offset=1)
    assert await api.variantes_por_gen(gen="GLA", texto="c.*2_3", limite=1, offset=1) == []
    assert pedidos[0]["query"] == {
        "gen": ["eq.GLA"],
        "select": ["id,hgvs_c"],
        "order": ["id"],
        "limit": ["1"],
        "offset": ["0"],
        "hgvs_c": [r"imatch.c\.\*2_3"],
    }
    assert pedidos[1]["query"]["offset"] == ["1"]
    assert pedidos[1] == pedidos[2]


async def test_validacion_exacta_distingue_vacio_de_error(servidor) -> None:
    api, pedidos, respuestas = servidor
    fila = {"id": "GAA:c.-32-13T>G", "hgvs_c": "c.-32-13T>G"}
    respuestas.extend([(200, [fila]), (200, []), (200, [{"id": "incompleta"}])])
    assert await api.variante_exacta(gen="GAA", nomenclatura="c.-32-13T>G") == VarianteExterna(
        "c.-32-13T>G", "GAA:c.-32-13T>G"
    )
    assert pedidos[0]["query"]["hgvs_c"] == ["eq.c.-32-13T>G"]
    assert await api.variante_exacta(gen="GAA", nomenclatura="c.1A>T") is None
    with pytest.raises(ApigenNoDisponible):
        await api.variante_exacta(gen="GAA", nomenclatura="c.-32-13T>G")
