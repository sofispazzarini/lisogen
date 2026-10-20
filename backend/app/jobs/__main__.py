"""`python -m app.jobs <tarea>`: corre una tarea programada a mano (útil en la demo, p. ej. orden_del_dia)."""

import asyncio
import logging
import sys

from app.db import get_engine
from app.jobs.tareas import TAREAS, ejecutar


async def main(nombre: str) -> None:
    cantidad = await ejecutar(nombre)
    await get_engine().dispose()
    print(f"{nombre}: {cantidad} procesados")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) != 2 or sys.argv[1] not in TAREAS:
        print(f"Uso: python -m app.jobs <{'|'.join(TAREAS)}>")
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
