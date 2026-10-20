"""APScheduler dentro del proceso de la API (hora Argentina). Se desactiva con SCHEDULER_ACTIVO=false.

Con más de una réplica de la API habría que correrlo en un único proceso (las tareas usan
`FOR UPDATE SKIP LOCKED`, así que dos instancias no procesan lo mismo, pero duplicarían trabajo)."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.domain.reglas import TZ_AR
from app.jobs.tareas import ejecutar

PROGRAMACION = {
    # E23: 06:00 de lunes a viernes; la tarea no genera nada si es feriado.
    "orden_del_dia": CronTrigger(day_of_week="mon-fri", hour=6, minute=0, timezone=TZ_AR),
    # Cierre de jornada: después del último Turno (17:45 + 15').
    "cierre_de_jornada": CronTrigger(day_of_week="mon-fri", hour=18, minute=30, timezone=TZ_AR),
    # Recordatorios: el día anterior a las 9:00 (S16); se revisa cada 15' por si la API estuvo caída.
    "recordatorios": IntervalTrigger(minutes=15, timezone=TZ_AR),
    "mails": IntervalTrigger(seconds=15, timezone=TZ_AR),
    "fedex": IntervalTrigger(minutes=1, timezone=TZ_AR),
}


def crear_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=TZ_AR)
    for nombre, trigger in PROGRAMACION.items():
        scheduler.add_job(
            ejecutar,
            trigger,
            args=[nombre],
            id=nombre,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=600,
        )
    return scheduler
