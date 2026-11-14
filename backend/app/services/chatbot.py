"""E14 Consultar Chatbot: módulo externo que responde sobre las cinco Patologías y no deriva a personas.

La conversación (`conversacion_id`) la lleva el frontend: el servicio externo recuerda los últimos 6
intercambios durante 30 minutos. El historial que ve el Paciente es el de LisoGen (`chatbot_mensaje`)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errores import ErrorNegocio
from app.integrations.ports import ErrorChatbot
from app.integrations.registro import Integraciones
from app.models import ChatbotMensaje, Usuario
from app.schemas.roles import ChatMensajeSalida


def _rechazo(e: ErrorChatbot) -> ErrorNegocio:
    """429: pasaron el límite de consultas. 503: el servicio está apagado y se muestra su aviso tal cual.
    Cualquier otro error (401 de configuración, 500, sin respuesta) es genérico para el Paciente."""
    if e.status == 429:
        return ErrorNegocio(
            "CHATBOT_OCUPADO",
            "El Chatbot tiene muchas consultas en este momento. Probá de nuevo en unos segundos.",
            429,
        )
    if e.status == 503 and e.detalle:
        return ErrorNegocio("CHATBOT_APAGADO", e.detalle, 502)
    return ErrorNegocio(
        "CHATBOT_NO_DISPONIBLE", "El Chatbot no está disponible por ahora. Intentá de nuevo más tarde.", 502
    )


async def preguntar(
    session: AsyncSession,
    ints: Integraciones,
    usuario: Usuario,
    pregunta: str,
    conversacion_id: str | None = None,
) -> ChatMensajeSalida:
    pregunta = pregunta.strip()
    try:
        r = await ints.chatbot.responder(pregunta=pregunta, conversacion_id=conversacion_id)
    except ErrorChatbot as e:
        raise _rechazo(e) from e
    mensaje = ChatbotMensaje(usuario_id=usuario.id, pregunta=pregunta, respuesta=r.respuesta)
    session.add(mensaje)
    await session.flush()
    await session.refresh(mensaje, ["created_at"])
    salida = ChatMensajeSalida.model_validate(mensaje)
    return salida.model_copy(update={"conversacion_id": r.conversacion_id, "tipo": r.tipo})


async def historial(session: AsyncSession, usuario: Usuario) -> list[ChatMensajeSalida]:
    filas = await session.scalars(
        select(ChatbotMensaje)
        .where(ChatbotMensaje.usuario_id == usuario.id)
        .order_by(ChatbotMensaje.created_at, ChatbotMensaje.id)
        .limit(200)
    )
    return [ChatMensajeSalida.model_validate(m) for m in filas]
