"""`/medico`: E2 Dar de alta Paciente, E3 Familiograma, E4 Dar de alta Estudio, E5 Asignar Cupón a
Paciente, E6 Solicitar Reanálisis. Más catálogos, propiedad de los datos y auditoría."""

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
)
from app.integrations.infra import MailMemoria
from app.models import (
    AuditoriaAcceso,
    Cupon,
    Estudio,
    EstudioGen,
    Gen,
    IntegracionLog,
    Notificacion,
    ObraSocial,
    Paciente,
    Patologia,
    Usuario,
)
from app.services.comun import ahora
from tests import factories
from tests.factories import headers

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
            "nombre": "Marta Rivas",
            "sintomas": "Insuficiencia renal",
            "patologia_diagnosticada_id": await _patologia(session, "Fabry"),
        },
        {"parentesco": "HERMANO", "nombre": "Pablo Rivas"},
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
    assert [f["parentesco"] for f in ficha["familiares"]] == ["MADRE", "HERMANO"]
    assert ficha["familiares"][0]["patologia_diagnosticada"] == "Fabry"
    assert ficha["sintomas"] == [{"concept_id": ACROPARESTESIA, "termino": "Acroparestesia"}]
    assert ficha["diagnosticos"][0]["patologia"] == "Fabry"
    auditoria = await session.scalar(select(AuditoriaAcceso).where(AuditoriaAcceso.accion == "VER_FICHA"))
    assert auditoria is not None and auditoria.entidad_id == pid and auditoria.usuario_id == medico.id

    # E3 por separado: agrega familiares y regenera el PDF
    r = await cliente.post(
        f"/medico/pacientes/{pid}/familiograma",
        json={"familiares": [{"parentesco": "TIA", "nombre": "Ana Rivas"}]},
        headers=headers(medico),
    )
    assert r.status_code == 200
    r = await cliente.get(f"/medico/pacientes/{pid}", headers=headers(medico))
    assert len(r.json()["familiares"]) == 3
    assert r.json()["familiograma_url"] != ficha["familiograma_url"]


async def test_alta_sin_familiares_deja_seccion_vacia(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    medico = demo[RolUsuario.MEDICO_TRATANTE]
    r = await cliente.post("/medico/pacientes", json=await _alta_paciente(session), headers=headers(medico))
    ficha = (await cliente.get(f"/medico/pacientes/{r.json()['id']}", headers=headers(medico))).json()
    assert ficha["familiares"] == [] and ficha["familiograma_url"] is None


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
