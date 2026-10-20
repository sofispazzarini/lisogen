"""E21 Cargar datos crudos, E22 Solicitar nueva extracción, E27 Tomar Estudio, E28 Cargar Variantes y
E13 Consultar Resultado."""

from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import (
    CanalNotif,
    EstadoEstudio,
    EstadoMuestra,
    MotivoReextraccion,
    OrigenGen,
    RolUsuario,
)
from app.models import (
    AuditoriaAcceso,
    CentroExtraccion,
    DatosCrudos,
    Estudio,
    EstudioGen,
    Gen,
    Muestra,
    Notificacion,
    Paciente,
    SolicitudReextraccion,
    Usuario,
)
from tests import factories, flujos
from tests.factories import headers
from tests.flujos import ok

GLA_PATOGENICA = "c.644A>G (p.Asn215Ser)"


@pytest.fixture
async def demo(session: AsyncSession) -> dict[RolUsuario, Usuario]:
    return await factories.seed(session)


async def _paciente_con_cuenta(session: AsyncSession, medico: Usuario) -> tuple[Paciente, Usuario]:
    p = await factories.paciente(session, medico)
    cuenta = await session.get(Usuario, p.usuario_id)
    assert cuenta is not None
    return p, cuenta


async def _en(
    session: AsyncSession, demo: dict[RolUsuario, Usuario], hasta: EstadoEstudio, **kw: Any
) -> Estudio:
    p = await factories.paciente(session, demo[RolUsuario.MEDICO_TRATANTE])
    return await factories.estudio_en(session, p, demo[RolUsuario.MEDICO_TRATANTE], hasta, **kw)


# --- E21 Cargar datos crudos ------------------------------------------------------------------


async def test_cargar_datos_crudos(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    admin, bio = demo[RolUsuario.ADMINISTRATIVO], demo[RolUsuario.BIOINFORMATICO]
    estudio = await _en(session, demo, EstadoEstudio.EN_VIAJE_COREA)
    m = await session.scalar(select(Muestra).where(Muestra.estudio_id == estudio.id))
    assert m is not None

    url = f"/administrativo/estudios/{estudio.id}/datos-crudos"
    r = await cliente.post(
        url, files={"archivo": ("vacio.fastq", b"", "application/octet-stream")}, headers=headers(admin)
    )
    assert r.status_code == 422 and r.json()["code"] == "ARCHIVO_VACIO"
    await ok(
        await cliente.post(
            url,
            files={"archivo": ("exoma.fastq.gz", b"@SEQ\nACGT\n", "application/gzip")},
            headers=headers(admin),
        )
    )
    assert await flujos.estado(cliente, admin, estudio.id) == "EN_ANALISIS_BIOINFORMATICA"
    crudos = await session.scalar(select(DatosCrudos).where(DatosCrudos.estudio_id == estudio.id))
    assert crudos is not None and crudos.cargado_por == admin.id
    await session.refresh(m)
    assert m.estado == EstadoMuestra.PROCESADA
    aviso = await session.scalar(
        select(Notificacion).where(Notificacion.usuario_id == bio.id, Notificacion.canal == CanalNotif.APP)
    )
    assert aviso is not None and estudio.codigo in aviso.asunto

    r = await cliente.post(
        url, files={"archivo": ("otra.fastq", b"ACGT", "application/octet-stream")}, headers=headers(admin)
    )
    assert r.status_code == 409 and r.json()["code"] == "ESTUDIO_SIN_MUESTRA_EN_COREA"


# --- E22 Solicitar nueva extracción -----------------------------------------------------------


async def test_reextraccion_por_adn_desnaturalizado(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    admin, medico = demo[RolUsuario.ADMINISTRATIVO], demo[RolUsuario.MEDICO_TRATANTE]
    p, cuenta = await _paciente_con_cuenta(session, medico)
    estudio = await factories.estudio_en(session, p, medico, EstadoEstudio.EN_VIAJE_COREA)
    await ok(
        await cliente.post(
            f"/administrativo/estudios/{estudio.id}/reextraccion",
            json={"motivo": "DESNATURALIZADA", "detalle": "Degradación en el transporte"},
            headers=headers(admin),
        )
    )
    assert await flujos.estado(cliente, admin, estudio.id) == "PAGADO"
    m = await session.scalar(select(Muestra).where(Muestra.estudio_id == estudio.id))
    assert m is not None
    await session.refresh(m)
    assert m.estado == EstadoMuestra.DESNATURALIZADA
    sol = await session.scalar(
        select(SolicitudReextraccion).where(SolicitudReextraccion.estudio_id == estudio.id)
    )
    assert (
        sol is not None
        and sol.motivo == MotivoReextraccion.DESNATURALIZADA
        and sol.solicitado_por == admin.id
    )
    destinatarios = set(
        await session.scalars(
            select(Notificacion.usuario_id).where(
                Notificacion.estudio_id == estudio.id, Notificacion.cuerpo.contains("desnaturalizó")
            )
        )
    )
    assert destinatarios == {cuenta.id, medico.id}

    # Mismo Estudio, sin costo: el Paciente saca un nuevo Turno y la nueva Muestra es la extracción 2
    from app.services.extracciones import registrar_extraccion

    centro = await session.scalar(select(CentroExtraccion.id).order_by(CentroExtraccion.id).limit(1))
    assert centro is not None
    dia = await flujos.proximo_dia_habil(session)
    turno = await flujos.sacar_turno(cliente, cuenta, estudio.id, centro, flujos.slot(dia, 12))
    nueva = await registrar_extraccion(session, turno["id"], Decimal("5"))
    assert nueva.nro_extraccion == 2


async def test_reextraccion_solo_con_muestra_en_corea(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    estudio = await _en(session, demo, EstadoEstudio.EN_LAB_CENTRAL)
    r = await cliente.post(
        f"/administrativo/estudios/{estudio.id}/reextraccion",
        json={},
        headers=headers(demo[RolUsuario.ADMINISTRATIVO]),
    )
    assert r.status_code == 409


# --- E27 Tomar Estudio ------------------------------------------------------------------------


async def test_pendientes_urgentes_primero_y_tomar_con_lock_optimista(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    bio = demo[RolUsuario.BIOINFORMATICO]
    otro_bio = await factories.usuario(session, RolUsuario.BIOINFORMATICO)
    comun = await _en(session, demo, EstadoEstudio.EN_ANALISIS_BIOINFORMATICA)
    urgente = await _en(session, demo, EstadoEstudio.EN_ANALISIS_BIOINFORMATICA, urgente=True)

    pendientes = await ok(await cliente.get("/bioinformatico/pendientes", headers=headers(bio)))
    assert [e["id"] for e in pendientes] == [urgente.id, comun.id]
    version = pendientes[0]["version"]

    r = await cliente.post(
        f"/bioinformatico/estudios/{urgente.id}/tomar", json={"version": version - 1}, headers=headers(bio)
    )
    assert r.status_code == 409 and r.json()["code"] == "ESTUDIO_YA_TOMADO"
    tomado = await ok(
        await cliente.post(
            f"/bioinformatico/estudios/{urgente.id}/tomar", json={"version": version}, headers=headers(bio)
        )
    )
    assert tomado["estado"] == "EN_ANALISIS" and tomado["tomado_por_mi"] and tomado["datos_crudos_url"]

    # El otro Bioinformático ya no lo ve disponible y si intenta tomarlo con la versión vieja: 409
    pendientes = await ok(await cliente.get("/bioinformatico/pendientes", headers=headers(otro_bio)))
    assert [e["id"] for e in pendientes] == [comun.id]
    r = await cliente.post(
        f"/bioinformatico/estudios/{urgente.id}/tomar", json={"version": version}, headers=headers(otro_bio)
    )
    assert r.status_code == 409 and r.json()["code"] == "ESTUDIO_YA_TOMADO"
    r = await cliente.get(f"/bioinformatico/estudios/{urgente.id}", headers=headers(otro_bio))
    assert r.status_code == 403
    mios = await ok(await cliente.get("/bioinformatico/estudios", headers=headers(bio)))
    assert [e["id"] for e in mios] == [urgente.id]


# --- E28 Cargar Variantes y E13 Consultar Resultado -------------------------------------------


async def _tomado(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario], **kw: Any
) -> Estudio:
    bio = demo[RolUsuario.BIOINFORMATICO]
    estudio = await _en(session, demo, EstadoEstudio.EN_ANALISIS_BIOINFORMATICA, **kw)
    await ok(
        await cliente.post(
            f"/bioinformatico/estudios/{estudio.id}/tomar",
            json={"version": estudio.version},
            headers=headers(bio),
        )
    )
    return estudio


async def test_variantes_del_gen_desde_la_api(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    bio = demo[RolUsuario.BIOINFORMATICO]
    estudio = await _tomado(cliente, session, demo)
    variantes = await ok(
        await cliente.get(f"/bioinformatico/estudios/{estudio.id}/genes/gla/variantes", headers=headers(bio))
    )
    assert GLA_PATOGENICA in [v["nomenclatura"] for v in variantes] and len(variantes) == 3
    r = await cliente.get(f"/bioinformatico/estudios/{estudio.id}/genes/GAA/variantes", headers=headers(bio))
    assert r.status_code == 422 and r.json()["code"] == "GEN_NO_SOLICITADO"


@pytest.mark.parametrize(
    ("variantes", "tipo"),
    [
        ([], "NEGATIVO"),
        ([{"gen": "GLA", "nomenclatura": GLA_PATOGENICA, "clasificacion": "PATOGENICA"}], "POSITIVO"),
        (
            [{"gen": "GLA", "nomenclatura": GLA_PATOGENICA, "clasificacion": "SIGNIFICADO_INCIERTO"}],
            "NO_CONCLUYENTE",
        ),
        ([{"gen": "GLA", "nomenclatura": GLA_PATOGENICA, "clasificacion": "BENIGNA"}], "NEGATIVO"),
    ],
)
async def test_confirmar_resultado(
    cliente: httpx.AsyncClient,
    session: AsyncSession,
    demo: dict[RolUsuario, Usuario],
    variantes: list,
    tipo: str,
) -> None:
    bio, medico = demo[RolUsuario.BIOINFORMATICO], demo[RolUsuario.MEDICO_TRATANTE]
    p, cuenta = await _paciente_con_cuenta(session, medico)
    estudio = await factories.estudio_en(session, p, medico, EstadoEstudio.EN_ANALISIS_BIOINFORMATICA)
    await ok(
        await cliente.post(
            f"/bioinformatico/estudios/{estudio.id}/tomar",
            json={"version": estudio.version},
            headers=headers(bio),
        )
    )

    r = await cliente.get(f"/paciente/estudios/{estudio.id}/resultado", headers=headers(cuenta))
    assert r.status_code == 404  # todavía no hay Resultado

    res = await ok(
        await cliente.post(
            f"/bioinformatico/estudios/{estudio.id}/resultado",
            json={"variantes": variantes},
            headers=headers(bio),
        )
    )
    assert res["tipo"] == tipo and res["pdf_url"].startswith("memoria://resultado_pdf/")
    assert await flujos.estado(cliente, demo[RolUsuario.ADMINISTRATIVO], estudio.id) == "FINALIZADO"
    avisados = set(
        await session.scalars(
            select(Notificacion.usuario_id).where(
                Notificacion.estudio_id == estudio.id, Notificacion.asunto.contains("Finalizado")
            )
        )
    )
    assert avisados == {cuenta.id, medico.id}

    # E13: el Paciente consulta y descarga; cada lectura queda auditada
    resultado = await ok(
        await cliente.get(f"/paciente/estudios/{estudio.id}/resultado", headers=headers(cuenta))
    )
    assert resultado["tipo"] == tipo and len(resultado["variantes"]) == len(variantes)
    await ok(await cliente.get(f"/medico/estudios/{estudio.id}/resultado", headers=headers(medico)))
    lecturas = set(
        await session.scalars(
            select(AuditoriaAcceso.usuario_id).where(AuditoriaAcceso.accion == "VER_RESULTADO")
        )
    )
    assert {cuenta.id, medico.id} <= lecturas
    otro = await factories.usuario(session, RolUsuario.PACIENTE)
    assert (
        await cliente.get(f"/paciente/estudios/{estudio.id}/resultado", headers=headers(otro))
    ).status_code == 404


async def test_hallazgo_secundario_no_define_el_resultado(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    bio = demo[RolUsuario.BIOINFORMATICO]
    estudio = await _tomado(cliente, session, demo)
    brca1 = await session.scalar(select(Gen).where(Gen.simbolo == "BRCA1"))
    assert brca1 is not None
    session.add(EstudioGen(estudio_id=estudio.id, gen_id=brca1.id, origen=OrigenGen.HALLAZGO_SECUNDARIO))
    await session.flush()
    res = await ok(
        await cliente.post(
            f"/bioinformatico/estudios/{estudio.id}/resultado",
            json={
                "variantes": [
                    {
                        "gen": "BRCA1",
                        "nomenclatura": "c.68_69del (p.Glu23ValfsTer17)",
                        "clasificacion": "PATOGENICA",
                    }
                ]
            },
            headers=headers(bio),
        )
    )
    assert res["tipo"] == "NEGATIVO"  # SUPUESTO S5
    assert res["variantes"][0]["hallazgo_secundario"] is True


async def test_resultado_validaciones(
    cliente: httpx.AsyncClient, session: AsyncSession, demo: dict[RolUsuario, Usuario]
) -> None:
    bio = demo[RolUsuario.BIOINFORMATICO]
    sin_tomar = await _en(session, demo, EstadoEstudio.EN_ANALISIS_BIOINFORMATICA)
    r = await cliente.post(
        f"/bioinformatico/estudios/{sin_tomar.id}/resultado", json={"variantes": []}, headers=headers(bio)
    )
    assert r.status_code == 409 and r.json()["code"] == "ESTUDIO_NO_EN_ANALISIS"

    estudio = await _tomado(cliente, session, demo)
    url = f"/bioinformatico/estudios/{estudio.id}/resultado"
    casos = [
        ([{"gen": "GLA", "nomenclatura": "c.1A>T", "clasificacion": "PATOGENICA"}], "VARIANTE_DESCONOCIDA"),
        ([{"gen": "TP53", "nomenclatura": "c.1A>T", "clasificacion": "PATOGENICA"}], "GEN_NO_SOLICITADO"),
        (
            [{"gen": "GLA", "nomenclatura": GLA_PATOGENICA, "clasificacion": "PATOGENICA"}] * 2,
            "VARIANTE_REPETIDA",
        ),
    ]
    for variantes, code in casos:
        r = await cliente.post(url, json={"variantes": variantes}, headers=headers(bio))
        assert r.status_code == 422 and r.json()["code"] == code
    otro_bio = await factories.usuario(session, RolUsuario.BIOINFORMATICO)
    r = await cliente.post(url, json={"variantes": []}, headers=headers(otro_bio))
    assert r.status_code == 403
