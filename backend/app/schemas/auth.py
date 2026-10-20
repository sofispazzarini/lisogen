from typing import Literal

from pydantic import EmailStr, Field

from app.domain.enums import RolUsuario
from app.schemas.comun import Esquema


class LoginEntrada(Esquema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class VerificarEntrada(Esquema):
    desafio_token: str
    codigo: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class CambioPasswordEntrada(Esquema):
    password_nueva: str = Field(min_length=1, max_length=200)
    desafio_token: str | None = None
    password_actual: str | None = None


class RefreshEntrada(Esquema):
    refresh_token: str


class UsuarioSalida(Esquema):
    id: int
    email: str
    rol: RolUsuario
    nombre: str
    apellido: str


class IngresoSalida(Esquema):
    estado: Literal["OK", "VERIFICACION_REQUERIDA", "CAMBIO_PASSWORD_REQUERIDO"]
    access_token: str | None = None
    refresh_token: str | None = None
    desafio_token: str | None = None
    usuario: UsuarioSalida | None = None


class RegistroEntrada(Esquema):
    rol: Literal["MEDICO_TRATANTE", "ADMINISTRATIVO", "BIOINFORMATICO", "GERENTE_MEDICO"]
    nombre: str = Field(min_length=1, max_length=100)
    apellido: str = Field(min_length=1, max_length=100)
    telefono: str = Field(min_length=6, max_length=30, pattern=r"^[0-9 +()-]+$")
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    matricula: str | None = Field(default=None, max_length=30)
    especialidad_ids: list[int] = Field(default_factory=list)
