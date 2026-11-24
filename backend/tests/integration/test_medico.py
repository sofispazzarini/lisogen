"""`/medico`: E2 Dar de alta Paciente, E3 Familiograma, E4 Dar de alta Estudio, E5 Asignar Cupón a
Paciente, E6 Solicitar Reanálisis. Más catálogos, propiedad de los datos y auditoría."""

import re
from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    CanalNotif,
    EstadoCupon,
    EstadoEstudio,
    OrigenGen,
    RolUsuario,
    ServicioExterno,
    TipoEstudio,
    TipoResultado,
)
from app.integrations.apigen_api import ApigenNoDisponible
from app.integrations.infra import MailMemoria
from app.integrations.mock import BioinformaticaMock
from app.integrations.ports import ConceptoSnomed, DetalleError, ErrorFamiliograma, ErrorSnomed
from app.integrations.registro import Adaptadores
from app.models import (
    AuditoriaAcceso,
    Cupon,
    Estudio,
    EstudioGen,
    Familiar,
    Gen,
    IntegracionLog,
    Notificacion,
    ObraSocial,
    Paciente,
    Patologia,
    Resultado,
    SnomedConcepto,
    Usuario,
)
from app.services.comun import ahora
from tests import factories
from tests.factories import headers
from tests.falsos import FamiliogramaConReglas, FamiliogramaFalla, SnomedFalla, SnomedFalso

# Síntomas SNOMED del seed
ACROPARESTESIA, ANGIOQUERATOMA, HIPOHIDROSIS, PROTEINURIA = 79256006, 254788004, 45004005, 29738008
HIPOTONIA = 398152000
ESPLENOMEGALIA = 16294009


@pytest.fixture
async def demo(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    return await factories.seed(session)


async def _patologia(session: AsyncSession, nombre: str) -> int:
    pid = await session.scalar(select(Patologia.id).where(Patologia.nombre == nombre))
    assert pid is not None
    return pid


async def _alta_paciente(session: AsyncSession, **cambios: Any) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "dni": "40123456",
        "nombre": "Sofía",
        "apellido": "Rivas",
        "fecha_nacimiento": "1992-07-01",
        "telefono": "+54 11 5555-1234",
        "email": "sofia.rivas@test.com.ar",
        "resumen_historia_clinica": "Dolor neuropático en extremidades desde la infancia.",
        "sintomas": [ACROPARESTESIA],
        "diagnosticos": [{"patologia_id": await _patologia(session, "Fabry"), "tipo_sospecha": "CLINICA"}],
    }
    return datos | cambios


# --- Catálogos --------------------------------------------------------------------------------


async def test_buscar_snomed(cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario]) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    r = await cliente.get("/medico/snomed", params={"q": "acropar"}, headers=h)
    assert r.status_code == 200
    assert {"concept_id": ACROPARESTESIA, "termino": "Acroparestesia"} in r.json()
    r = await cliente.get("/medico/snomed", params={"q": "dolor"}, headers=h)
    assert {c["termino"] for c in r.json()} >= {"Dolor abdominal", "Dolor óseo"}
    r = await cliente.get("/medico/snomed", params={"q": "a"}, headers=h)
    assert r.status_code == 422


async def test_snomed_api_copia_lo_sugerido_a_la_cache(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    adaptadores.snomed = SnomedFalso(
        [ConceptoSnomed(267036007, "disnea"), ConceptoSnomed(ACROPARESTESIA, "Otro nombre de la API")]
    )
    r = await cliente.get("/medico/snomed", params={"q": "me falta el aire"}, headers=h)
    assert r.status_code == 200
    assert {c["concept_id"] for c in r.json()} == {267036007, ACROPARESTESIA}
    nuevo = await session.get(SnomedConcepto, 267036007)
    assert nuevo is not None and nuevo.termino == "disnea"  # ahora se puede guardar como síntoma
    existente = await session.get(SnomedConcepto, ACROPARESTESIA)
    assert existente is not None and existente.termino == "Acroparestesia"  # no pisa el término verificado
    log = await session.scalar(
        select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.SNOMED)
    )
    assert log is not None and log.ok and log.request["texto"] == "[omitido]"


async def test_snomed_sin_coincidencias_devuelve_lista_vacia(
    cliente: httpx.AsyncClient, adaptadores: Adaptadores, demo: dict[RolUsuario, Usuario]
) -> None:
    adaptadores.snomed = SnomedFalso([])
    r = await cliente.get(
        "/medico/snomed", params={"q": "dolor de muela"}, headers=headers(demo[RolUsuario.MEDICO_TRATANTE])
    )
    assert r.status_code == 200 and r.json() == []


async def test_si_la_api_de_snomed_falla_se_busca_en_la_cache(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    adaptadores: Adaptadores,
    demo: dict[RolUsuario, Usuario],
) -> None:
    adaptadores.snomed = SnomedFalla(ErrorSnomed("HTTP 503", status=503))
    r = await cliente.get(
        "/medico/snomed", params={"q": "acropar"}, headers=headers(demo[RolUsuario.MEDICO_TRATANTE])
    )
    assert r.status_code == 200
    assert {"concept_id": ACROPARESTESIA, "termino": "Acroparestesia"} in r.json()
    log = await session.scalar(
        select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.SNOMED)
    )
    assert log is not None and not log.ok  # la falla queda registrada


async def test_patologias_y_genes_de_la_api(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    r = await cliente.get("/medico/patologias", headers=h)
    assert {p["nombre"] for p in r.json()} == {"Fabry", "Pompe", "MPS 1", "Gaucher", "ASMD"}
    fabry = next(p for p in r.json() if p["nombre"] == "Fabry")
    assert fabry["sintoma_cardinal"]["termino"] == "Acroparestesia" and fabry["genes"] == ["GLA"]

    r = await cliente.get(f"/medico/patologias/{fabry['id']}/genes", headers=h)
    assert r.json()["genes"] == ["GLA"]
    assert r.json()["hallazgos_secundarios"] == ["BRCA1", "BRCA2", "MLH1", "LDLR", "MYBPC3"]
    llamadas = await session.scalar(
        select(func.count())
        .select_from(IntegracionLog)
        .where(IntegracionLog.servicio == ServicioExterno.BIOINFORMATICA)
    )
    assert llamadas == 2

    r = await cliente.get("/medico/obras-sociales", headers=h)
    assert len(r.json()) == 3


async def test_solo_medicos(cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario]) -> None:
    for rol in (RolUsuario.PACIENTE, RolUsuario.GERENTE_MEDICO, RolUsuario.ADMINISTRATIVO):
        r = await cliente.get("/medico/estudios", headers=headers(demo[rol]))
        assert r.status_code == 403
    assert (await cliente.get("/medico/estudios")).status_code == 401


# --- E2 Dar de alta Paciente ------------------------------------------------------------------


async def test_alta_paciente_envia_credenciales(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario], mails: MailMemoria
) -> None:
    r = await cliente.post(
        "/medico/pacientes",
        json=await _alta_paciente(session),
        headers=headers(demo[RolUsuario.MEDICO_TRATANTE]),
    )
    assert r.status_code == 201, r.text
    assert r.json()["dni"] == "40123456" and r.json()["cantidad_estudios"] == 0

    cuenta = await session.scalar(select(Usuario).where(Usuario.email == "sofia.rivas@test.com.ar"))
    assert cuenta is not None and cuenta.rol == RolUsuario.PACIENTE and cuenta.debe_cambiar_password
    mail = mails.enviados[-1]
    assert mail.destinatario == "sofia.rivas@test.com.ar"
    assert "Contraseña provisoria" in mail.cuerpo
    log = await session.scalar(select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.MAIL))
    assert log is not None and "sofia.rivas" not in str(log.request)


@pytest.mark.parametrize(
    ("sintomas", "valida"),
    [
        ([ACROPARESTESIA], True),  # síntoma cardinal
        ([ANGIOQUERATOMA, HIPOHIDROSIS], True),  # dos secundarios
        ([ANGIOQUERATOMA], False),  # un solo secundario
        ([ESPLENOMEGALIA, HIPOTONIA], False),  # síntomas de otras Patologías
    ],
)
async def test_validar_diagnostico(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    sintomas: list[int],
    valida: bool,
) -> None:
    r = await cliente.post(
        "/medico/pacientes",
        json=await _alta_paciente(session, sintomas=sintomas),
        headers=headers(demo[RolUsuario.MEDICO_TRATANTE]),
    )
    if valida:
        assert r.status_code == 201, r.text
    else:
        assert r.status_code == 422
        assert r.json()["code"] == "DIAGNOSTICO_NO_VALIDADO"
        assert "Fabry" in r.json()["message"]
        assert await session.scalar(select(Paciente.id).where(Paciente.dni == "40123456")) is None


@pytest.mark.parametrize(
    "faltante", ["dni", "fecha_nacimiento", "telefono", "resumen_historia_clinica", "sintomas"]
)
async def test_alta_paciente_datos_obligatorios(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario], faltante: str
) -> None:
    datos = await _alta_paciente(session)
    del datos[faltante]
    r = await cliente.post("/medico/pacientes", json=datos, headers=headers(demo[RolUsuario.MEDICO_TRATANTE]))
    assert r.status_code == 422 and r.json()["code"] == "DATOS_INVALIDOS"
    assert faltante in r.json()["campos"]


async def test_alta_paciente_menor_de_edad_usa_mail_del_padre(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario], mails: MailMemoria
) -> None:
    nacimiento = (ahora().date() - timedelta(days=60)).isoformat()
    datos = await _alta_paciente(
        session,
        fecha_nacimiento=nacimiento,
        email="papa.de.tomas@test.com.ar",
        sintomas=[HIPOTONIA],
        diagnosticos=[{"patologia_id": await _patologia(session, "Pompe"), "tipo_sospecha": "CLINICA"}],
    )
    r = await cliente.post("/medico/pacientes", json=datos, headers=headers(demo[RolUsuario.MEDICO_TRATANTE]))
    assert r.status_code == 201, r.text
    paciente = await session.scalar(select(Paciente).where(Paciente.dni == "40123456"))
    assert paciente is not None and paciente.es_menor_al_alta
    assert paciente.email_contacto == "papa.de.tomas@test.com.ar"
    assert "en nombre de tu hijo o hija" in mails.enviados[-1].cuerpo


async def test_alta_paciente_duplicados_y_obra_social(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    os_id = await session.scalar(select(ObraSocial.id).limit(1))
    r = await cliente.post(
        "/medico/pacientes",
        json=await _alta_paciente(session, obra_social_id=os_id, nro_afiliado="A-1"),
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["obra_social"] is not None
    r = await cliente.post(
        "/medico/pacientes", json=await _alta_paciente(session, email="otro@test.com.ar"), headers=h
    )
    assert r.status_code == 409 and r.json()["code"] == "PACIENTE_EXISTENTE"
    r = await cliente.post("/medico/pacientes", json=await _alta_paciente(session, dni="40999999"), headers=h)
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_EN_USO"
    r = await cliente.post(
        "/medico/pacientes",
        json=await _alta_paciente(session, dni="41000000", email="x@test.com.ar", nro_afiliado="A-2"),
        headers=h,
    )
    assert r.json()["code"] == "OBRA_SOCIAL_REQUERIDA"


async def test_alta_paciente_sintoma_inexistente(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    r = await cliente.post(
        "/medico/pacientes",
        json=await _alta_paciente(session, sintomas=[ACROPARESTESIA, 123]),
        headers=headers(demo[RolUsuario.MEDICO_TRATANTE]),
    )
    assert r.json()["code"] == "SINTOMA_DESCONOCIDO"


# --- E3 Familiograma y ficha ------------------------------------------------------------------


async def test_alta_con_familiograma_y_ficha_auditada(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    familiares = [
        {
            "parentesco": "MADRE",
            "nombre": "Marta",
            "apellido": "Rivas",
            "sintomas": "Insuficiencia renal",
            "patologia_diagnosticada_id": await _patologia(session, "Fabry"),
        },
        {"parentesco": "HERMANO", "nombre": "Pablo", "apellido": "Rivas"},
    ]
    r = await cliente.post(
        "/medico/pacientes",
        json=await _alta_paciente(session, familiares=familiares),
        headers=headers(medico),
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    r = await cliente.get(f"/medico/pacientes/{pid}", headers=headers(medico))
    ficha = r.json()
    assert ficha["familiograma_url"].startswith("memoria://familiograma_pdf/")
    assert ficha["familiograma_mime"] == "image/svg+xml" and ficha["familiograma_advertencias"] == []
    assert [f["parentesco"] for f in ficha["familiares"]] == ["MADRE", "HERMANO"]
    assert ficha["familiares"][0]["patologia_diagnosticada"] == "Fabry"
    assert ficha["sintomas"] == [{"concept_id": ACROPARESTESIA, "termino": "Acroparestesia"}]
    assert ficha["diagnosticos"][0]["patologia"] == "Fabry"
    auditoria = await session.scalar(select(AuditoriaAcceso).where(AuditoriaAcceso.accion == "VER_FICHA"))
    assert auditoria is not None and auditoria.entidad_id == pid and auditoria.usuario_id == medico.id

    # E3 por separado: agrega familiares y regenera el PDF
    r = await cliente.post(
        f"/medico/pacientes/{pid}/familiograma",
        json={"familiares": [{"parentesco": "TIA", "nombre": "Ana", "apellido": "Rivas", "lado": "MATERNO"}]},
        headers=headers(medico),
    )
    assert r.status_code == 200
    r = await cliente.get(f"/medico/pacientes/{pid}", headers=headers(medico))
    assert len(r.json()["familiares"]) == 3
    assert r.json()["familiograma_url"] != ficha["familiograma_url"]


async def test_familiar_con_lado_segun_parentesco(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    for familiar in (
        {"parentesco": "ABUELA", "nombre": "Rosa", "apellido": "Rivas"},  # falta el lado
        {"parentesco": "PADRE", "nombre": "Raúl", "apellido": "Rivas", "lado": "PATERNO"},  # sobra
        {"parentesco": "PADRE", "nombre": "Raúl"},  # falta el apellido
    ):
        r = await cliente.post(
            "/medico/pacientes", json=await _alta_paciente(session, familiares=[familiar]), headers=h
        )
        assert r.status_code == 422 and r.json()["code"] == "DATOS_INVALIDOS", familiar


async def test_familiograma_guarda_las_advertencias(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    familiares = [
        {"parentesco": "MADRE", "nombre": "Marta", "apellido": "Rivas"},
        {"parentesco": "OTRO", "nombre": "Elsa", "apellido": "Paz"},
    ]
    r = await cliente.post(
        "/medico/pacientes", json=await _alta_paciente(session, familiares=familiares), headers=h
    )
    assert r.status_code == 201, r.text
    ficha = (await cliente.get(f"/medico/pacientes/{r.json()['id']}", headers=h)).json()
    assert [a["codigo"] for a in ficha["familiograma_advertencias"]] == ["PARENTESCO_SIN_CODIGO"]
    assert "Elsa" not in ficha["familiograma_advertencias"][0]["mensaje"]
    assert len(ficha["familiares"]) == 2  # el familiar se guarda aunque no se dibuje


async def test_familiograma_422_de_la_api_se_muestra_con_los_campos(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    adaptadores: Adaptadores,
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    r = await cliente.post("/medico/pacientes", json=await _alta_paciente(session), headers=h)
    pid = r.json()["id"]
    falso = FamiliogramaFalla(
        ErrorFamiliograma(
            "API de familiograma HTTP 422",
            status=422,
            detalles=(DetalleError("personas.1.parentesco", "REFERENCIA_AMBIGUA: falta la madre"),),
        )
    )
    adaptadores.familiograma = falso
    r = await cliente.post(
        f"/medico/pacientes/{pid}/familiograma",
        json={
            "familiares": [{"parentesco": "ABUELA", "nombre": "Rosa", "apellido": "Paz", "lado": "MATERNO"}]
        },
        headers=h,
    )
    assert r.status_code == 422
    cuerpo = r.json()
    assert cuerpo["code"] == "FAMILIOGRAMA_DATOS_INVALIDOS"
    assert "Familiar n.º 1 (abuela materno): falta la madre" in cuerpo["message"]
    assert cuerpo["campos"] == ["Familiar n.º 1 (abuela materno) · parentesco"]
    assert [p.parentesco for p in falso.recibidas] == [0, 3]


async def test_alta_sigue_aunque_falle_el_familiograma_y_se_regenera_desde_la_ficha(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    adaptadores: Adaptadores,
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    real = adaptadores.familiograma
    adaptadores.familiograma = FamiliogramaFalla(ErrorFamiliograma("HTTP 502", status=502))
    familiares = [{"parentesco": "MADRE", "nombre": "Marta", "apellido": "Rivas"}]
    r = await cliente.post(
        "/medico/pacientes", json=await _alta_paciente(session, familiares=familiares), headers=h
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    ficha = (await cliente.get(f"/medico/pacientes/{pid}", headers=h)).json()
    assert ficha["familiograma_url"] is None and len(ficha["familiares"]) == 1
    assert [a["codigo"] for a in ficha["familiograma_advertencias"]] == ["FAMILIOGRAMA_PENDIENTE"]
    log = await session.scalar(
        select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.FAMILIOGRAMA)
    )
    assert log is not None and not log.ok and "Marta" not in str(log.request)

    # Vuelve la API: se regenera sin cargar familiares nuevos
    adaptadores.familiograma = real
    r = await cliente.post(f"/medico/pacientes/{pid}/familiograma", json={"familiares": []}, headers=h)
    assert r.status_code == 200, r.text
    ficha = (await cliente.get(f"/medico/pacientes/{pid}", headers=h)).json()
    assert ficha["familiograma_mime"] == "image/svg+xml" and ficha["familiograma_advertencias"] == []
    assert len(ficha["familiares"]) == 1


async def test_familiograma_deja_fuera_a_quien_le_falta_su_referencia(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    adaptadores: Adaptadores,
) -> None:
    """Primo paterno → tío paterno → abuelo paterno: sin abuelo, la API rechaza al tío; sin tío, al primo.
    Se dibuja el resto y cada exclusión queda como advertencia (no se inventan personas)."""
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    falso = FamiliogramaConReglas()
    adaptadores.familiograma = falso
    familiares = [
        {"parentesco": "MADRE", "nombre": "Marta", "apellido": "Rivas"},
        {"parentesco": "TIO", "nombre": "Raúl", "apellido": "Rivas", "lado": "PATERNO"},
        {"parentesco": "PRIMA", "nombre": "Sol", "apellido": "Rivas", "lado": "PATERNO"},
    ]
    r = await cliente.post(
        "/medico/pacientes", json=await _alta_paciente(session, familiares=familiares), headers=h
    )
    pid = r.json()["id"]
    ficha = (await cliente.get(f"/medico/pacientes/{pid}", headers=h)).json()
    assert ficha["familiograma_mime"] == "image/svg+xml"
    assert [a["codigo"] for a in ficha["familiograma_advertencias"]] == ["FAMILIAR_SIN_REFERENCIA"] * 2
    assert (
        "familiar n.º 2 (tio paterno): necesita un abuelo/a paterno/a"
        in ficha["familiograma_advertencias"][0]["mensaje"]
    )
    assert falso.pedidos == [[0, 1, 6, 8], [0, 1, 8], [0, 1]]

    # Con el abuelo paterno cargado, se dibujan todos
    r = await cliente.post(
        f"/medico/pacientes/{pid}/familiograma",
        json={
            "familiares": [{"parentesco": "ABUELO", "nombre": "José", "apellido": "Rivas", "lado": "PATERNO"}]
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    ficha = (await cliente.get(f"/medico/pacientes/{pid}", headers=h)).json()
    assert ficha["familiograma_advertencias"] == [] and falso.pedidos[-1] == [0, 1, 6, 8, 4]


async def test_familiograma_error_que_no_es_de_referencia_se_muestra(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    adaptadores: Adaptadores,
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    pid = (await cliente.post("/medico/pacientes", json=await _alta_paciente(session), headers=h)).json()[
        "id"
    ]
    adaptadores.familiograma = FamiliogramaConReglas()
    r = await cliente.post(
        f"/medico/pacientes/{pid}/familiograma",
        json={
            "familiares": [
                {"parentesco": "MADRE", "nombre": "Marta", "apellido": "Rivas"},
                {"parentesco": "PADRE", "nombre": "Raúl", "apellido": "Rivas"},
                {"parentesco": "PADRE", "nombre": "Luis", "apellido": "Paz"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 422
    assert "Familiar n.º 3 (padre): hay más de dos progenitores." in r.json()["message"]
    ficha = (await cliente.get(f"/medico/pacientes/{pid}", headers=h)).json()
    assert ficha["familiares"] == []  # E3 por separado: no se guarda nada


@pytest.mark.parametrize(
    ("status", "codigo", "http"),
    [
        (401, "FAMILIOGRAMA_NO_DISPONIBLE", 502),
        (415, "FAMILIOGRAMA_ERROR_INTERNO", 502),
        (413, "FAMILIOGRAMA_DEMASIADO_GRANDE", 422),
        (502, "FAMILIOGRAMA_SIN_RESPUESTA", 502),
        (0, "FAMILIOGRAMA_SIN_RESPUESTA", 502),
    ],
)
async def test_familiograma_errores_de_la_api(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    adaptadores: Adaptadores,
    status: int,
    codigo: str,
    http: int,
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    pid = (await cliente.post("/medico/pacientes", json=await _alta_paciente(session), headers=h)).json()[
        "id"
    ]
    adaptadores.familiograma = FamiliogramaFalla(ErrorFamiliograma(f"HTTP {status}", status=status))
    r = await cliente.post(
        f"/medico/pacientes/{pid}/familiograma",
        json={"familiares": [{"parentesco": "MADRE", "nombre": "Marta", "apellido": "Rivas"}]},
        headers=h,
    )
    assert (r.status_code, r.json()["code"]) == (http, codigo)
    assert "FAMILIOGRAMA_API_KEY" not in r.text


async def test_alta_sin_familiares_deja_seccion_vacia(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    r = await cliente.post("/medico/pacientes", json=await _alta_paciente(session), headers=headers(medico))
    ficha = (await cliente.get(f"/medico/pacientes/{r.json()['id']}", headers=headers(medico))).json()
    assert ficha["familiares"] == [] and ficha["familiograma_url"] is None


# --- Historial de la familia -----------------------------------------------------------------


async def test_alta_asigna_familia_y_se_puede_vincular(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    h = headers(demo[RolUsuario.MEDICO_TRATANTE])
    r = await cliente.post("/medico/pacientes", json=await _alta_paciente(session), headers=h)
    madre = (await cliente.get(f"/medico/pacientes/{r.json()['id']}", headers=h)).json()
    assert re.fullmatch(r"FAM-\d{6}", madre["familia_codigo"])

    # Alta de la hija con el número de la madre: queda en la misma familia
    hija = await _alta_paciente(
        session,
        dni="40999111",
        email="hija.rivas@test.com.ar",
        familia_codigo=madre["familia_codigo"].lower(),
    )
    r = await cliente.post("/medico/pacientes", json=hija, headers=h)
    assert r.status_code == 201, r.text
    ficha_hija = (await cliente.get(f"/medico/pacientes/{r.json()['id']}", headers=h)).json()
    assert ficha_hija["familia_codigo"] == madre["familia_codigo"]

    # Un primo dado de alta aparte se vincula después desde la ficha
    primo = await _alta_paciente(session, dni="40999222", email="primo.rivas@test.com.ar")
    pid = (await cliente.post("/medico/pacientes", json=primo, headers=h)).json()["id"]
    r = await cliente.put(
        f"/medico/pacientes/{pid}/familia", json={"familia_codigo": madre["familia_codigo"]}, headers=h
    )
    assert r.status_code == 200, r.text
    auditorias = await session.scalar(
        select(func.count()).where(AuditoriaAcceso.accion == "VINCULAR_FAMILIA")
    )
    assert auditorias == 2

    for codigo, esperado in (("FAM-999999", "FAMILIA_INEXISTENTE"), ("familia-1", "DATOS_INVALIDOS")):
        r = await cliente.put(f"/medico/pacientes/{pid}/familia", json={"familia_codigo": codigo}, headers=h)
        assert r.status_code == 422 and r.json()["code"] == esperado


async def test_historial_de_la_familia(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, bio = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.BIOINFORMATICO]
    otro_medico = await factories.usuario(session, RolUsuario.MEDICO_TRATANTE)
    propio = await factories.paciente(session, medico)
    ajeno = await factories.paciente(session, otro_medico, fecha_nacimiento=date(1960, 1, 1))
    ajeno.familia_codigo = propio.familia_codigo
    session.add(Familiar(paciente_id=ajeno.id, parentesco="MADRE", nombre="Elsa", apellido="Gómez"))
    finalizado = await factories.estudio_en(
        session, ajeno, otro_medico, EstadoEstudio.FINALIZADO, bioinformatico=bio
    )
    session.add(Resultado(estudio_id=finalizado.id, tipo=TipoResultado.POSITIVO, confirmado_por=bio.id))
    await session.flush()

    r = await cliente.get(f"/medico/familias/{propio.familia_codigo}", headers=headers(medico))
    assert r.status_code == 200, r.text
    historial = r.json()
    assert historial["familia_codigo"] == propio.familia_codigo
    mayor, menor = historial["miembros"]  # ordenados por fecha de nacimiento
    assert mayor["paciente_id"] is None  # no está a cargo del Médico: no puede abrir su ficha
    assert menor["paciente_id"] == propio.id
    assert [(e["codigo"], e["estado"], e["resultado"]) for e in mayor["estudios"]] == [
        (finalizado.codigo, "FINALIZADO", "POSITIVO")
    ]
    assert mayor["familiares_declarados"][0]["nombre"] == "Elsa"
    for dato in ("dni", "telefono", "email_contacto"):  # sin datos de contacto
        assert dato not in mayor
    assert ajeno.dni not in r.text and ajeno.email_contacto not in r.text
    auditoria = await session.scalar(
        select(AuditoriaAcceso).where(AuditoriaAcceso.accion == "VER_HISTORIAL_FAMILIA")
    )
    assert auditoria is not None and auditoria.usuario_id == medico.id

    # Un Médico sin Pacientes en esa familia no la ve
    tercero = await factories.usuario(session, RolUsuario.MEDICO_TRATANTE)
    r = await cliente.get(f"/medico/familias/{propio.familia_codigo}", headers=headers(tercero))
    assert r.status_code == 403
    r = await cliente.get("/medico/familias/FAM-999999", headers=headers(medico))
    assert r.status_code == 404
    r = await cliente.get("/medico/familias/cualquiera", headers=headers(medico))
    assert r.status_code == 422


async def test_medico_solo_ve_sus_pacientes(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    otro = await factories.usuario(session, RolUsuario.MEDICO_TRATANTE)
    paciente_demo = await session.scalar(select(Paciente))
    assert paciente_demo is not None
    r = await cliente.get(f"/medico/pacientes/{paciente_demo.id}", headers=headers(otro))
    assert r.status_code == 403
    r = await cliente.post("/medico/pacientes/buscar", json={"texto": ""}, headers=headers(otro))
    assert r.json() == []
    r = await cliente.post(
        "/medico/pacientes/buscar",
        json={"texto": "ibarra"},
        headers=headers(demo[RolUsuario.MEDICO_TRATANTE]),
    )
    assert [p["dni"] for p in r.json()] == ["30111222"]


# --- E4 Dar de alta Estudio -------------------------------------------------------------------


async def _genes(session: AsyncSession, estudio_id: int) -> dict[str, OrigenGen]:
    filas = await session.execute(
        select(Gen.simbolo, EstudioGen.origen)
        .join(Gen, Gen.id == EstudioGen.gen_id)
        .where(EstudioGen.estudio_id == estudio_id)
    )
    return dict(filas.tuples().all())


async def test_alta_estudio_con_genes_api_manuales_y_hallazgos(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    paciente = await session.scalar(select(Paciente))
    assert paciente is not None
    r = await cliente.post(
        "/medico/estudios",
        json={
            "paciente_id": paciente.id,
            "patologia_ids": [await _patologia(session, "Fabry")],
            "genes_manuales": ["tp53", "GLA"],
            "evalua_hallazgos_secundarios": True,
        },
        headers=headers(demo[RolUsuario.MEDICO_TRATANTE]),
    )
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "CREADO" and cuerpo["tipo"] == "EXOMA" and not cuerpo["urgente"]
    assert cuerpo["codigo"].startswith(f"EST-{ahora().year}-")
    assert cuerpo["patologias"] == ["Fabry"]
    genes = await _genes(session, cuerpo["id"])
    assert genes["GLA"] == OrigenGen.API_PATOLOGIA  # no se duplica como manual
    assert genes["TP53"] == OrigenGen.MANUAL
    assert {g for g, o in genes.items() if o == OrigenGen.HALLAZGO_SECUNDARIO} == {
        "BRCA1",
        "BRCA2",
        "MLH1",
        "LDLR",
        "MYBPC3",
    }
    log = await session.scalar(
        select(IntegracionLog).where(
            IntegracionLog.servicio == ServicioExterno.BIOINFORMATICA,
            IntegracionLog.estudio_id == cuerpo["id"],
        )
    )
    assert log is not None


async def test_alta_estudio_varias_patologias_suma_genes(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    paciente = await session.scalar(select(Paciente))
    assert paciente is not None
    r = await cliente.post(
        "/medico/estudios",
        json={
            "paciente_id": paciente.id,
            "patologia_ids": [await _patologia(session, "Fabry"), await _patologia(session, "Gaucher")],
        },
        headers=headers(demo[RolUsuario.MEDICO_TRATANTE]),
    )
    assert set(await _genes(session, r.json()["id"])) == {"GLA", "GBA1"}


async def test_alta_estudio_revierte_si_fallan_los_hallazgos(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    adaptadores: Adaptadores,
) -> None:
    class CatalogoCaido(BioinformaticaMock):
        async def genes_por_patologia(self, *, patologia: str) -> list[str]:
            return ["GENNUEVO"]

        async def genes_hallazgos_secundarios(self) -> list[str]:
            raise ApigenNoDisponible()

    adaptadores.bioinformatica = CatalogoCaido()
    paciente = await session.scalar(select(Paciente))
    assert paciente is not None
    r = await cliente.post(
        "/medico/estudios",
        json={
            "paciente_id": paciente.id,
            "patologia_ids": [await _patologia(session, "Fabry")],
            "evalua_hallazgos_secundarios": True,
        },
        headers=headers(demo[RolUsuario.MEDICO_TRATANTE]),
    )
    assert r.status_code == 502 and r.json()["code"] == "APIGEN_NO_DISPONIBLE"
    assert await session.scalar(select(Estudio.id)) is None
    assert await session.scalar(select(Gen.id).where(Gen.simbolo == "GENNUEVO")) is None


@pytest.mark.parametrize(("dias", "urgente"), [(60, True), (130, False)])
async def test_pompe_menor_de_4_meses_es_urgente(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    dias: int,
    urgente: bool,
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    bebe = await factories.paciente(session, medico, fecha_nacimiento=ahora().date() - timedelta(days=dias))
    r = await cliente.post(
        "/medico/estudios",
        json={"paciente_id": bebe.id, "patologia_ids": [await _patologia(session, "Pompe")]},
        headers=headers(medico),
    )
    assert r.status_code == 201
    assert r.json()["urgente"] is urgente


async def test_alta_estudio_valida_datos(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    paciente = await session.scalar(select(Paciente))
    assert paciente is not None
    r = await cliente.post(
        "/medico/estudios", json={"paciente_id": paciente.id, "patologia_ids": []}, headers=headers(medico)
    )
    assert r.json()["code"] == "DATOS_INVALIDOS"
    r = await cliente.post(
        "/medico/estudios",
        json={"paciente_id": paciente.id, "patologia_ids": [9999]},
        headers=headers(medico),
    )
    assert r.json()["code"] == "PATOLOGIA_INVALIDA"
    r = await cliente.post(
        "/medico/estudios",
        json={"paciente_id": paciente.id, "patologia_ids": [1], "genes_manuales": ["no válido!"]},
        headers=headers(medico),
    )
    assert r.json()["code"] == "DATOS_INVALIDOS"
    otro = await factories.usuario(session, RolUsuario.MEDICO_TRATANTE)
    r = await cliente.post(
        "/medico/estudios", json={"paciente_id": paciente.id, "patologia_ids": [1]}, headers=headers(otro)
    )
    assert r.status_code == 403


async def test_mis_estudios_y_detalle(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    paciente = await session.scalar(select(Paciente))
    assert paciente is not None
    mio = await factories.estudio(session, paciente, medico)
    otro_medico = await factories.usuario(session, RolUsuario.MEDICO_TRATANTE)
    ajeno = await factories.estudio(session, await factories.paciente(session, otro_medico), otro_medico)

    r = await cliente.get("/medico/estudios", headers=headers(medico))
    assert [e["id"] for e in r.json()] == [mio.id]
    r = await cliente.get(f"/medico/estudios/{mio.id}", headers=headers(medico))
    assert r.status_code == 200
    detalle = r.json()
    assert detalle["historial"][0]["estado_nuevo"] == "CREADO"
    assert detalle["presupuesto"] is None and detalle["turno"] is None
    r = await cliente.get(f"/medico/estudios/{ajeno.id}", headers=headers(medico))
    assert r.status_code == 404


# --- E6 Solicitar Reanálisis ------------------------------------------------------------------


async def test_reanalisis_reutiliza_el_exoma(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, bio = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.BIOINFORMATICO]
    paciente = await session.scalar(select(Paciente))
    assert paciente is not None
    exoma = await factories.estudio_finalizado(session, paciente, medico, bio)
    gla = await session.scalar(select(Gen).where(Gen.simbolo == "GLA"))
    assert gla is not None
    session.add(EstudioGen(estudio_id=exoma.id, gen_id=gla.id, origen=OrigenGen.API_PATOLOGIA))

    r = await cliente.post(
        f"/medico/estudios/{exoma.id}/reanalisis", json={"genes_manuales": ["GLA"]}, headers=headers(medico)
    )
    assert r.status_code == 422 and r.json()["code"] == "SIN_GENES_NUEVOS"

    r = await cliente.post(
        f"/medico/estudios/{exoma.id}/reanalisis",
        json={"patologia_ids": [await _patologia(session, "Pompe")], "genes_manuales": ["GLA"]},
        headers=headers(medico),
    )
    assert r.status_code == 201, r.text
    nuevo = r.json()
    assert nuevo["tipo"] == "REANALISIS" and nuevo["estado"] == "EN_ANALISIS_BIOINFORMATICA"
    reanalisis = await session.get(Estudio, nuevo["id"])
    assert reanalisis is not None and reanalisis.estudio_origen_id == exoma.id
    assert set(await _genes(session, nuevo["id"])) == {"GAA"}  # GLA ya se analizó
    aviso_bio = await session.scalar(
        select(Notificacion).where(
            Notificacion.usuario_id == bio.id,
            Notificacion.estudio_id == nuevo["id"],
            Notificacion.canal == CanalNotif.APP,
        )
    )
    assert aviso_bio is not None and "listo para análisis" in aviso_bio.asunto

    # Reanálisis de un Reanálisis: se ancla al exoma original
    estudio_r = await session.get(Estudio, nuevo["id"])
    assert estudio_r is not None and estudio_r.tipo == TipoEstudio.REANALISIS


async def test_reanalisis_solo_de_finalizado(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    paciente = await session.scalar(select(Paciente))
    assert paciente is not None
    creado = await factories.estudio(session, paciente, medico)
    r = await cliente.post(
        f"/medico/estudios/{creado.id}/reanalisis", json={"genes_manuales": ["GAA"]}, headers=headers(medico)
    )
    assert r.status_code == 409 and r.json()["code"] == "ESTUDIO_NO_FINALIZADO"
    assert creado.estado == EstadoEstudio.CREADO


# --- E5 Asignar Cupón a Paciente --------------------------------------------------------------


async def test_asignar_cupon_a_paciente(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, gerente = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.GERENTE_MEDICO]
    r = await cliente.post(
        "/gerente/cupones", json={"descuento_pct": 20, "cantidad": 2}, headers=headers(gerente)
    )
    ids = [c["id"] for c in r.json()]
    await cliente.post(
        "/gerente/cupones/asignar", json={"cupon_ids": ids, "medico_id": medico.id}, headers=headers(gerente)
    )

    r = await cliente.get("/medico/cupones", headers=headers(medico))
    assert {c["estado"] for c in r.json()} == {"ASIGNADO_MEDICO"}

    paciente = await session.scalar(select(Paciente))
    assert paciente is not None
    r = await cliente.post(
        f"/medico/cupones/{ids[0]}/asignar", json={"paciente_id": paciente.id}, headers=headers(medico)
    )
    assert r.status_code == 200
    cupon = await session.get(Cupon, ids[0])
    assert cupon is not None
    await session.refresh(cupon)
    assert cupon.estado == EstadoCupon.ASIGNADO_PACIENTE and cupon.paciente_asignado_id == paciente.id
    aviso = await session.scalar(
        select(Notificacion).where(
            Notificacion.usuario_id == paciente.usuario_id, Notificacion.asunto.contains("Cupón")
        )
    )
    assert aviso is not None

    # Ya no está disponible para el Médico (E5 ep. 4)
    r = await cliente.post(
        f"/medico/cupones/{ids[0]}/asignar", json={"paciente_id": paciente.id}, headers=headers(medico)
    )
    assert r.status_code == 409 and r.json()["code"] == "CUPON_NO_DISPONIBLE"
    disponibles = [
        c
        for c in (await cliente.get("/medico/cupones", headers=headers(medico))).json()
        if c["estado"] == "ASIGNADO_MEDICO"
    ]
    assert [c["id"] for c in disponibles] == [ids[1]]


async def test_asignar_cupon_ajeno_o_a_paciente_ajeno(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico, gerente = demo[RolUsuario.MEDICO_TRATANTE], demo[RolUsuario.GERENTE_MEDICO]
    otro = await factories.usuario(session, RolUsuario.MEDICO_TRATANTE)
    r = await cliente.post(
        "/gerente/cupones", json={"descuento_pct": 10, "cantidad": 1}, headers=headers(gerente)
    )
    cid = r.json()[0]["id"]
    await cliente.post(
        "/gerente/cupones/asignar", json={"cupon_ids": [cid], "medico_id": otro.id}, headers=headers(gerente)
    )
    paciente = await session.scalar(select(Paciente))
    assert paciente is not None

    r = await cliente.post(
        f"/medico/cupones/{cid}/asignar", json={"paciente_id": paciente.id}, headers=headers(medico)
    )
    assert r.status_code == 404  # el Cupón es de otro Médico
    r = await cliente.post(
        f"/medico/cupones/{cid}/asignar", json={"paciente_id": paciente.id}, headers=headers(otro)
    )
    assert r.status_code == 403  # el Paciente no es suyo


async def test_sin_cupones_disponibles(cliente: httpx.AsyncClient, demo: dict[RolUsuario, Usuario]) -> None:
    r = await cliente.get("/medico/cupones", headers=headers(demo[RolUsuario.MEDICO_TRATANTE]))
    assert r.status_code == 200 and r.json() == []


async def test_fecha_nacimiento_futura(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    futura = (date.today() + timedelta(days=3)).isoformat()
    r = await cliente.post(
        "/medico/pacientes",
        json=await _alta_paciente(session, fecha_nacimiento=futura),
        headers=headers(demo[RolUsuario.MEDICO_TRATANTE]),
    )
    assert r.json()["code"] == "FECHA_NACIMIENTO_INVALIDA"
