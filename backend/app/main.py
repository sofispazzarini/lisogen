"""Aplicación FastAPI: chequeo de salud, routers por rol, manejo de errores `{code, message}` y
tareas programadas (APScheduler)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.errores import registrar_manejadores
from app.api.routers import (
    administrativo,
    auth,
    avisos,
    bioinformatico,
    gerente,
    integraciones,
    medico,
    paciente,
    transportista,
)
from app.config import get_settings
from app.db import get_sessionmaker
from app.jobs.scheduler import crear_scheduler


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    scheduler = crear_scheduler() if s.scheduler_activo and s.entorno != "test" else None
    if scheduler is not None:
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="LisoGen API",
    version="0.1.0",
    description="Gestión de Estudios de exoma clínico para Patologías lisosomales.",
    lifespan=ciclo_de_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],  # CORS cerrado al front
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Device-Id"],
)
registrar_manejadores(app)
for router in (
    auth.router,
    avisos.router,
    medico.router,
    paciente.router,
    administrativo.router,
    transportista.router,
    bioinformatico.router,
    gerente.router,
    integraciones.router,
):
    app.include_router(router)


@app.get("/salud", tags=["infra"])
async def salud() -> dict[str, str]:
    async with get_sessionmaker()() as session:
        await session.execute(text("SELECT 1"))
    return {"estado": "ok"}
