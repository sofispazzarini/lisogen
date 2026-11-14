"""Adaptadores falsos para probar cómo reacciona LisoGen cuando un módulo externo responde mal."""

from datetime import date
from decimal import Decimal

from app.integrations.mock import ChatbotMock, CuponesMock, ObrasSocialesMock
from app.integrations.ports import (
    CuponExterno,
    ErrorChatbot,
    ErrorCupones,
    ErrorObraSocial,
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
