from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.domain.enums import RolUsuario
from app.models import (
    CentroExtraccion,
    DiagnosticoPresuntivo,
    Feriado,
    Gen,
    ObraSocial,
    Paciente,
    PacienteSintoma,
    Patologia,
    PatologiaGen,
    ProfesionalMedico,
    Provincia,
    SnomedConcepto,
    Transportista,
    Usuario,
)
from app.seed import datos
from app.seed.cargar import cargar, vaciar


async def _contar(session: AsyncSession, modelo: type) -> int:
    return int(await session.scalar(select(func.count()).select_from(modelo)) or 0)


async def test_seed_carga_catalogos_y_usuarios(session: AsyncSession) -> None:
    await vaciar(session)
    await cargar(session)
    assert await _contar(session, Provincia) == 24
    assert await _contar(session, Patologia) == 5
    assert await _contar(session, CentroExtraccion) == 10
    assert await _contar(session, ObraSocial) == 3
    assert await _contar(session, Feriado) == 16
    assert await _contar(session, Gen) == 10
    assert await _contar(session, PatologiaGen) == 5
    assert await _contar(session, SnomedConcepto) == len(datos.SNOMED)
    assert await _contar(session, Usuario) == 6
    roles = set(await session.scalars(select(Usuario.rol)))
    assert roles == set(RolUsuario)
    assert await _contar(session, ProfesionalMedico) == 2
    assert await _contar(session, Transportista) == 1


async def test_seed_es_recargable(session: AsyncSession) -> None:
    for _ in range(2):
        await vaciar(session)
        await cargar(session)
    assert await _contar(session, Usuario) == 6
    assert await session.scalar(select(func.min(Provincia.id))) == 1  # secuencias reiniciadas


async def test_usuarios_demo_con_password_demo(session: AsyncSession) -> None:
    await vaciar(session)
    await cargar(session)
    for u in await session.scalars(select(Usuario)):
        assert security.verificar_password(datos.PASSWORD_DEMO, u.password_hash)
        assert not u.debe_cambiar_password


async def test_patologias_y_paciente_demo_validan_diagnostico(session: AsyncSession) -> None:
    await vaciar(session)
    await cargar(session)
    pompe = await session.scalar(select(Patologia).where(Patologia.nombre == "Pompe"))
    assert pompe is not None and pompe.es_pompe
    for p in await session.scalars(select(Patologia)):
        assert len(p.secundarios) >= 2
    paciente = await session.scalar(select(Paciente))
    assert paciente is not None
    sintomas = set(
        await session.scalars(
            select(PacienteSintoma.concept_id).where(PacienteSintoma.paciente_id == paciente.id)
        )
    )
    dx = await session.scalar(
        select(DiagnosticoPresuntivo).where(DiagnosticoPresuntivo.paciente_id == paciente.id)
    )
    assert dx is not None
    patologia = await session.get(Patologia, dx.patologia_id)
    assert patologia is not None and patologia.sintoma_cardinal_id in sintomas


def test_feriados_2026_son_de_2026_y_sin_repetir() -> None:
    fechas = [f for f, _ in datos.FERIADOS_2026]
    assert len(set(fechas)) == len(fechas)
    assert all(f.year == 2026 for f in fechas)
    # Los trasladables caen en lunes
    for f in (date(2026, 6, 15), date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 23)):
        assert f.weekday() == 0


def test_centros_con_coordenadas_dentro_de_argentina() -> None:
    for _, _, _, lat, lon in datos.CENTROS:
        assert -55.1 <= float(lat) <= -21.7
        assert -73.6 <= float(lon) <= -53.6
