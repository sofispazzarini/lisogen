"""E1, E7, E15, E26, E29: registro de profesionales, ingreso con verificación de dispositivo nuevo,
cambio obligatorio de contraseña, refresh, rate limit y autorización por rol."""

import re
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.api.deps import requiere_rol
from app.domain.enums import RolUsuario, ServicioExterno
from app.integrations.infra import MailMemoria
from app.models import CodigoVerificacion, DispositivoConfiable, Especialidad, IntegracionLog, Usuario
from app.services.comun import ahora

PASSWORD = "Clave-segura-2026"


async def crear_usuario(
    session: AsyncSession,
    rol: RolUsuario,
    email: str,
    *,
    debe_cambiar: bool = False,
    password: str = PASSWORD,
) -> Usuario:
    u = Usuario(
        email=email,
        password_hash=security.hashear_password(password),
        rol=rol,
        nombre="Prueba",
        apellido="Usuario",
        telefono="1145550000",
        debe_cambiar_password=debe_cambiar,
    )
    session.add(u)
    await session.flush()
    return u


def codigo_del_mail(mails: MailMemoria) -> str:
    m = re.search(r"\b(\d{6})\b", mails.enviados[-1].cuerpo)
    assert m, mails.enviados[-1].cuerpo
    return m.group(1)


async def ingresar(
    cliente: httpx.AsyncClient, mails: MailMemoria, email: str, password: str = PASSWORD
) -> dict[str, Any]:
    """Login completo desde un dispositivo nuevo: login → código por mail → verificar."""
    r = await cliente.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "VERIFICACION_REQUERIDA"
    r = await cliente.post(
        "/auth/verificar", json={"desafio_token": r.json()["desafio_token"], "codigo": codigo_del_mail(mails)}
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


# --- E7: ingreso y dispositivo nuevo --------------------------------------------------------


async def test_dispositivo_nuevo_pide_codigo_y_luego_queda_confiable(
    cliente: httpx.AsyncClient, session: AsyncSession, mails: MailMemoria
) -> None:
    await crear_usuario(session, RolUsuario.ADMINISTRATIVO, "admin@test.com.ar")
    datos = await ingresar(cliente, mails, "admin@test.com.ar")
    assert datos["estado"] == "OK"
    assert datos["access_token"] and datos["refresh_token"]
    assert datos["usuario"]["rol"] == "ADMINISTRATIVO"
    assert mails.enviados[-1].destinatario == "admin@test.com.ar"

    # Mismo dispositivo: entra directo, sin otro mail
    enviados = len(mails.enviados)
    r = await cliente.post("/auth/login", json={"email": "admin@test.com.ar", "password": PASSWORD})
    assert r.json()["estado"] == "OK"
    assert len(mails.enviados) == enviados

    # Otro dispositivo: vuelve a pedir código
    r = await cliente.post(
        "/auth/login",
        json={"email": "admin@test.com.ar", "password": PASSWORD},
        headers={"X-Device-Id": "otro"},
    )
    assert r.json()["estado"] == "VERIFICACION_REQUERIDA"
    assert await session.scalar(select(func.count()).select_from(DispositivoConfiable)) == 1


async def test_mail_del_codigo_queda_en_integracion_log_sin_datos_personales(
    cliente: httpx.AsyncClient, session: AsyncSession, mails: MailMemoria
) -> None:
    await crear_usuario(session, RolUsuario.BIOINFORMATICO, "bio@test.com.ar")
    await cliente.post("/auth/login", json={"email": "bio@test.com.ar", "password": PASSWORD})
    log = await session.scalar(select(IntegracionLog).where(IntegracionLog.servicio == ServicioExterno.MAIL))
    assert log is not None and log.ok and log.operacion == "enviar"
    texto = str(log.request) + str(log.response)
    assert "bio@test.com.ar" not in texto
    assert codigo_del_mail(mails) not in texto


async def test_credenciales_invalidas(cliente: httpx.AsyncClient, session: AsyncSession) -> None:
    await crear_usuario(session, RolUsuario.PACIENTE, "p@test.com.ar")
    for email, pw in (("p@test.com.ar", "otra-cosa-123"), ("nadie@test.com.ar", PASSWORD)):
        r = await cliente.post("/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 401
        assert r.json() == {
            "code": "CREDENCIALES_INVALIDAS",
            "message": "El mail o la contraseña no son correctos.",
        }


async def test_usuario_inactivo_no_ingresa(cliente: httpx.AsyncClient, session: AsyncSession) -> None:
    u = await crear_usuario(session, RolUsuario.PACIENTE, "inactivo@test.com.ar")
    u.activo = False
    r = await cliente.post("/auth/login", json={"email": "inactivo@test.com.ar", "password": PASSWORD})
    assert r.status_code == 401


async def test_codigo_incorrecto_suma_intentos_y_se_bloquea(
    cliente: httpx.AsyncClient, session: AsyncSession, mails: MailMemoria
) -> None:
    await crear_usuario(session, RolUsuario.GERENTE_MEDICO, "g@test.com.ar")
    r = await cliente.post("/auth/login", json={"email": "g@test.com.ar", "password": PASSWORD})
    desafio = r.json()["desafio_token"]
    bueno = codigo_del_mail(mails)
    malo = "000000" if bueno != "000000" else "111111"
    for _ in range(4):
        r = await cliente.post("/auth/verificar", json={"desafio_token": desafio, "codigo": malo})
        assert r.status_code == 422 and r.json()["code"] == "CODIGO_INCORRECTO"
    cv = await session.scalar(select(CodigoVerificacion))
    assert cv is not None
    await session.refresh(cv)
    assert cv.intentos == 4
    await session.execute(update(CodigoVerificacion).values(intentos=5))
    r = await cliente.post("/auth/verificar", json={"desafio_token": desafio, "codigo": bueno})
    assert r.json()["code"] == "CODIGO_VENCIDO"


async def test_codigo_vencido(cliente: httpx.AsyncClient, session: AsyncSession, mails: MailMemoria) -> None:
    await crear_usuario(session, RolUsuario.GERENTE_MEDICO, "v@test.com.ar")
    r = await cliente.post("/auth/login", json={"email": "v@test.com.ar", "password": PASSWORD})
    await session.execute(update(CodigoVerificacion).values(expira_at=ahora() - timedelta(seconds=1)))
    r = await cliente.post(
        "/auth/verificar", json={"desafio_token": r.json()["desafio_token"], "codigo": codigo_del_mail(mails)}
    )
    assert r.status_code == 422 and r.json()["code"] == "CODIGO_VENCIDO"


async def test_desafio_invalido(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/auth/verificar", json={"desafio_token": "basura", "codigo": "123456"})
    assert r.status_code == 401 and r.json()["code"] == "DESAFIO_VENCIDO"


async def test_paciente_primer_ingreso_cambia_password(
    cliente: httpx.AsyncClient, session: AsyncSession, mails: MailMemoria
) -> None:
    """E7: credenciales provisorias → código por equipo nuevo → cambio obligatorio → acceso."""
    await crear_usuario(
        session, RolUsuario.PACIENTE, "paciente@test.com.ar", debe_cambiar=True, password="Provisoria1"
    )
    datos = await ingresar(cliente, mails, "paciente@test.com.ar", "Provisoria1")
    assert datos["estado"] == "CAMBIO_PASSWORD_REQUERIDO"
    assert datos["access_token"] is None
    desafio = datos["desafio_token"]

    r = await cliente.post(
        "/auth/cambiar-password", json={"desafio_token": desafio, "password_nueva": "corta"}
    )
    assert r.status_code == 422 and r.json()["code"] == "PASSWORD_DEBIL"
    r = await cliente.post(
        "/auth/cambiar-password", json={"desafio_token": desafio, "password_nueva": "Provisoria1"}
    )
    assert r.json()["code"] in {"PASSWORD_DEBIL", "PASSWORD_REPETIDA"}

    r = await cliente.post(
        "/auth/cambiar-password", json={"desafio_token": desafio, "password_nueva": PASSWORD}
    )
    assert r.status_code == 200 and r.json()["estado"] == "OK"
    token = r.json()["access_token"]
    r = await cliente.get("/auth/yo", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["email"] == "paciente@test.com.ar"

    # La provisoria ya no sirve; la nueva entra directo (el dispositivo quedó confiable)
    r = await cliente.post("/auth/login", json={"email": "paciente@test.com.ar", "password": "Provisoria1"})
    assert r.status_code == 401
    r = await cliente.post("/auth/login", json={"email": "paciente@test.com.ar", "password": PASSWORD})
    assert r.json()["estado"] == "OK"


async def test_token_de_desafio_no_sirve_como_access(
    cliente: httpx.AsyncClient, session: AsyncSession, mails: MailMemoria
) -> None:
    await crear_usuario(session, RolUsuario.PACIENTE, "d@test.com.ar", debe_cambiar=True)
    datos = await ingresar(cliente, mails, "d@test.com.ar")
    r = await cliente.get("/auth/yo", headers={"Authorization": f"Bearer {datos['desafio_token']}"})
    assert r.status_code == 401


async def test_access_con_password_provisoria_pendiente_es_403(
    session: AsyncSession, cliente: httpx.AsyncClient
) -> None:
    u = await crear_usuario(session, RolUsuario.PACIENTE, "pend@test.com.ar", debe_cambiar=True)
    token = security.crear_token(u.id, u.rol, "access")
    r = await cliente.get("/auth/yo", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403 and r.json()["code"] == "CAMBIO_PASSWORD_REQUERIDO"


async def test_cambio_voluntario_con_password_actual(
    cliente: httpx.AsyncClient, session: AsyncSession, mails: MailMemoria
) -> None:
    await crear_usuario(session, RolUsuario.ADMINISTRATIVO, "c@test.com.ar")
    token = (await ingresar(cliente, mails, "c@test.com.ar"))["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    r = await cliente.post(
        "/auth/cambiar-password",
        json={"password_actual": "mala-1234567", "password_nueva": "Otra-clave-2027"},
        headers=auth,
    )
    assert r.json()["code"] == "PASSWORD_ACTUAL_INCORRECTA"
    r = await cliente.post(
        "/auth/cambiar-password",
        json={"password_actual": PASSWORD, "password_nueva": "Otra-clave-2027"},
        headers=auth,
    )
    assert r.status_code == 200
    r = await cliente.post("/auth/cambiar-password", json={"password_nueva": "Otra-clave-2028"})
    assert r.status_code == 401


async def test_refresh(cliente: httpx.AsyncClient, session: AsyncSession, mails: MailMemoria) -> None:
    await crear_usuario(session, RolUsuario.TRANSPORTISTA, "t@test.com.ar")
    datos = await ingresar(cliente, mails, "t@test.com.ar")
    r = await cliente.post("/auth/refresh", json={"refresh_token": datos["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]
    r = await cliente.post("/auth/refresh", json={"refresh_token": datos["access_token"]})
    assert r.status_code == 401 and r.json()["code"] == "SESION_VENCIDA"


async def test_rate_limit_en_login(cliente: httpx.AsyncClient, session: AsyncSession) -> None:
    await crear_usuario(session, RolUsuario.PACIENTE, "rl@test.com.ar")
    for _ in range(5):
        r = await cliente.post("/auth/login", json={"email": "rl@test.com.ar", "password": "incorrecta-1"})
        assert r.status_code == 401
    r = await cliente.post("/auth/login", json={"email": "rl@test.com.ar", "password": PASSWORD})
    assert r.status_code == 429 and r.json()["code"] == "DEMASIADOS_INTENTOS"


async def test_rate_limit_en_verificacion(cliente: httpx.AsyncClient, session: AsyncSession) -> None:
    await crear_usuario(session, RolUsuario.PACIENTE, "rv@test.com.ar")
    r = await cliente.post("/auth/login", json={"email": "rv@test.com.ar", "password": PASSWORD})
    desafio = r.json()["desafio_token"]
    codigos = []
    for _ in range(6):
        r = await cliente.post("/auth/verificar", json={"desafio_token": desafio, "codigo": "000001"})
        codigos.append(r.status_code)
    assert codigos[-1] == 429


# --- E1, E15, E26, E29: registro de profesionales -------------------------------------------


async def _especialidad(session: AsyncSession) -> int:
    e = Especialidad(nombre="Genética Médica")
    session.add(e)
    await session.flush()
    return e.id


def _registro(**cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "rol": "MEDICO_TRATANTE",
        "nombre": "Laura",
        "apellido": "Gómez",
        "telefono": "+54 11 4444-5555",
        "email": "laura@test.com.ar",
        "password": PASSWORD,
        "matricula": "MN 555",
        "especialidad_ids": [],
    }
    return base | cambios


async def test_registro_medico_tratante_y_luego_ingresa(
    cliente: httpx.AsyncClient, session: AsyncSession, mails: MailMemoria
) -> None:
    esp = await _especialidad(session)
    r = await cliente.get("/auth/especialidades")
    assert r.json() == [{"id": esp, "nombre": "Genética Médica"}]
    r = await cliente.post("/auth/registro", json=_registro(especialidad_ids=[esp]))
    assert r.status_code == 201, r.text
    assert r.json()["rol"] == "MEDICO_TRATANTE"
    datos = await ingresar(cliente, mails, "laura@test.com.ar")
    assert datos["estado"] == "OK"


@pytest.mark.parametrize("rol", ["ADMINISTRATIVO", "BIOINFORMATICO"])
async def test_registro_sin_matricula_para_roles_no_medicos(cliente: httpx.AsyncClient, rol: str) -> None:
    r = await cliente.post(
        "/auth/registro", json=_registro(rol=rol, matricula=None, email=f"{rol.lower()}@test.com.ar")
    )
    assert r.status_code == 201, r.text


async def test_registro_gerente_requiere_matricula_y_especialidad(
    cliente: httpx.AsyncClient, session: AsyncSession
) -> None:
    esp = await _especialidad(session)
    r = await cliente.post("/auth/registro", json=_registro(rol="GERENTE_MEDICO", especialidad_ids=[]))
    assert r.status_code == 422 and r.json()["code"] == "DATOS_PROFESIONALES_FALTANTES"
    r = await cliente.post(
        "/auth/registro", json=_registro(rol="GERENTE_MEDICO", especialidad_ids=[esp + 99])
    )
    assert r.json()["code"] == "ESPECIALIDAD_INVALIDA"
    r = await cliente.post("/auth/registro", json=_registro(rol="GERENTE_MEDICO", especialidad_ids=[esp]))
    assert r.status_code == 201


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"email": "no-es-mail"}, "email"),
        ({"nombre": ""}, "nombre"),
        ({"telefono": "abc"}, "telefono"),
        ({"rol": "PACIENTE"}, "rol"),
        ({"rol": "TRANSPORTISTA"}, "rol"),
    ],
)
async def test_registro_datos_invalidos(
    cliente: httpx.AsyncClient, cambios: dict[str, object], campo: str
) -> None:
    r = await cliente.post("/auth/registro", json=_registro(**cambios))
    assert r.status_code == 422
    assert r.json()["code"] == "DATOS_INVALIDOS"
    assert campo in r.json()["campos"]


async def test_registro_email_y_matricula_duplicados(
    cliente: httpx.AsyncClient, session: AsyncSession
) -> None:
    esp = await _especialidad(session)
    assert (await cliente.post("/auth/registro", json=_registro(especialidad_ids=[esp]))).status_code == 201
    r = await cliente.post("/auth/registro", json=_registro(especialidad_ids=[esp], matricula="MN 999"))
    assert r.status_code == 409 and r.json()["code"] == "EMAIL_EN_USO"
    r = await cliente.post("/auth/registro", json=_registro(especialidad_ids=[esp], email="otra@test.com.ar"))
    assert r.status_code == 409 and r.json()["code"] == "MATRICULA_EN_USO"


async def test_registro_password_debil(cliente: httpx.AsyncClient) -> None:
    r = await cliente.post("/auth/registro", json=_registro(rol="ADMINISTRATIVO", password="1234"))
    assert r.json()["code"] == "PASSWORD_DEBIL"


# --- Autorización por rol -------------------------------------------------------------------


@pytest.fixture
async def ruta_medico(cliente: httpx.AsyncClient) -> httpx.AsyncClient:
    from app.main import app

    if not any(getattr(r, "path", "") == "/_test/medico" for r in app.routes):
        router = APIRouter()

        @router.get("/_test/medico")
        async def solo_medico(
            u: Usuario = Depends(requiere_rol(RolUsuario.MEDICO_TRATANTE)),
        ) -> dict[str, int]:
            return {"id": u.id}

        app.include_router(router)
    return cliente


@pytest.mark.parametrize(
    ("rol", "esperado"),
    [(RolUsuario.MEDICO_TRATANTE, 200)] + [(r, 403) for r in RolUsuario if r != RolUsuario.MEDICO_TRATANTE],
)
async def test_requiere_rol(
    ruta_medico: httpx.AsyncClient, session: AsyncSession, rol: RolUsuario, esperado: int
) -> None:
    u = await crear_usuario(session, rol, f"{rol.value.lower()}@test.com.ar")
    token = security.crear_token(u.id, u.rol, "access")
    r = await ruta_medico.get("/_test/medico", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == esperado
    if esperado == 403:
        assert r.json()["code"] == "SIN_PERMISO"


@pytest.mark.parametrize("cabecera", [None, "Bearer basura", "Basic abc"])
async def test_requiere_rol_sin_sesion(ruta_medico: httpx.AsyncClient, cabecera: str | None) -> None:
    headers = {"Authorization": cabecera} if cabecera else {}
    r = await ruta_medico.get("/_test/medico", headers=headers)
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"
