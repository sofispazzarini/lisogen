from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    entorno: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+asyncpg://lisogen:lisogen@localhost:5432/lisogen"

    jwt_secret: str = "cambiar-en-produccion-con-32-bytes-o-mas"
    jwt_access_min: int = 15
    jwt_refresh_dias: int = 7
    jwt_desafio_min: int = 10

    web_origin: str = "http://localhost:5173"
    api_public_url: str = "http://localhost:8000"

    # Integraciones: "mock" es el único modo implementado (DECISIONES T6)
    integraciones_modo: Literal["mock"] = "mock"
    mock_cupones_sin_qr: bool = False

    # Mail (Mailpit en local)
    mail_modo: Literal["smtp", "memoria"] = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    mail_remitente: str = "LisoGen <no-responder@lisogen-demo.com.ar>"

    # Archivos (MinIO privado, URLs firmadas)
    storage_modo: Literal["minio", "memoria"] = "minio"
    minio_endpoint: str = "localhost:9000"
    minio_public_endpoint: str = "localhost:9000"
    minio_access_key: str = "lisogen"
    minio_secret_key: str = "lisogen-secret"
    minio_bucket: str = "lisogen-privado"
    minio_secure: bool = False
    url_firmada_segundos: int = 300

    # Seguridad
    verificar_dispositivo: bool = True
    rate_limit_intentos: int = 5
    rate_limit_ventana_seg: int = 300

    # Laboratorio Central (origen de recorridos y ubicación de Muestras en el laboratorio)
    lab_central_lat: Decimal = Decimal("-34.603722")
    lab_central_lon: Decimal = Decimal("-58.381592")

    scheduler_activo: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
