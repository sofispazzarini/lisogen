"""Fixtures con PostgreSQL real. Cada corrida crea bases nuevas (`<base>_test_*`) y las borra al final.

La URL sale de `TEST_DATABASE_URL` o, si no está, de `DATABASE_URL` (Settings). El usuario tiene que
poder crear bases (en CI y en docker-compose lo es)."""

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import get_settings
from app.db import ejecutar_post_commit, get_session
from app.integrations.infra import MailMemoria
from app.integrations.registro import Adaptadores, Integraciones

BACKEND = Path(__file__).resolve().parents[1]


def pytest_configure(config: pytest.Config) -> None:
    """Mail y archivos en memoria, sin scheduler. Se fija antes de importar la app (Settings se cachea)."""
    for clave, valor in {
        "ENTORNO": "test",
        "MAIL_MODO": "memoria",
        "STORAGE_MODO": "memoria",
        "SCHEDULER_ACTIVO": "false",
    }.items():
        os.environ.setdefault(clave, valor)
    get_settings.cache_clear()


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


@pytest.fixture
def adaptadores() -> Adaptadores:
    return Adaptadores(get_settings())


@pytest.fixture
def mails(adaptadores: Adaptadores) -> MailMemoria:
    assert isinstance(adaptadores.mail, MailMemoria)
    return adaptadores.mail


@pytest.fixture
async def cliente(session: AsyncSession, adaptadores: Adaptadores) -> AsyncIterator[httpx.AsyncClient]:
    """Cliente HTTP contra la app, con la sesión del test (mismo ciclo commit/post-commit que get_session)."""
    from app.api.deps import get_integraciones
    from app.main import app
    from app.services.auth import limitador

    async def _session() -> AsyncIterator[AsyncSession]:
        await session.commit()  # fija los datos que preparó el test antes del request
        # Cada request corre en su SAVEPOINT: si falla, se revierte sólo lo suyo y los objetos que
        # preparó el test no quedan expirados (un rollback completo los expiraría).
        request_tx = await session.begin_nested()
        try:
            yield session
            await session.commit()
        except BaseException:
            if request_tx.is_active:
                await request_tx.rollback()
            else:
                await session.rollback()
            raise
        await ejecutar_post_commit(session)
        await session.commit()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_integraciones] = lambda: Integraciones(session, adaptadores)
    limitador.reiniciar()
    transporte = httpx.ASGITransport(app=app)
    cabeceras = {"User-Agent": "pytest", "X-Device-Id": "dispositivo-de-prueba"}
    async with httpx.AsyncClient(transport=transporte, base_url="http://test", headers=cabeceras) as c:
        yield c
    app.dependency_overrides.clear()
