import redis.asyncio as redis
from app.core.config import settings
import json
import logging
import asyncio

logger = logging.getLogger(__name__)

# Cliente Redis global
redis_client: redis.Redis | None = None


async def init_redis() -> redis.Redis:
    """
    Inicializa la conexión a Redis.
    Llamar al inicio de la aplicación.
    """
    global redis_client
    redis_client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
        retry_on_timeout=True,
    )
    # Verificar conexión
    try:
        await asyncio.wait_for(
            redis_client.ping(),
            timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS + settings.REDIS_SOCKET_TIMEOUT_SECONDS,
        )
    except Exception:
        # Cerrar el cliente para no dejar conexiones colgadas
        try:
            await redis_client.aclose()
        except Exception:
            pass
        redis_client = None
        logger.exception(
            "No se pudo conectar a Redis (url=%s, connect_timeout=%ss, socket_timeout=%ss).",
            settings.REDIS_URL,
            settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            settings.REDIS_SOCKET_TIMEOUT_SECONDS,
        )
        raise
    return redis_client


async def close_redis():
    """
    Cierra la conexión a Redis.
    Llamar al cerrar la aplicación.
    """
    global redis_client
    if redis_client:
        await redis_client.aclose()


def get_redis() -> redis.Redis:
    """
    Obtiene el cliente Redis.
    """
    if redis_client is None:
        raise RuntimeError("Redis no inicializado. Llama init_redis() primero.")
    return redis_client


class ConversationMemory:
    """
    Maneja la memoria de conversaciones en Redis.
    Cada conversación se guarda como una lista de mensajes.
    """
    
    def __init__(self, client_id: int, phone_number: str):
        """
        Args:
            client_id: ID del cliente (tenant)
            phone_number: Número de teléfono del usuario
        """
        self.key = f"chat:{client_id}:{phone_number}"
        self.redis = get_redis()
    
    async def add_message(self, role: str, content: str):
        """
        Agrega un mensaje al historial.
        
        Args:
            role: "user" o "assistant"
            content: Contenido del mensaje
        """
        message = json.dumps({
            "role": role,
            "content": content
        })
        await self.redis.rpush(self.key, message)
        
        # Mantener solo los últimos N mensajes
        await self.redis.ltrim(self.key, -settings.MAX_CONTEXT_MESSAGES, -1)
        
        # Renovar TTL
        await self.redis.expire(self.key, settings.SESSION_EXPIRE_SECONDS)
    
    async def get_history(self) -> list[dict]:
        """
        Obtiene todo el historial de la conversación.
        
        Returns:
            Lista de mensajes [{"role": "user", "content": "..."}, ...]
        """
        messages = await self.redis.lrange(self.key, 0, -1)
        return [json.loads(msg) for msg in messages]
    
    async def clear(self):
        """Limpia el historial de la conversación."""
        await self.redis.delete(self.key)
    
    async def get_context_for_llm(self) -> list[dict]:
        """
        Obtiene el historial en formato para Gemini.
        
        Returns:
            Lista de mensajes formateados para la API de Gemini
        """
        history = await self.get_history()
        # Gemini usa "user" y "model" como roles
        formatted = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            formatted.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
        return formatted
    
    # ==========================================
    # MÉTODOS PARA INTERVENCIÓN HUMANA
    # ==========================================
    
    async def is_human_handled(self) -> bool:
        """
        Verifica si la conversación está siendo manejada por un humano.
        
        Returns:
            True si hay intervención humana activa
        """
        status_key = f"{self.key}:status"
        status = await self.redis.get(status_key)
        return status in ["human_handled", "escalated"]
    
    async def set_human_handled(self, handled: bool = True, admin_user: str | None = None, ttl_seconds: int = 1800):
        """
        Marca la conversación como manejada por humano o libera el control.
        
        Args:
            handled: True para marcar como manejada por humano, False para liberar
            admin_user: Usuario/admin que está manejando (opcional)
            ttl_seconds: Tiempo en segundos antes de que la IA se reanude automáticamente (default: 30 min)
        """
        status_key = f"{self.key}:status"
        admin_key = f"{self.key}:admin"
        
        if handled:
            await self.redis.set(status_key, "human_handled", ex=ttl_seconds)
            if admin_user:
                await self.redis.set(admin_key, admin_user, ex=ttl_seconds)
        else:
            await self.redis.delete(status_key)
            await self.redis.delete(admin_key)
    
    async def set_escalated(self, escalated: bool = True, motivo: str | None = None):
        """
        Marca la conversación como escalada.
        
        Args:
            escalated: True para escalar, False para desescalar
            motivo: Motivo de la escalación (opcional)
        """
        status_key = f"{self.key}:status"
        reason_key = f"{self.key}:escalation_reason"
        
        if escalated:
            await self.redis.set(status_key, "escalated", ex=settings.SESSION_EXPIRE_SECONDS)
            if motivo:
                await self.redis.set(reason_key, motivo, ex=settings.SESSION_EXPIRE_SECONDS)
        else:
            await self.redis.delete(status_key)
            await self.redis.delete(reason_key)
    
    async def get_status(self) -> dict:
        """
        Obtiene el estado actual de la conversación.
        
        Returns:
            Dict con status, admin (si aplica), escalation_reason (si aplica)
        """
        status_key = f"{self.key}:status"
        admin_key = f"{self.key}:admin"
        reason_key = f"{self.key}:escalation_reason"
        
        status = await self.redis.get(status_key) or "active"
        admin = await self.redis.get(admin_key)
        reason = await self.redis.get(reason_key)
        
        return {
            "status": status,
            "admin": admin,
            "escalation_reason": reason
        }
    
    async def add_human_message(self, content: str, admin_name: str = "Agente"):
        """
        Agrega un mensaje enviado por un humano/admin.
        
        Args:
            content: Contenido del mensaje
            admin_name: Nombre del admin (opcional)
        """
        message = json.dumps({
            "role": "assistant",
            "content": content,
            "human": True,
            "admin": admin_name
        })
        await self.redis.rpush(self.key, message)
        await self.redis.ltrim(self.key, -settings.MAX_CONTEXT_MESSAGES, -1)
        await self.redis.expire(self.key, settings.SESSION_EXPIRE_SECONDS)
    
    async def save_sent_message_id(self, message_id: str):
        """
        Guarda el message_id de un mensaje enviado por el bot.
        
        Args:
            message_id: ID del mensaje enviado
        """
        sent_key = f"{self.key}:sent_messages"
        await self.redis.sadd(sent_key, message_id)
        await self.redis.expire(sent_key, settings.SESSION_EXPIRE_SECONDS)
    
    async def is_message_sent_by_bot(self, message_id: str) -> bool:
        """
        Verifica si un mensaje fue enviado por el bot.
        
        Args:
            message_id: ID del mensaje a verificar
            
        Returns:
            True si el mensaje fue enviado por el bot
        """
        sent_key = f"{self.key}:sent_messages"
        return await self.redis.sismember(sent_key, message_id)
