"""Fixtures con PostgreSQL real. Cada corrida crea bases nuevas (`<base>_test_*`) y las borra al final.

La URL sale de `TEST_DATABASE_URL` o, si no está, de `DATABASE_URL` (Settings). El usuario tiene que
poder crear bases (en CI y en docker-compose lo es)."""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import get_settings

BACKEND = Path(__file__).resolve().parents[1]


def url_base() -> str:
    return os.environ.get("TEST_DATABASE_URL") or get_settings().database_url


def url_para(nombre_db: str, driver: str = "postgresql+asyncpg") -> str:
    return (
        make_url(url_base()).set(drivername=driver, database=nombre_db).render_as_string(hide_password=False)
    )


def url_libpq(nombre_db: str) -> str:
    return url_para(nombre_db, "postgresql")


def _admin() -> psycopg.Connection:
    return psycopg.connect(url_libpq("postgres"), autocommit=True)


def crear_base(nombre: str) -> None:
    with _admin() as c:
        c.execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{nombre}"')


def borrar_base(nombre: str) -> None:
    with _admin() as c:
        c.execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')


def alembic_config(nombre_db: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url_para(nombre_db, "postgresql+psycopg"))
    return cfg


@pytest.fixture(scope="session")
def nombre_base() -> Iterator[str]:
    """Base migrada a `head`, compartida por toda la corrida."""
    nombre = f"{make_url(url_base()).database}_test_{os.getpid()}"
    crear_base(nombre)
    command.upgrade(alembic_config(nombre), "head")
    yield nombre
    borrar_base(nombre)


@pytest.fixture(scope="session")
async def engine(nombre_base: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(url_para(nombre_base))
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Sesión dentro de una transacción que se revierte al final: cada test arranca con la base vacía.
    Los commit() del código bajo prueba sólo liberan savepoints."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        s = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield s
        finally:
            await s.close()
            await trans.rollback()
