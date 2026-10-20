"""Máquina de estados del Estudio (estado_estudio).

Regla pura: qué pares origen→destino existen, qué actor los puede disparar y para qué tipo de Estudio.
La única función que aplica una transición sobre la base es `app.services.transiciones.transicionar`.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from app.domain.enums import EstadoEstudio as E
from app.domain.enums import RolUsuario as R
from app.domain.enums import TipoEstudio
from app.domain.errores import Conflicto, ErrorNegocio

SISTEMA: Final = "SISTEMA"
Actor = R | Literal["SISTEMA"]

HABILITANTES: Final = frozenset({E.PAGADO, E.AUTORIZADO})
"""Estados que habilitan Sacar Turno (E11)."""


@dataclass(frozen=True)
class Regla:
    actores: frozenset[Actor]
    tipos: frozenset[TipoEstudio] = frozenset({TipoEstudio.EXOMA})
    escenario: str = ""


def _r(*actores: Actor, tipos: Iterable[TipoEstudio] = (TipoEstudio.EXOMA,), escenario: str = "") -> Regla:
    return Regla(frozenset(actores), frozenset(tipos), escenario)


TRANSICIONES: Final[dict[tuple[E, E], Regla]] = {
    # Presupuesto (E16)
    (E.CREADO, E.POR_PAGAR): _r(R.ADMINISTRATIVO, escenario="E16"),
    (E.CREADO, E.PENDIENTE_AUTORIZACION): _r(R.ADMINISTRATIVO, escenario="E16"),
    # Obra Social (E17, E18, E10). SUPUESTO S1: autorización parcial deja la diferencia POR_PAGAR.
    (E.PENDIENTE_AUTORIZACION, E.AUTORIZADO): _r(R.ADMINISTRATIVO, escenario="E17"),
    (E.PENDIENTE_AUTORIZACION, E.POR_PAGAR): _r(R.ADMINISTRATIVO, escenario="E17"),
    (E.PENDIENTE_AUTORIZACION, E.RECHAZADO): _r(R.ADMINISTRATIVO, escenario="E18"),
    (E.RECHAZADO, E.PENDIENTE_AUTORIZACION): _r(R.PACIENTE, escenario="E10"),  # SUPUESTO S2
    # Pago (E8)
    (E.POR_PAGAR, E.PAGADO): _r(R.PACIENTE, escenario="E8"),
    # Turno (E11, E12) e inasistencias
    (E.PAGADO, E.TURNO_SACADO): _r(R.PACIENTE, escenario="E11"),
    (E.AUTORIZADO, E.TURNO_SACADO): _r(R.PACIENTE, escenario="E11"),
    (E.TURNO_SACADO, E.PAGADO): _r(R.PACIENTE, SISTEMA, escenario="E12/E11"),
    (E.TURNO_SACADO, E.AUTORIZADO): _r(R.PACIENTE, SISTEMA, escenario="E12/E11"),
    (E.TURNO_SACADO, E.POR_PAGAR): _r(SISTEMA, escenario="E11"),  # 5 inasistencias
    # Tomar Muestra (Centro de Extracción; endpoint pendiente, ver DECISIONES C6)
    (E.TURNO_SACADO, E.LISTO_PARA_RETIRAR): _r(SISTEMA, escenario="Tomar Muestra"),
    # Logística (E24, E25, E20)
    (E.LISTO_PARA_RETIRAR, E.EN_CAMINO_LAB_CENTRAL): _r(R.TRANSPORTISTA, escenario="E24"),
    (E.EN_CAMINO_LAB_CENTRAL, E.EN_LAB_CENTRAL): _r(R.TRANSPORTISTA, escenario="E25"),
    (E.EN_CAMINO_LAB_CENTRAL, E.PAGADO): _r(SISTEMA, escenario="E25"),  # Muestra < 2 ml
    (E.EN_CAMINO_LAB_CENTRAL, E.AUTORIZADO): _r(SISTEMA, escenario="E25"),
    (E.EN_LAB_CENTRAL, E.EN_ESPERA_RETIRO): _r(SISTEMA, escenario="E25"),
    (E.EN_ESPERA_RETIRO, E.EN_VIAJE_COREA): _r(SISTEMA, escenario="E20"),
    # Datos crudos y nueva extracción (E21, E22)
    (E.EN_VIAJE_COREA, E.EN_ANALISIS_BIOINFORMATICA): _r(R.ADMINISTRATIVO, escenario="E21"),
    (E.EN_VIAJE_COREA, E.PAGADO): _r(R.ADMINISTRATIVO, escenario="E22"),  # SUPUESTO S10
    (E.EN_VIAJE_COREA, E.AUTORIZADO): _r(R.ADMINISTRATIVO, escenario="E22"),
    # Reanálisis (E6): reutiliza los datos crudos del Estudio origen. SUPUESTO S3
    (E.CREADO, E.EN_ANALISIS_BIOINFORMATICA): _r(SISTEMA, tipos=(TipoEstudio.REANALISIS,), escenario="E6"),
    # Bioinformática (E27, E28)
    (E.EN_ANALISIS_BIOINFORMATICA, E.EN_ANALISIS): _r(
        R.BIOINFORMATICO, tipos=(TipoEstudio.EXOMA, TipoEstudio.REANALISIS), escenario="E27"
    ),
    (E.EN_ANALISIS, E.FINALIZADO): _r(
        R.BIOINFORMATICO, tipos=(TipoEstudio.EXOMA, TipoEstudio.REANALISIS), escenario="E28"
    ),
}


def validar_transicion(origen: E, destino: E, actor: Actor, tipo: TipoEstudio) -> Regla:
    """Valida el par origen→destino, el actor habilitado y el tipo de Estudio. Devuelve la regla aplicada."""
    regla = TRANSICIONES.get((origen, destino))
    if regla is None:
        raise Conflicto(
            "TRANSICION_INVALIDA",
            f"El Estudio no puede pasar de {etiqueta(origen)} a {etiqueta(destino)}.",
        )
    if tipo not in regla.tipos:
        raise Conflicto(
            "TRANSICION_INVALIDA",
            f"Un Estudio de tipo {tipo.value} no puede pasar de {etiqueta(origen)} a {etiqueta(destino)}.",
        )
    if actor not in regla.actores:
        raise ErrorNegocio(
            "ROL_NO_HABILITADO",
            f"Tu rol no puede pasar el Estudio de {etiqueta(origen)} a {etiqueta(destino)}.",
            status=403,
        )
    return regla


def destinos_posibles(origen: E, tipo: TipoEstudio = TipoEstudio.EXOMA) -> set[E]:
    return {d for (o, d), r in TRANSICIONES.items() if o == origen and tipo in r.tipos}


def estado_habilitante(historial: Sequence[E]) -> E:
    """SUPUESTO S11: al cancelar Turno o re-extraer, el Estudio vuelve al último PAGADO/AUTORIZADO."""
    for estado in reversed(historial):
        if estado in HABILITANTES:
            return estado
    raise Conflicto("SIN_ESTADO_HABILITANTE", "El Estudio nunca estuvo Pagado ni Autorizado.")


_ETIQUETAS: Final[dict[E, str]] = {
    E.CREADO: "Creado",
    E.POR_PAGAR: "Por Pagar",
    E.PENDIENTE_AUTORIZACION: "Pendiente de Autorización",
    E.RECHAZADO: "Rechazado",
    E.PAGADO: "Pagado",
    E.AUTORIZADO: "Autorizado",
    E.TURNO_SACADO: "Turno Sacado",
    E.LISTO_PARA_RETIRAR: "Listo para Retirar",
    E.EN_CAMINO_LAB_CENTRAL: "En camino al Laboratorio Central",
    E.EN_LAB_CENTRAL: "En Laboratorio Central",
    E.EN_ESPERA_RETIRO: "En Espera de Retiro",
    E.EN_VIAJE_COREA: "En viaje a Corea",
    E.EN_ANALISIS_BIOINFORMATICA: "En análisis por bioinformática",
    E.EN_ANALISIS: "En Análisis",
    E.FINALIZADO: "Finalizado",
}


def etiqueta(estado: E) -> str:
    return _ETIQUETAS[estado]


_MENSAJES: Final[dict[E, str]] = {
    E.POR_PAGAR: "Ya tenés disponible el Presupuesto de tu Estudio. Podés pagarlo desde LisoGen.",
    E.PENDIENTE_AUTORIZACION: "El Estudio está esperando la Autorización de la Obra Social.",
    E.RECHAZADO: "La Obra Social rechazó el Estudio. Podés solicitar la reautorización adjuntando "
    "la decisión judicial.",
    E.PAGADO: "El Estudio está pagado. Ya podés Sacar Turno para la extracción.",
    E.AUTORIZADO: "La Obra Social autorizó el Estudio. Ya podés Sacar Turno para la extracción.",
    E.TURNO_SACADO: "Reservamos el Turno de extracción.",
    E.LISTO_PARA_RETIRAR: "La Muestra fue tomada y espera al Transportista.",
    E.EN_CAMINO_LAB_CENTRAL: "La Muestra va en camino al Laboratorio Central.",
    E.EN_LAB_CENTRAL: "La Muestra llegó al Laboratorio Central.",
    E.EN_ESPERA_RETIRO: "La Muestra está en un Lote sellado, esperando el retiro de FedEx.",
    E.EN_VIAJE_COREA: "La Muestra viaja a Corea para la secuenciación.",
    E.EN_ANALISIS_BIOINFORMATICA: "Llegaron los datos crudos; el Estudio espera al equipo de bioinformática.",
    E.EN_ANALISIS: "Un Bioinformático está analizando el Estudio.",
    E.FINALIZADO: "El Resultado del Estudio está disponible.",
}


def mensaje_notificacion(codigo_estudio: str, destino: E, motivo: str | None) -> tuple[str, str]:
    """Asunto y cuerpo del Aviso por cambio de Estado. Sin datos personales del Paciente."""
    asunto = f"Estudio {codigo_estudio}: {etiqueta(destino)}"
    cuerpo = _MENSAJES.get(destino, f"El Estudio pasó a {etiqueta(destino)}.")
    if motivo:
        cuerpo = f"{cuerpo}\nMotivo: {motivo}"
    return asunto, cuerpo
