"""Contra la API real de familiograma. Se saltea si FAMILIOGRAMA_API_KEY no está definida (en el entorno
o en el .env de la raíz del repositorio, el mismo que usa docker compose).

Los árboles son ficticios. El de punta a punta usa la base de test, como el resto de la integración.
La clave nunca se imprime."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domain.enums import RolUsuario
from app.integrations import familiograma_mapeo as mapeo
from app.integrations.familiograma_api import FamiliogramaApi
from app.integrations.ports import CodigoNombre, ErrorFamiliograma, PersonaFamiliograma
from app.integrations.registro import Adaptadores
from app.models import Archivo, Paciente, Usuario
from tests import factories
from tests.conftest import BACKEND
from tests.factories import headers
from tests.integration.test_medico import _alta_paciente, _patologia

_settings = Settings(_env_file=(BACKEND.parent / ".env", ".env"))  # type: ignore[call-arg]
pytestmark = pytest.mark.skipif(
    not _settings.familiograma_api_key, reason="FAMILIOGRAMA_API_KEY no está definida"
)


def _api() -> FamiliogramaApi:
    return FamiliogramaApi(_settings)


async def test_catalogo_de_parentescos_coincide_con_el_mapeo() -> None:
    catalogo = await _api().parentescos()
    assert {p.id: p.parentesco for p in catalogo} == mapeo.CATALOGO


async def test_genera_un_svg() -> None:
    imagen = await _api().generar(
        personas=[
            PersonaFamiliograma(0, "Paciente", "Prueba", edad=30),
            PersonaFamiliograma(
                1, "Madre", "Prueba", "mujer", diagnosticos=(CodigoNombre("SIM-FABRY", "Fabry"),)
            ),
            PersonaFamiliograma(1, "Padre", "Prueba", "hombre", fallecido=True, edad=60),
            PersonaFamiliograma(3, "Abuela", "Materna", "mujer"),
        ]
    )
    assert imagen.mime == "image/svg+xml"
    assert b"<svg" in imagen.contenido and b"<script" not in imagen.contenido


async def test_vinculo_imposible_responde_422_con_detalles() -> None:
    # Abuela materna sin progenitor mujer: el lado materno no se puede deducir
    with pytest.raises(ErrorFamiliograma) as e:
        await _api().generar(
            personas=[
                PersonaFamiliograma(0, "Paciente", "Prueba"),
                PersonaFamiliograma(3, "Abuela", "Prueba", "mujer"),
            ]
        )
    assert e.value.status == 422 and e.value.detalles


@pytest.fixture
async def demo(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    return await factories.seed(session)


async def test_alta_con_familiograma_real_de_punta_a_punta(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    adaptadores: Adaptadores,
) -> None:
    """E2 + E3 por HTTP con la API real: el SVG queda guardado y la ficha lo muestra con sus avisos."""
    adaptadores.familiograma = _api()
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    familiares = [
        {
            "parentesco": "MADRE",
            "nombre": "Marta",
            "apellido": "Prueba",
            "patologia_diagnosticada_id": await _patologia(session, "Fabry"),
        },
        {"parentesco": "PADRE", "nombre": "Raúl", "apellido": "Prueba"},
        {"parentesco": "ABUELA", "nombre": "Rosa", "apellido": "Prueba", "lado": "MATERNO"},
        {"parentesco": "TIO", "nombre": "Juan", "apellido": "Prueba", "lado": "PATERNO"},
        {"parentesco": "OTRO", "nombre": "Elsa", "apellido": "Prueba"},
    ]
    r = await cliente.post(
        "/medico/pacientes", json=await _alta_paciente(session, familiares=familiares), headers=h
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    ficha = (await cliente.get(f"/medico/pacientes/{pid}", headers=h)).json()
    assert ficha["familiograma_mime"] == "image/svg+xml", ficha["familiograma_advertencias"]
    # OTRO no tiene código; el tío paterno necesita un abuelo paterno (regla de la API real)
    codigos = [a["codigo"] for a in ficha["familiograma_advertencias"]]
    assert codigos == ["PARENTESCO_SIN_CODIGO", "FAMILIAR_SIN_REFERENCIA"], ficha["familiograma_advertencias"]

    paciente = await session.get(Paciente, pid)
    assert paciente is not None and paciente.familiograma_archivo_id is not None
    archivo = await session.get(Archivo, paciente.familiograma_archivo_id)
    assert archivo is not None and archivo.nombre.endswith(".svg")
    svg = await adaptadores.storage.leer(clave=archivo.storage_key)
    assert svg.lstrip().startswith(b"<?xml") and b"<svg" in svg and b"<script" not in svg
    assert b"Marta" in svg  # el dibujo lleva los nombres

    # Con el abuelo paterno cargado se dibuja también el tío
    r = await cliente.post(
        f"/medico/pacientes/{pid}/familiograma",
        json={
            "familiares": [
                {"parentesco": "ABUELO", "nombre": "José", "apellido": "Prueba", "lado": "PATERNO"}
            ]
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    ficha = (await cliente.get(f"/medico/pacientes/{pid}", headers=h)).json()
    assert [a["codigo"] for a in ficha["familiograma_advertencias"]] == ["PARENTESCO_SIN_CODIGO"]

    # Un error que no es de referencia (tres progenitores) se informa y no guarda nada
    otro = await _alta_paciente(session, dni="40999888", email="otra.prueba@test.com.ar")
    pid2 = (await cliente.post("/medico/pacientes", json=otro, headers=h)).json()["id"]
    r = await cliente.post(
        f"/medico/pacientes/{pid2}/familiograma",
        json={
            "familiares": [
                {"parentesco": "MADRE", "nombre": "Ana", "apellido": "Prueba"},
                {"parentesco": "PADRE", "nombre": "Raúl", "apellido": "Prueba"},
                {"parentesco": "PADRE", "nombre": "Luis", "apellido": "Prueba"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 422 and r.json()["code"] == "FAMILIOGRAMA_DATOS_INVALIDOS", r.text
    assert "Familiar n.º" in r.json()["message"]
