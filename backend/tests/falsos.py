"""Adaptadores falsos para probar cómo reacciona LisoGen cuando un módulo externo responde mal."""

from datetime import date
from decimal import Decimal

from app.integrations.mock import ChatbotMock, CuponesMock, FamiliogramaMock, ObrasSocialesMock
from app.integrations.ports import (
    ConceptoSnomed,
    CuponExterno,
    DetalleError,
    ErrorChatbot,
    ErrorCupones,
    ErrorFamiliograma,
    ErrorObraSocial,
    ErrorSnomed,
    Familiograma,
    PersonaFamiliograma,
    ReglaSospecha,
    RespuestaChat,
    SolicitudExterna,
)


class CuponesFalla(CuponesMock):
    """Cupones que anda bien hasta que `operacion` recibe su llamada número `desde` (la primera es 1):
    desde ahí responde `error`, como si la API de Cupones rechazara el pedido."""

    def __init__(self, operacion: str, error: ErrorCupones, desde: int = 1) -> None:
        self._operacion = operacion
        self._error = error
        self._desde = desde
        self._llamadas = 0

    def _pasa(self, operacion: str) -> None:
        if operacion != self._operacion:
            return
        self._llamadas += 1
        if self._llamadas >= self._desde:
            raise self._error

    async def generar(self, *, gerente_id: int, descuento_pct: int, cantidad: int) -> list[CuponExterno]:
        self._pasa("generar")
        return await super().generar(gerente_id=gerente_id, descuento_pct=descuento_pct, cantidad=cantidad)

    async def asignar_a_medico(self, *, gerente_id: int, medico_id: int, codigo: str) -> None:
        self._pasa("asignar_a_medico")

    async def asignar_a_paciente(self, *, medico_id: int, paciente_id: int, codigo: str) -> None:
        self._pasa("asignar_a_paciente")

    async def canjear(self, *, paciente_id: int, codigo: str) -> None:
        self._pasa("canjear")


class ChatbotFalla(ChatbotMock):
    """Chatbot que siempre responde `error`, como si el servicio externo estuviera caído o limitado."""

    def __init__(self, error: ErrorChatbot) -> None:
        self._error = error

    async def responder(self, *, pregunta: str, conversacion_id: str | None = None) -> RespuestaChat:
        raise self._error


class ObrasSocialesFalla(ObrasSocialesMock):
    """Obras Sociales que anda bien hasta que `operacion` recibe su llamada número `desde` (la primera es 1):
    desde ahí responde `error`, como si la API de Obras Sociales rechazara el pedido."""

    def __init__(self, operacion: str, error: ErrorObraSocial, desde: int = 1) -> None:
        self._operacion = operacion
        self._error = error
        self._desde = desde
        self._llamadas = 0

    def _pasa(self, operacion: str) -> None:
        if operacion != self._operacion:
            return
        self._llamadas += 1
        if self._llamadas >= self._desde:
            raise self._error

    async def cobertura(self, *, codigo_obra_social: str, cantidad_genes: int) -> Decimal:
        self._pasa("cobertura")
        return await super().cobertura(codigo_obra_social=codigo_obra_social, cantidad_genes=cantidad_genes)

    async def solicitar(
        self, *, codigo_obra_social: str, paciente_nombre: str, fecha: date, referencia: str
    ) -> SolicitudExterna:
        self._pasa("solicitar")
        return await super().solicitar(
            codigo_obra_social=codigo_obra_social,
            paciente_nombre=paciente_nombre,
            fecha=fecha,
            referencia=referencia,
        )

    async def autorizar(
        self, *, solicitud: SolicitudExterna, porcentaje: Decimal | None = None
    ) -> SolicitudExterna:
        self._pasa("autorizar")
        return await super().autorizar(solicitud=solicitud, porcentaje=porcentaje)

    async def rechazar(self, *, solicitud: SolicitudExterna, motivo: str) -> SolicitudExterna:
        self._pasa("rechazar")
        return await super().rechazar(solicitud=solicitud, motivo=motivo)

    async def presentar_demanda(
        self, *, solicitud: SolicitudExterna, nombre_archivo: str, contenido: bytes
    ) -> SolicitudExterna:
        self._pasa("presentar_demanda")
        return await super().presentar_demanda(
            solicitud=solicitud, nombre_archivo=nombre_archivo, contenido=contenido
        )


class SnomedFalso:
    """API de síntomas que sugiere siempre los mismos conceptos, como si fueran de SNOMED."""

    def __init__(self, conceptos: list[ConceptoSnomed]) -> None:
        self._conceptos = conceptos

    async def buscar(self, *, texto: str, limite: int = 20) -> list[ConceptoSnomed]:
        return self._conceptos


class SnomedFalla:
    """API de síntomas que no responde."""

    def __init__(self, error: ErrorSnomed) -> None:
        self._error = error

    async def buscar(self, *, texto: str, limite: int = 20) -> list[ConceptoSnomed]:
        raise self._error


class FamiliogramaFalla(FamiliogramaMock):
    """Familiograma que responde `error`; guarda las personas recibidas para revisar el árbol enviado."""

    def __init__(self, error: ErrorFamiliograma) -> None:
        self.error = error
        self.recibidas: list[PersonaFamiliograma] = []

    async def generar(
        self, *, personas: list[PersonaFamiliograma], regla_sospecha: ReglaSospecha = "desactivada"
    ) -> Familiograma:
        self.recibidas = personas
        raise self.error


class FamiliogramaConReglas(FamiliogramaMock):
    """Imita las reglas de vínculos de la API real: el tío/a paterno/a (6) necesita un abuelo/a paterno/a
    (4), el primo/a paterno/a (8) un tío/a paterno/a (6), y no puede haber más de dos progenitores (1)."""

    def __init__(self) -> None:
        self.pedidos: list[list[int]] = []

    async def generar(
        self, *, personas: list[PersonaFamiliograma], regla_sospecha: ReglaSospecha = "desactivada"
    ) -> Familiograma:
        codigos = [p.parentesco for p in personas]
        self.pedidos.append(codigos)
        if codigos.count(1) > 2:
            i = [k for k, c in enumerate(codigos) if c == 1][2]
            raise _rechazo(i, "MAS_DE_DOS_PROGENITORES: hay más de dos progenitores.")
        detalles = [
            DetalleError(f"personas.{i}.parentesco", f"FALTA_PERSONA_DE_REFERENCIA: {falta}")
            for i, c in enumerate(codigos)
            for necesita, falta in (
                (6, "necesita un abuelo/a paterno/a."),
                (8, "necesita un tío/a paterno/a."),
            )
            if c == necesita and (necesita - 2) not in codigos
        ]
        if detalles:
            raise ErrorFamiliograma(
                "HTTP 422", status=422, codigo="ENTRADA_INVALIDA", detalles=tuple(detalles)
            )
        return await super().generar(personas=personas, regla_sospecha=regla_sospecha)


def _rechazo(i: int, mensaje: str) -> ErrorFamiliograma:
    return ErrorFamiliograma(
        "HTTP 422",
        status=422,
        codigo="ENTRADA_INVALIDA",
        detalles=(DetalleError(f"personas.{i}.parentesco", mensaje),),
    )
