"""Errores de negocio. La API los traduce a 409/422 con cuerpo {code, message} en español."""

import unicodedata
from typing import Literal


class ErrorNegocio(Exception):
    """Violación de una regla de negocio. `status` 422 = datos inválidos; 409 = conflicto de estado."""

    def __init__(self, code: str, message: str, status: Literal[401, 403, 404, 409, 422, 429] = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class Conflicto(ErrorNegocio):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status=409)


class NoEncontrado(ErrorNegocio):
    def __init__(self, entidad: str, articulo: Literal["el", "la"] = "el") -> None:
        sin_tildes = unicodedata.normalize("NFKD", entidad).encode("ascii", "ignore").decode()
        codigo = sin_tildes.upper().replace(" ", "_")
        super().__init__(f"{codigo}_NO_ENCONTRADO", f"No encontramos {articulo} {entidad}.", 404)


class SinPermiso(ErrorNegocio):
    def __init__(self, message: str = "No tenés permiso para realizar esta acción.") -> None:
        super().__init__("SIN_PERMISO", message, status=403)
