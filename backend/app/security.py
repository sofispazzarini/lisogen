import hashlib
import hmac
import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings

_hasher = PasswordHasher()

TipoToken = Literal["access", "refresh", "verificacion", "cambio_password"]


def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# Hash que se usa cuando el email no existe, para que el tiempo de respuesta no revele cuentas.
_HASH_SENUELO = _hasher.hash(secrets.token_urlsafe(16))


def verificar_password_senuelo(password: str) -> None:
    verificar_password(password, _HASH_SENUELO)


def password_provisoria() -> str:
    alfabeto = string.ascii_letters + string.digits
    while True:
        p = "".join(secrets.choice(alfabeto) for _ in range(12))
        if any(c.isdigit() for c in p) and any(c.isalpha() for c in p):
            return p


def password_es_robusta(password: str) -> bool:
    return len(password) >= 10 and any(c.isdigit() for c in password) and any(c.isalpha() for c in password)


def codigo_verificacion() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_codigo(codigo: str) -> str:
    return hmac.new(get_settings().jwt_secret.encode(), codigo.encode(), hashlib.sha256).hexdigest()


def huella_dispositivo(user_agent: str, device_id: str) -> str:
    return hashlib.sha256(f"{user_agent}|{device_id}".encode()).hexdigest()


def crear_token(usuario_id: int, rol: str, tipo: TipoToken) -> str:
    s = get_settings()
    duracion = {
        "access": timedelta(minutes=s.jwt_access_min),
        "refresh": timedelta(days=s.jwt_refresh_dias),
        "verificacion": timedelta(minutes=s.jwt_desafio_min),
        "cambio_password": timedelta(minutes=s.jwt_desafio_min),
    }[tipo]
    ahora = datetime.now(UTC)
    payload = {"sub": str(usuario_id), "rol": rol, "typ": tipo, "iat": ahora, "exp": ahora + duracion}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def leer_token(token: str, tipo: TipoToken) -> dict[str, Any] | None:
    try:
        payload: dict[str, Any] = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != tipo:
        return None
    return payload


def token_webhook(recurso: str, recurso_id: int) -> str:
    """Token HMAC no adivinable para URLs de webhooks externos (FedEx)."""
    msg = f"{recurso}:{recurso_id}".encode()
    return hmac.new(get_settings().jwt_secret.encode(), msg, hashlib.sha256).hexdigest()[:40]


def verificar_token_webhook(recurso: str, recurso_id: int, token: str) -> bool:
    return hmac.compare_digest(token_webhook(recurso, recurso_id), token)


def hmac_igual(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
