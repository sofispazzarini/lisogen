import jwt
import pytest

from app import security
from app.config import get_settings


def test_hash_argon2_y_verificacion() -> None:
    h = security.hashear_password("Demo-2026!")
    assert h.startswith("$argon2")
    assert security.verificar_password("Demo-2026!", h)
    assert not security.verificar_password("demo-2026!", h)
    assert not security.verificar_password("Demo-2026!", "no-es-un-hash")


@pytest.mark.parametrize(
    ("password", "robusta"),
    [
        ("Demo-2026!", True),
        ("abcdefghij1", True),
        ("abcdefghij", False),
        ("1234567890", False),
        ("Ab1", False),
    ],
)
def test_password_robusta(password: str, robusta: bool) -> None:
    assert security.password_es_robusta(password) is robusta


def test_password_provisoria_cumple_la_politica() -> None:
    for _ in range(50):
        assert security.password_es_robusta(security.password_provisoria() + "x")
        assert len(security.password_provisoria()) == 12


def test_codigo_verificacion_de_6_digitos_y_hash_estable() -> None:
    c = security.codigo_verificacion()
    assert len(c) == 6 and c.isdigit()
    assert security.hash_codigo(c) == security.hash_codigo(c)
    assert security.hash_codigo(c) != c


def test_tokens_por_tipo() -> None:
    t = security.crear_token(7, "PACIENTE", "access")
    payload = security.leer_token(t, "access")
    assert payload is not None and payload["sub"] == "7" and payload["rol"] == "PACIENTE"
    assert security.leer_token(t, "refresh") is None
    assert security.leer_token("basura", "access") is None


def test_token_con_otra_firma_es_invalido() -> None:
    falso = jwt.encode(
        {"sub": "1", "rol": "GERENTE_MEDICO", "typ": "access"}, "otra-clave-de-al-menos-32-bytes!!", "HS256"
    )
    assert security.leer_token(falso, "access") is None


def test_token_vencido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "jwt_access_min", -1)
    assert security.leer_token(security.crear_token(1, "PACIENTE", "access"), "access") is None


def test_huella_depende_de_user_agent_y_dispositivo() -> None:
    a = security.huella_dispositivo("Firefox", "d1")
    assert a == security.huella_dispositivo("Firefox", "d1")
    assert a != security.huella_dispositivo("Firefox", "d2")
    assert a != security.huella_dispositivo("Chrome", "d1")


def test_token_webhook() -> None:
    t = security.token_webhook("lote", 3)
    assert security.verificar_token_webhook("lote", 3, t)
    assert not security.verificar_token_webhook("lote", 4, t)
