"""Máquina de estados del Estudio: tests exhaustivos sobre todos los pares origen→destino."""

import itertools

import pytest

from app.domain.enums import EstadoEstudio as E
from app.domain.enums import RolUsuario as R
from app.domain.enums import TipoEstudio as T
from app.domain.errores import Conflicto, ErrorNegocio
from app.domain.estados import (
    SISTEMA,
    TRANSICIONES,
    destinos_posibles,
    estado_habilitante,
    etiqueta,
    mensaje_notificacion,
    validar_transicion,
)

ACTORES = [*R, SISTEMA]

CAMINO_PRINCIPAL_PARTICULAR = [
    (E.CREADO, E.POR_PAGAR, R.ADMINISTRATIVO),
    (E.POR_PAGAR, E.PAGADO, R.PACIENTE),
    (E.PAGADO, E.TURNO_SACADO, R.PACIENTE),
    (E.TURNO_SACADO, E.LISTO_PARA_RETIRAR, SISTEMA),
    (E.LISTO_PARA_RETIRAR, E.EN_CAMINO_LAB_CENTRAL, R.TRANSPORTISTA),
    (E.EN_CAMINO_LAB_CENTRAL, E.EN_LAB_CENTRAL, R.TRANSPORTISTA),
    (E.EN_LAB_CENTRAL, E.EN_ESPERA_RETIRO, SISTEMA),
    (E.EN_ESPERA_RETIRO, E.EN_VIAJE_COREA, SISTEMA),
    (E.EN_VIAJE_COREA, E.EN_ANALISIS_BIOINFORMATICA, R.ADMINISTRATIVO),
    (E.EN_ANALISIS_BIOINFORMATICA, E.EN_ANALISIS, R.BIOINFORMATICO),
    (E.EN_ANALISIS, E.FINALIZADO, R.BIOINFORMATICO),
]


def test_camino_principal_llega_a_finalizado() -> None:
    estado = E.CREADO
    for origen, destino, actor in CAMINO_PRINCIPAL_PARTICULAR:
        assert estado == origen
        validar_transicion(origen, destino, actor, T.EXOMA)
        estado = destino
    assert estado == E.FINALIZADO


def test_camino_obra_social() -> None:
    validar_transicion(E.CREADO, E.PENDIENTE_AUTORIZACION, R.ADMINISTRATIVO, T.EXOMA)
    validar_transicion(E.PENDIENTE_AUTORIZACION, E.AUTORIZADO, R.ADMINISTRATIVO, T.EXOMA)
    validar_transicion(E.AUTORIZADO, E.TURNO_SACADO, R.PACIENTE, T.EXOMA)


def test_rechazo_y_reautorizacion() -> None:
    validar_transicion(E.PENDIENTE_AUTORIZACION, E.RECHAZADO, R.ADMINISTRATIVO, T.EXOMA)
    validar_transicion(E.RECHAZADO, E.PENDIENTE_AUTORIZACION, R.PACIENTE, T.EXOMA)
    validar_transicion(E.PENDIENTE_AUTORIZACION, E.AUTORIZADO, R.ADMINISTRATIVO, T.EXOMA)


def test_cobertura_parcial_pasa_a_por_pagar() -> None:
    validar_transicion(E.PENDIENTE_AUTORIZACION, E.POR_PAGAR, R.ADMINISTRATIVO, T.EXOMA)


@pytest.mark.parametrize("vuelta", [E.PAGADO, E.AUTORIZADO])
def test_cancelar_turno_vuelve_a_habilitante(vuelta: E) -> None:
    validar_transicion(E.TURNO_SACADO, vuelta, R.PACIENTE, T.EXOMA)
    validar_transicion(E.TURNO_SACADO, vuelta, SISTEMA, T.EXOMA)


def test_cinco_inasistencias_vuelve_a_por_pagar_solo_sistema() -> None:
    validar_transicion(E.TURNO_SACADO, E.POR_PAGAR, SISTEMA, T.EXOMA)
    with pytest.raises(ErrorNegocio) as e:
        validar_transicion(E.TURNO_SACADO, E.POR_PAGAR, R.PACIENTE, T.EXOMA)
    assert e.value.code == "ROL_NO_HABILITADO"


@pytest.mark.parametrize("vuelta", [E.PAGADO, E.AUTORIZADO])
def test_reextraccion_sin_costo(vuelta: E) -> None:
    validar_transicion(E.EN_CAMINO_LAB_CENTRAL, vuelta, SISTEMA, T.EXOMA)  # < 2 ml
    validar_transicion(E.EN_VIAJE_COREA, vuelta, R.ADMINISTRATIVO, T.EXOMA)  # desnaturalizada


def test_reanalisis_saltea_turno_y_logistica() -> None:
    validar_transicion(E.CREADO, E.EN_ANALISIS_BIOINFORMATICA, SISTEMA, T.REANALISIS)
    with pytest.raises(Conflicto):
        validar_transicion(E.CREADO, E.EN_ANALISIS_BIOINFORMATICA, SISTEMA, T.EXOMA)
    with pytest.raises(Conflicto):
        validar_transicion(E.CREADO, E.POR_PAGAR, R.ADMINISTRATIVO, T.REANALISIS)
    validar_transicion(E.EN_ANALISIS_BIOINFORMATICA, E.EN_ANALISIS, R.BIOINFORMATICO, T.REANALISIS)
    validar_transicion(E.EN_ANALISIS, E.FINALIZADO, R.BIOINFORMATICO, T.REANALISIS)


@pytest.mark.parametrize(("origen", "destino"), list(itertools.product(E, E)))
@pytest.mark.parametrize("tipo", list(T))
def test_todos_los_pares(origen: E, destino: E, tipo: T) -> None:
    """Cada par (origen, destino, tipo) es válido exactamente para los actores de la tabla."""
    regla = TRANSICIONES.get((origen, destino))
    for actor in ACTORES:
        permitido = regla is not None and tipo in regla.tipos and actor in regla.actores
        if permitido:
            assert validar_transicion(origen, destino, actor, tipo) is regla
        else:
            with pytest.raises(ErrorNegocio) as e:
                validar_transicion(origen, destino, actor, tipo)
            esperado = (
                "ROL_NO_HABILITADO" if regla is not None and tipo in regla.tipos else "TRANSICION_INVALIDA"
            )
            assert e.value.code == esperado
            assert e.value.status == (403 if esperado == "ROL_NO_HABILITADO" else 409)


def test_finalizado_es_terminal() -> None:
    for tipo in T:
        assert destinos_posibles(E.FINALIZADO, tipo) == set()


def test_ningun_estado_vuelve_a_creado() -> None:
    assert all(d != E.CREADO for (_, d) in TRANSICIONES)


def test_todos_los_estados_son_alcanzables_desde_creado() -> None:
    alcanzados, pendientes = {E.CREADO}, [E.CREADO]
    while pendientes:
        actual = pendientes.pop()
        for tipo in T:
            for d in destinos_posibles(actual, tipo) - alcanzados:
                alcanzados.add(d)
                pendientes.append(d)
    assert alcanzados == set(E)


def test_estado_habilitante_toma_el_ultimo() -> None:
    hist = [E.CREADO, E.PENDIENTE_AUTORIZACION, E.POR_PAGAR, E.PAGADO, E.TURNO_SACADO]
    assert estado_habilitante(hist) == E.PAGADO
    hist2 = [E.CREADO, E.PENDIENTE_AUTORIZACION, E.AUTORIZADO, E.TURNO_SACADO]
    assert estado_habilitante(hist2) == E.AUTORIZADO


def test_estado_habilitante_sin_pago() -> None:
    with pytest.raises(Conflicto):
        estado_habilitante([E.CREADO, E.POR_PAGAR])


def test_etiquetas_y_mensajes_cubren_todos_los_estados() -> None:
    for estado in E:
        assert etiqueta(estado)
        asunto, cuerpo = mensaje_notificacion("EST-2026-000001", estado, None)
        assert "EST-2026-000001" in asunto
        assert cuerpo
    _, cuerpo = mensaje_notificacion("EST-1", E.RECHAZADO, "Sin cobertura genética")
    assert "Motivo: Sin cobertura genética" in cuerpo
