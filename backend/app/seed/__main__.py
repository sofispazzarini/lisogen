"""`python -m app.seed`: vacía la base y recarga los datos de ejemplo."""

import asyncio

from app.db import get_engine, get_sessionmaker
from app.integrations.registro import Integraciones, get_adaptadores
from app.seed.cargar import cargar, vaciar
from app.seed.datos import PASSWORD_DEMO, USUARIOS
from app.seed.estudios import cargar_estudios


async def main() -> None:
    async with get_sessionmaker()() as session, session.begin():
        await vaciar(session)
        await cargar(session)
        await cargar_estudios(session, Integraciones(session, get_adaptadores()))
    await get_engine().dispose()
    print("Seed cargado. Usuarios demo (contraseña " + PASSWORD_DEMO + "):")
    for u in USUARIOS:
        print(f"  {u.rol.value:<16} {u.email}")


if __name__ == "__main__":
    asyncio.run(main())
