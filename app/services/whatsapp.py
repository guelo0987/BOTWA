import httpx
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class WhatsAppService:

    
    def __init__(self):
        self.base_url = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
    
    async def send_text_message(
        self, 
        to: str, 
        message: str,
        preview_url: bool = False,
        client_id: int | None = None
    ) -> dict:
        """
        Envía un mensaje de texto.
        
        Args:
            to: Número de teléfono destino (formato: 18091234567)
            message: Texto del mensaje
            preview_url: Si mostrar preview de URLs
            client_id: ID del cliente (opcional, para guardar message_id en Redis)
            
        Returns:
            Respuesta de la API de Meta
        """
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": message
            }
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url, 
                    json=payload, 
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                
                # Guardar message_id en Redis si tenemos client_id (para detectar mensajes desde Business Suite)
                if client_id and "messages" in result:
                    message_id = result["messages"][0].get("id")
                    if message_id:
                        try:
                            from app.core.redis import ConversationMemory
                            memory = ConversationMemory(client_id, to)
                            await memory.save_sent_message_id(message_id)
                        except Exception as e:
                            logger.debug(f"No se pudo guardar message_id: {e}")
                
                logger.debug(f"Mensaje enviado a {to}")
                return result
            except httpx.HTTPStatusError as e:
                logger.error(f"Error HTTP enviando mensaje: {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error enviando mensaje: {e}")
                raise
    
    async def mark_as_read(self, message_id: str) -> dict:
        """
        Marca un mensaje como leído (doble check azul).
        
        Args:
            message_id: ID del mensaje recibido
        """
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(f"No se pudo marcar como leído: {e}")
                return {}
    
    async def get_media_url(self, media_id: str) -> str | None:
        """
        Obtiene la URL de descarga de un archivo multimedia.
        
        Args:
            media_id: ID del media (imagen, audio, documento)
            
        Returns:
            URL de descarga temporal
        """
        url = f"{self.base_url}/{media_id}"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                return data.get("url")
            except Exception as e:
                logger.error(f"Error obteniendo URL de media: {e}")
                return None
    
    async def download_media(self, media_url: str) -> bytes | None:
        """
        Descarga un archivo multimedia.
        
        Args:
            media_url: URL obtenida de get_media_url
            
        Returns:
            Contenido binario del archivo
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    media_url, 
                    headers=self.headers,
                    timeout=60.0
                )
                response.raise_for_status()
                return response.content
            except Exception as e:
                logger.error(f"Error descargando media: {e}")
                return None
    

# Instancia global del servicio
whatsapp_service = WhatsAppService()
