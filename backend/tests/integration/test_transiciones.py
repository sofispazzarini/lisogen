"""`transicionar`: único punto que cambia estudio.estado, escribe el historial y avisa (APP + MAIL)
al Paciente y al Médico Tratante."""

import itertools
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import CanalNotif, RolUsuario, TipoEstudio
from app.domain.enums import EstadoEstudio as E
from app.domain.errores import Conflicto, ErrorNegocio
from app.models import Estudio, EstudioEstadoHistorial, Notificacion, Paciente, Usuario
from app.services.transiciones import transicionar, volver_a_habilitante
from tests import factories


@dataclass
class Actores:
    medico: Usuario
    administrativo: Usuario
    transportista: Usuario
    bioinformatico: Usuario
    paciente_cuenta: Usuario
    paciente: Paciente


@pytest.fixture
async def actores(session: AsyncSession) -> Actores:
    medico = await factories.usuario(session, RolUsuario.MEDICO_TRATANTE)
    paciente = await factories.paciente(session, medico)
    cuenta = await session.get(Usuario, paciente.usuario_id)
    assert cuenta is not None
    return Actores(
        medico=medico,
        administrativo=await factories.usuario(session, RolUsuario.ADMINISTRATIVO),
        transportista=await factories.usuario(session, RolUsuario.TRANSPORTISTA),
        bioinformatico=await factories.usuario(session, RolUsuario.BIOINFORMATICO),
        paciente_cuenta=cuenta,
        paciente=paciente,
    )


async def _historial(session: AsyncSession, estudio: Estudio) -> list[EstudioEstadoHistorial]:
    return list(
        await session.scalars(
            select(EstudioEstadoHistorial)
            .where(EstudioEstadoHistorial.estudio_id == estudio.id)
            .order_by(EstudioEstadoHistorial.id)
        )
    )


async def _notificaciones(session: AsyncSession, estudio: Estudio) -> list[Notificacion]:
    return list(
        await session.scalars(
            select(Notificacion).where(Notificacion.estudio_id == estudio.id).order_by(Notificacion.id)
        )
    )


async def test_transicion_valida_cambia_estado_escribe_historial_y_avisa(
    session: AsyncSession, actores: Actores
) -> None:
    estudio = await factories.estudio(session, actores.paciente, actores.medico)
    await transicionar(session, estudio, E.POR_PAGAR, actores.administrativo, "Presupuesto emitido")

    assert estudio.estado == E.POR_PAGAR
    hist = await _historial(session, estudio)
    assert [(h.estado_anterior, h.estado_nuevo) for h in hist] == [(None, E.CREADO), (E.CREADO, E.POR_PAGAR)]
    assert hist[-1].usuario_id == actores.administrativo.id
    assert hist[-1].motivo == "Presupuesto emitido"

    notifs = await _notificaciones(session, estudio)
    assert {(n.usuario_id, n.canal) for n in notifs} == {
        (actores.paciente_cuenta.id, CanalNotif.APP),
        (actores.paciente_cuenta.id, CanalNotif.MAIL),
        (actores.medico.id, CanalNotif.APP),
        (actores.medico.id, CanalNotif.MAIL),
    }
    assert all(estudio.codigo in n.asunto and "Por Pagar" in n.asunto for n in notifs)
    assert all("Motivo: Presupuesto emitido" in n.cuerpo for n in notifs)


async def test_avisos_sin_datos_personales_del_paciente(session: AsyncSession, actores: Actores) -> None:
    estudio = await factories.estudio(session, actores.paciente, actores.medico)
    await transicionar(session, estudio, E.POR_PAGAR, actores.administrativo)
    for n in await _notificaciones(session, estudio):
        texto = n.asunto + n.cuerpo
        assert actores.paciente.apellido not in texto
        assert actores.paciente.dni not in texto


async def test_paciente_sin_cuenta_solo_avisa_al_medico(session: AsyncSession, actores: Actores) -> None:
    sin_cuenta = await factories.paciente(session, actores.medico, con_cuenta=False)
    estudio = await factories.estudio(session, sin_cuenta, actores.medico)
    await transicionar(session, estudio, E.POR_PAGAR, actores.administrativo)
    assert {n.usuario_id for n in await _notificaciones(session, estudio)} == {actores.medico.id}


async def test_transicion_invalida_no_cambia_nada(session: AsyncSession, actores: Actores) -> None:
    estudio = await factories.estudio(session, actores.paciente, actores.medico)
    with pytest.raises(Conflicto) as e:
        await transicionar(session, estudio, E.PAGADO, actores.paciente_cuenta)
    assert e.value.code == "TRANSICION_INVALIDA" and e.value.status == 409
    assert estudio.estado == E.CREADO
    assert len(await _historial(session, estudio)) == 1
    assert await _notificaciones(session, estudio) == []


async def test_rol_no_habilitado_es_403(session: AsyncSession, actores: Actores) -> None:
    estudio = await factories.estudio(session, actores.paciente, actores.medico)
    with pytest.raises(ErrorNegocio) as e:
        await transicionar(session, estudio, E.POR_PAGAR, actores.paciente_cuenta)
    assert e.value.code == "ROL_NO_HABILITADO" and e.value.status == 403
    assert estudio.estado == E.CREADO


async def test_proceso_automatico_queda_sin_usuario(session: AsyncSession, actores: Actores) -> None:
    estudio = await factories.estudio(session, actores.paciente, actores.medico)
    for destino, actor in ((E.POR_PAGAR, actores.administrativo), (E.PAGADO, actores.paciente_cuenta)):
        await transicionar(session, estudio, destino, actor)
    await transicionar(session, estudio, E.TURNO_SACADO, actores.paciente_cuenta)
    await transicionar(session, estudio, E.LISTO_PARA_RETIRAR, None, "Muestra tomada")
    assert (await _historial(session, estudio))[-1].usuario_id is None


async def test_asignacion_directa_del_estado_esta_prohibida(session: AsyncSession, actores: Actores) -> None:
    estudio = await factories.estudio(session, actores.paciente, actores.medico)
    with pytest.raises(RuntimeError, match="transicionar"):
        estudio.estado = E.PAGADO
    assert estudio.estado == E.CREADO


async def test_lock_optimista_detecta_modificacion_concurrente(
    session: AsyncSession, actores: Actores
) -> None:
    estudio = await factories.estudio(session, actores.paciente, actores.medico)
    version = estudio.version
    await transicionar(session, estudio, E.POR_PAGAR, actores.administrativo)
    assert estudio.version == version + 1

    # Otra transacción modificó el Estudio después de leerlo
    await session.execute(text("UPDATE estudio SET version = version + 1 WHERE id = :id"), {"id": estudio.id})
    with pytest.raises(Conflicto) as e:
        await transicionar(session, estudio, E.PAGADO, actores.paciente_cuenta)
    assert e.value.code == "ESTUDIO_MODIFICADO"


async def _llevar(session: AsyncSession, estudio: Estudio, pasos: list[tuple[E, Usuario | None]]) -> None:
    for destino, actor in pasos:
        await transicionar(session, estudio, destino, actor)


async def test_volver_a_habilitante_particular_y_obra_social(session: AsyncSession, actores: Actores) -> None:
    a = actores
    particular = await factories.estudio(session, a.paciente, a.medico)
    await _llevar(
        session,
        particular,
        [(E.POR_PAGAR, a.administrativo), (E.PAGADO, a.paciente_cuenta), (E.TURNO_SACADO, a.paciente_cuenta)],
    )
    assert (
        await volver_a_habilitante(session, particular, a.paciente_cuenta, "Cancelación de Turno") == E.PAGADO
    )
    assert particular.estado == E.PAGADO

    con_os = await factories.estudio(session, a.paciente, a.medico)
    await _llevar(
        session,
        con_os,
        [
            (E.PENDIENTE_AUTORIZACION, a.administrativo),
            (E.AUTORIZADO, a.administrativo),
            (E.TURNO_SACADO, a.paciente_cuenta),
        ],
    )
    assert await volver_a_habilitante(session, con_os, None, "Inasistencia") == E.AUTORIZADO


async def test_camino_principal_completo_hasta_finalizado(session: AsyncSession, actores: Actores) -> None:
    a = actores
    estudio = await factories.estudio(session, a.paciente, a.medico)
    await _llevar(
        session,
        estudio,
        [
            (E.POR_PAGAR, a.administrativo),
            (E.PAGADO, a.paciente_cuenta),
            (E.TURNO_SACADO, a.paciente_cuenta),
            (E.LISTO_PARA_RETIRAR, None),
            (E.EN_CAMINO_LAB_CENTRAL, a.transportista),
            (E.EN_LAB_CENTRAL, a.transportista),
            (E.EN_ESPERA_RETIRO, None),
            (E.EN_VIAJE_COREA, None),
            (E.EN_ANALISIS_BIOINFORMATICA, a.administrativo),
        ],
    )
    estudio.bioinformatico_id = a.bioinformatico.id  # CHECK del schema: EN_ANALISIS requiere Bioinformático
    await _llevar(session, estudio, [(E.EN_ANALISIS, a.bioinformatico), (E.FINALIZADO, a.bioinformatico)])

    assert estudio.estado == E.FINALIZADO
    assert estudio.finalizado_at is not None
    hist = await _historial(session, estudio)
    assert len(hist) == 12
    assert all(h.estado_anterior == prev.estado_nuevo for prev, h in itertools.pairwise(hist))
    total = await session.scalar(
        select(func.count()).select_from(Notificacion).where(Notificacion.estudio_id == estudio.id)
    )
    assert total == 11 * 4  # 11 transiciones x (Paciente + Médico) x (APP + MAIL)


async def test_reanalisis_pasa_directo_a_bioinformatica(session: AsyncSession, actores: Actores) -> None:
    a = actores
    origen = await factories.estudio(session, a.paciente, a.medico)
    reanalisis = await factories.estudio(
        session, a.paciente, a.medico, tipo=TipoEstudio.REANALISIS, origen=origen
    )
    await transicionar(session, reanalisis, E.EN_ANALISIS_BIOINFORMATICA, None, "Reanálisis")
    assert reanalisis.estado == E.EN_ANALISIS_BIOINFORMATICA
    with pytest.raises(Conflicto):
        await transicionar(session, origen, E.EN_ANALISIS_BIOINFORMATICA, None)
