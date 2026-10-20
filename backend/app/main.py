"""Aplicación FastAPI. En esta etapa sólo expone el chequeo de salud; los routers por rol se suman
en las etapas siguientes."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import get_sessionmaker

app = FastAPI(
    title="LisoGen API",
    version="0.1.0",
    description="Gestión de Estudios de exoma clínico para Patologías lisosomales.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],  # CORS cerrado al front
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Device-Id"],
)


@app.get("/salud", tags=["infra"])
async def salud() -> dict[str, str]:
    async with get_sessionmaker()() as session:
        await session.execute(text("SELECT 1"))
    return {"estado": "ok"}
