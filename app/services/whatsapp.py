import httpx
import logging

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    Servicio para interactuar con la API de WhatsApp.
    Multi-tenant: cada método recibe las credenciales del cliente.
    """
    
    def __init__(self):
        # Cliente compartido con connection pooling (sin headers por defecto)
        self._client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    
    async def close(self):
        """Cierra el cliente HTTP. Llamar al cerrar la aplicación."""
        await self._client.aclose()
    
    def _headers(self, access_token: str) -> dict:
        """Construye headers de autorización para un cliente específico."""
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    def _base_url(self, phone_number_id: str, api_version: str) -> str:
        """Construye la URL base de la API para un cliente específico."""
        return f"https://graph.facebook.com/{api_version}/{phone_number_id}"
    
    async def send_text_message(
        self, 
        *,
        to: str, 
        message: str,
        access_token: str,
        phone_number_id: str,
        api_version: str,
        preview_url: bool = False,
        client_id: int | None = None
    ) -> dict:
        url = f"{self._base_url(phone_number_id, api_version)}/messages"
        
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
        
        try:
            response = await self._client.post(
                url, json=payload, headers=self._headers(access_token)
            )
            response.raise_for_status()
            result = response.json()
            
            # Guardar message_id en Redis (para detectar mensajes desde Business Suite)
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
    
    async def mark_as_read(
        self,
        message_id: str,
        *,
        access_token: str,
        phone_number_id: str,
        api_version: str
    ) -> dict:
        """
        Marca un mensaje como leído (doble check azul).
        
        Args:
            message_id: ID del mensaje recibido
            access_token: Token de acceso de Meta del cliente
            phone_number_id: Phone Number ID del cliente
        """
        url = f"{self._base_url(phone_number_id, api_version)}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        
        try:
            response = await self._client.post(
                url, json=payload, headers=self._headers(access_token)
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning(f"No se pudo marcar como leído: {e}")
            return {}
    
    async def send_typing_indicator(
        self,
        to: str,
        *,
        message_id: str,
        access_token: str,
        phone_number_id: str,
        api_version: str
    ) -> None:
        """
        Envía el indicador nativo de 'escribiendo...' en WhatsApp.
        Se auto-cancela después de 25 segundos o al enviar un mensaje.
        """
        url = f"{self._base_url(phone_number_id, api_version)}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
            "typing_indicator": {
                "type": "text"
            }
        }
        
        try:
            response = await self._client.post(
                url, json=payload, headers=self._headers(access_token)
            )
            if response.status_code >= 400:
                logger.debug(f"Typing indicator falló: {response.status_code} - {response.text}")
        except Exception as e:
            logger.debug(f"No se pudo enviar typing indicator: {e}")
    
    async def get_media_url(
        self,
        media_id: str,
        *,
        access_token: str,
        api_version: str
    ) -> str | None:
        """
        Obtiene la URL de descarga de un archivo multimedia.
        
        Args:
            media_id: ID del media (imagen, audio, documento)
            access_token: Token de acceso de Meta del cliente
            
        Returns:
            URL de descarga temporal
        """
        url = f"https://graph.facebook.com/{api_version}/{media_id}"
        
        try:
            response = await self._client.get(
                url, headers=self._headers(access_token)
            )
            response.raise_for_status()
            data = response.json()
            return data.get("url")
        except Exception as e:
            logger.error(f"Error obteniendo URL de media: {e}")
            return None
    
    async def download_media(
        self,
        media_url: str,
        *,
        access_token: str
    ) -> bytes | None:
        """
        Descarga un archivo multimedia.
        
        Args:
            media_url: URL obtenida de get_media_url
            access_token: Token de acceso de Meta del cliente
            
        Returns:
            Contenido binario del archivo
        """
        try:
            response = await self._client.get(
                media_url, 
                headers=self._headers(access_token),
                timeout=60.0
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Error descargando media: {e}")
            return None
    

# Instancia global del servicio (sin credenciales, las recibe por llamada)
whatsapp_service = WhatsAppService()
