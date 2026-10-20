from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

PostCommit = Callable[[], Awaitable[Any]]

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


def al_confirmar(session: AsyncSession, accion: PostCommit) -> None:
    """Registra una acción a ejecutar sólo si la transacción se confirma (p. ej. mails con secretos)."""
    session.info.setdefault("post_commit", []).append(accion)


async def ejecutar_post_commit(session: AsyncSession) -> None:
    acciones: list[PostCommit] = session.info.pop("post_commit", [])
    for accion in acciones:
        await accion()


async def get_session() -> AsyncIterator[AsyncSession]:
    """Una transacción por request: commit al final, rollback ante cualquier error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
        await ejecutar_post_commit(session)
