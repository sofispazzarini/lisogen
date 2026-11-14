"""`python -m app.seed`: vacía la base y recarga los datos de ejemplo."""

import asyncio

from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.integrations.registro import Adaptadores, Integraciones
from app.seed.cargar import cargar, vaciar
from app.seed.datos import PASSWORD_DEMO, USUARIOS
from app.seed.estudios import cargar_estudios


async def main() -> None:
    # El seed arma Presupuestos, Autorizaciones y Cupones de ejemplo: no debe crear nada en las APIs reales.
    settings = get_settings().model_copy(update={"cupones_modo": "mock", "obras_sociales_modo": "mock"})
    async with get_sessionmaker()() as session, session.begin():
        await vaciar(session)
        await cargar(session)
        await cargar_estudios(session, Integraciones(session, Adaptadores(settings)))
    await get_engine().dispose()
    print("Seed cargado. Usuarios demo (contraseña " + PASSWORD_DEMO + "):")
    for u in USUARIOS:
        print(f"  {u.rol.value:<16} {u.email}")


if __name__ == "__main__":
    asyncio.run(main())
