"""E14 Consultar Chatbot: módulo externo que responde sobre las cinco Patologías y no deriva a personas."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.registro import Integraciones
from app.models import ChatbotMensaje, Usuario
from app.schemas.roles import ChatMensajeSalida


async def preguntar(
    session: AsyncSession, ints: Integraciones, usuario: Usuario, pregunta: str
) -> ChatMensajeSalida:
    respuesta = await ints.chatbot.responder(pregunta=pregunta.strip())
    mensaje = ChatbotMensaje(usuario_id=usuario.id, pregunta=pregunta.strip(), respuesta=respuesta)
    session.add(mensaje)
    await session.flush()
    await session.refresh(mensaje, ["created_at"])
    return ChatMensajeSalida.model_validate(mensaje)


async def historial(session: AsyncSession, usuario: Usuario) -> list[ChatMensajeSalida]:
    filas = await session.scalars(
        select(ChatbotMensaje)
        .where(ChatbotMensaje.usuario_id == usuario.id)
        .order_by(ChatbotMensaje.created_at, ChatbotMensaje.id)
        .limit(200)
    )
    return [ChatMensajeSalida.model_validate(m) for m in filas]
