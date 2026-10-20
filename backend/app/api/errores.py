"""Traduce errores a respuestas `{code, message}` en español."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errores import ErrorNegocio


def _cuerpo(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


async def _error_negocio(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ErrorNegocio)
    headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
    return JSONResponse(_cuerpo(exc.code, exc.message), status_code=exc.status, headers=headers)


async def _validacion(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    campos = sorted({".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]) for e in exc.errors()})
    return JSONResponse(
        {**_cuerpo("DATOS_INVALIDOS", f"Revisá estos datos: {', '.join(campos)}."), "campos": campos},
        status_code=422,
    )


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(ErrorNegocio, _error_negocio)
    app.add_exception_handler(RequestValidationError, _validacion)
