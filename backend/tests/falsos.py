"""Adaptadores falsos para probar cómo reacciona LisoGen cuando un módulo externo responde mal."""

from app.integrations.mock import ChatbotMock, CuponesMock
from app.integrations.ports import CuponExterno, ErrorChatbot, ErrorCupones, RespuestaChat


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
