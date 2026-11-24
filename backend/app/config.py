from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

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

    apigen_modo: Literal["mock", "api"] = "mock"
    apigen_api_url: str = "https://edmrjmfjklwgazzztjcl.supabase.co/rest/v1"
    apigen_api_key: str = ""

    # Cupones (API de Exoma Care): la clave es del grupo; va en .env, nunca en el repositorio
    cupones_modo: Literal["mock", "api"] = "mock"
    cupones_api_url: str = "https://vekuhonbpqtzakqbcoph.supabase.co/functions/v1/cupones-api"
    cupones_api_key: str = ""

    # Obras Sociales (API del módulo 6): la clave es del grupo; va en .env, nunca en el repositorio
    obras_sociales_modo: Literal["mock", "api"] = "mock"
    obras_sociales_api_url: str = "https://bxsvmfesrtjrqubblgws.supabase.co/functions/v1/api"
    obras_sociales_api_key: str = ""

    # Síntomas SNOMED CT (API de terminología): la clave es del grupo; va en .env, nunca en el repositorio
    snomed_modo: Literal["cache", "api"] = "cache"
    snomed_api_url: str = "https://hwmpslajqivdqeaylhdc.supabase.co/functions/v1/terminologia/sintomas"
    snomed_api_key: str = ""

    # Familiograma (API del Laboratorio): la clave va en .env, nunca en el repositorio
    familiograma_modo: Literal["mock", "api"] = "mock"
    familiograma_api_url: str = "https://cnylfdemauswqeqmvwmz.supabase.co/functions/v1/familiograma"
    familiograma_api_key: str = ""

    # Chatbot (GenLab): la apikey y el token van en .env, nunca en el repositorio
    chatbot_modo: Literal["mock", "api"] = "mock"
    chatbot_url: str = "https://vglzngsrbyagquqqmakf.supabase.co/functions/v1/chat"
    chatbot_apikey: str = ""
    chatbot_token: str = ""

    # FedEx: "api" consume la API de retiros (DECISIONES T26)
    fedex_modo: Literal["mock", "api"] = "mock"
    fedex_api_url: str = ""
    fedex_usuario: str = ""
    fedex_password: str = ""
    fedex_lugar_retiro: str = "La Plata, Buenos Aires"

    # Mail (Mailpit en local)
    mail_modo: Literal["smtp", "memoria", "api"] = "smtp"
    mail_api_url: str = ""
    mail_api_key: str = ""
    mail_dominio_demo: str = "lisogen-demo.com.ar"
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


    # Laboratorio Central: calle 62 N° 555, La Plata
    lab_central_lat: Decimal = Decimal("-34.919223")
    lab_central_lon: Decimal = Decimal("-57.942838")
    rutas_modo: Literal["mock", "api"] = "mock"
    rutas_api_url: str = "https://optimizacionapi.vercel.app/api/optimizacion"

    scheduler_activo: bool = True

    @model_validator(mode="after")
    def _fedex_real_configurado(self) -> "Settings":
        credenciales = self.fedex_api_url and self.fedex_usuario and self.fedex_password
        if self.fedex_modo == "api" and not credenciales:
            raise ValueError("FEDEX_MODO=api requiere FEDEX_API_URL, FEDEX_USUARIO y FEDEX_PASSWORD")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
