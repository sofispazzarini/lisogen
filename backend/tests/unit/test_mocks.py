"""Adaptadores mock determinísticos de las integraciones externas, generador de PDF y saneamiento del
`integracion_log` (sin datos personales)."""

import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.integrations import mock
from app.integrations.infra import MailMemoria, StorageMemoria
from app.integrations.pdf import es_pdf, generar_pdf
from app.integrations.ports import FamiliarExterno, Parada, Punto
from app.integrations.registro import CAMPOS_SENSIBLES, _resumir

# --- Bioinformática ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("patologia", "genes"),
    [
        ("Fabry", ["GLA"]),
        ("Pompe", ["GAA"]),
        ("MPS 1", ["IDUA"]),
        ("Gaucher", ["GBA1"]),
        ("ASMD", ["SMPD1"]),
        ("fábry", ["GLA"]),
        ("Desconocida", []),
    ],
)
async def test_genes_por_patologia(patologia: str, genes: list[str]) -> None:
    assert await mock.BioinformaticaMock().genes_por_patologia(patologia=patologia) == genes


async def test_genes_de_hallazgos_secundarios() -> None:
    assert await mock.BioinformaticaMock().genes_hallazgos_secundarios() == [
        "BRCA1",
        "BRCA2",
        "MLH1",
        "LDLR",
        "MYBPC3",
    ]


@pytest.mark.parametrize("gen", ["GLA", "GAA", "BRCA1", "TP53", "ttn"])
async def test_variantes_deterministicas_y_validas(gen: str) -> None:
    api = mock.BioinformaticaMock()
    primera = await api.variantes_por_gen(gen=gen)
    assert primera == await api.variantes_por_gen(gen=gen)
    assert len({v.nomenclatura for v in primera}) == len(primera) >= 2
    for v in primera:
        m = re.fullmatch(r"c\.\d+([ACGT])>([ACGT])", v.nomenclatura)
        if m:
            assert m.group(1) != m.group(2)  # sin variantes "A>A"
    if gen.upper() in mock.VARIANTES_CONOCIDAS:
        assert primera[0].nomenclatura == mock.VARIANTES_CONOCIDAS[gen.upper()]


# --- Obras sociales, familiograma, Ministerio, FedEx -------------------------------------------


@pytest.mark.parametrize(("codigo", "pct"), [("OSPS", 100), ("andina", 70), ("FEDERAL", 50), ("OTRA", 0)])
async def test_cobertura(codigo: str, pct: int) -> None:
    assert await mock.ObrasSocialesMock().cobertura(codigo_obra_social=codigo, cantidad_genes=3) == Decimal(
        pct
    )


async def test_familiograma_pdf() -> None:
    pdf = await mock.FamiliogramaMock().generar(
        familiares=[
            FamiliarExterno("MADRE", "Marta", "Dolor de manos", "Fabry"),
            FamiliarExterno("TIO", "Juan", None, None),
        ]
    )
    assert es_pdf(pdf) and b"Marta" in pdf and b"riesgo aumentado" in pdf


async def test_ministerio_devuelve_autorizacion_estable() -> None:
    csv = b"lote,estudio\nL1,E1\nL1,E2\n"
    a = await mock.MinisterioSaludMock().autorizar_lote(codigo_lote="LOTE-2026-000001", csv=csv)
    assert a == await mock.MinisterioSaludMock().autorizar_lote(codigo_lote="LOTE-2026-000001", csv=csv)
    assert es_pdf(a) and b"Muestras declaradas: 2" in a


async def test_fedex_tracking_determinístico() -> None:
    cuando = datetime(2026, 10, 26, 13, 0, tzinfo=UTC)
    t1 = await mock.FedexMock().programar_retiro(fecha_hora=cuando, url_lote="https://x/1")
    assert t1 == await mock.FedexMock().programar_retiro(fecha_hora=cuando, url_lote="https://x/1")
    assert t1 != await mock.FedexMock().programar_retiro(fecha_hora=cuando, url_lote="https://x/2")
    assert re.fullmatch(r"FDX\d{12}", t1)


# --- Cupones ----------------------------------------------------------------------------------


async def test_cupones_con_qr_y_lectura_del_pdf() -> None:
    api = mock.CuponesMock()
    cupones = await api.generar(descuento_pct=15, cantidad=3)
    assert len({c.codigo for c in cupones}) == 3
    for c in cupones:
        assert re.fullmatch(r"LG15-[0-9A-F]{8}", c.codigo) and c.qr_pdf is not None
        assert mock.leer_codigo_de_pdf_cupon(c.qr_pdf) == c.codigo
        assert await api.validar(codigo=c.codigo)
    assert mock.leer_codigo_de_pdf_cupon(generar_pdf("Otro", ["sin código"])) is None


async def test_cupones_sin_qr_usan_codigo_numerico() -> None:
    cupones = await mock.CuponesMock(sin_qr=True).generar(descuento_pct=10, cantidad=2)
    assert all(c.qr_pdf is None and re.fullmatch(r"\d{10}", c.codigo) for c in cupones)
    assert await mock.CuponesMock().validar(codigo=cupones[0].codigo)
    assert not await mock.CuponesMock().validar(codigo="CUALQUIERA")


# --- Optimización de recorridos ---------------------------------------------------------------


async def test_rutas_vecino_mas_cercano() -> None:
    origen = Punto(Decimal(0), Decimal(0))
    paradas = [
        Parada(3, Punto(Decimal(5), Decimal(0))),
        Parada(1, Punto(Decimal(1), Decimal(0))),
        Parada(2, Punto(Decimal(2), Decimal(0))),
        Parada(4, Punto(Decimal(-1), Decimal(0))),
    ]
    orden = await mock.OptimizacionRutasMock().ordenar_paradas(origen=origen, paradas=paradas)
    # Desde 0: 1 y 4 empatan (gana el id menor); desde 2: 3 y 4 empatan (gana 3)
    assert orden == [1, 2, 3, 4]
    assert orden == await mock.OptimizacionRutasMock().ordenar_paradas(
        origen=origen, paradas=list(reversed(paradas))
    )
    assert await mock.OptimizacionRutasMock().ordenar_paradas(origen=origen, paradas=[]) == []


# --- Chatbot ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pregunta", "esperado"),
    [
        ("¿Qué es Fabry?", "GLA"),
        ("pompe en bebés", "GAA"),
        ("Tengo dudas sobre la mucopolisacaridosis", "IDUA"),
        ("¿Qué es GAUCHER?", "GBA1"),
        ("Niemann-Pick", "SMPD1"),
        ("¿Cuándo saco turno?", "15 minutos"),
    ],
)
async def test_chatbot_responde_sobre_las_patologias(pregunta: str, esperado: str) -> None:
    respuesta = await mock.ChatbotMock().responder(pregunta=pregunta)
    assert esperado in respuesta
    assert "no reemplaza la consulta con tu Médico Tratante" in respuesta


async def test_chatbot_no_deriva_a_una_persona() -> None:
    respuesta = await mock.ChatbotMock().responder(pregunta="Pasame con un humano")
    assert "Fabry, Pompe, MPS 1, Gaucher y ASMD" in respuesta
    assert "derivo" not in respuesta.lower() and "operador" not in respuesta.lower()


# --- Infra en memoria y PDF -------------------------------------------------------------------


async def test_mail_y_storage_en_memoria() -> None:
    mail, storage = MailMemoria(), StorageMemoria()
    await mail.enviar(destinatario="a@b.com", asunto="Hola", cuerpo="Texto")
    assert mail.enviados[0].asunto == "Hola"
    await storage.guardar(clave="x/1", contenido=b"datos", mime="text/plain")
    assert await storage.leer(clave="x/1") == b"datos"
    assert (await storage.url_firmada(clave="x/1", nombre_descarga="informe final.pdf")).startswith(
        "memoria://x/1"
    )


def test_pdf_multipagina_con_acentos_y_parentesis() -> None:
    pdf = generar_pdf("Informe (prueba)", [f"Línea {i}: señal (ñ) á é í ó ú" for i in range(120)])
    assert es_pdf(pdf) and pdf.rstrip().endswith(b"%%EOF")
    assert pdf.count(b"/Type /Page ") == 3
    assert b"\\(prueba\\)" in pdf
    assert "ñ".encode("cp1252") in pdf


# --- integracion_log sin datos personales -----------------------------------------------------


def test_resumir_omite_datos_sensibles() -> None:
    entrada = {
        "destinatario": "paciente@test.com",
        "asunto": "Credenciales",
        "cuerpo": "Contraseña provisoria: X",
        "pregunta": "Tengo Fabry",
        "csv": b"dni,nombre\n1,Juan",
        "codigo_lote": "LOTE-1",
        "cobertura": Decimal("70.5"),
        "fecha_hora": datetime(2026, 10, 26, tzinfo=UTC),
        "paradas": [Parada(1, Punto(Decimal(1), Decimal(2)))],
    }
    r = _resumir(entrada)
    for k in ("destinatario", "asunto", "cuerpo", "pregunta", "csv"):
        assert k in CAMPOS_SENSIBLES and r[k] == "[omitido]"
    assert r["codigo_lote"] == "LOTE-1" and r["cobertura"] == "70.5"
    assert r["fecha_hora"] == "2026-10-26T00:00:00+00:00"
    assert r["paradas"] == {"cantidad": 1}  # las listas anidadas sólo se cuentan
    assert _resumir(b"123") == {"bytes": 3}
    assert _resumir("x" * 500) == {"texto_len": 500}
    assert _resumir(list(range(50))) == {"cantidad": 50}
