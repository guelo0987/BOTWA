"""
Servicio para procesamiento de multimedia (audio, documentos).
"""
import logging
import base64
import httpx
from google import genai
from google.genai import types

from app.core.config import settings
from app.services.whatsapp import whatsapp_service

logger = logging.getLogger(__name__)


class MediaService:
    """
    Servicio para procesar archivos multimedia de WhatsApp.
    - Transcripción de audio con Gemini
    - Procesamiento de documentos
    """
    
    def __init__(self):
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.model = settings.GEMINI_MODEL
    
    async def download_media(self, media_id: str) -> bytes | None:
       
        try:
            # Primero obtener la URL del media
            media_url = await whatsapp_service.get_media_url(media_id)
            
            if not media_url:
                logger.error(f"No se pudo obtener URL para media: {media_id}")
                return None
            
            # Descargar el archivo
            content = await whatsapp_service.download_media(media_url)
            return content
            
        except Exception as e:
            logger.error(f"Error descargando media: {e}")
            return None
    
    async def transcribe_audio(self, media_id: str) -> str:
        """
        Transcribe un audio de WhatsApp usando Gemini.
        
        Args:
            media_id: ID del audio en WhatsApp
            
        Returns:
            Texto transcrito
        """
        try:
            # Descargar el audio
            audio_content = await self.download_media(media_id)
            
            if not audio_content:
                return "[No se pudo descargar el audio]"
            
            # Convertir a base64
            audio_base64 = base64.b64encode(audio_content).decode('utf-8')
            
            # Usar Gemini para transcribir
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(
                                data=audio_content,
                                mime_type="audio/ogg"  # WhatsApp usa OGG
                            ),
                            types.Part.from_text(
                                text="Transcribe este audio al español. Solo devuelve la transcripción, sin comentarios adicionales."
                            )
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=1024,
                )
            )
            
            transcription = response.text.strip()
            logger.debug("Audio transcrito")
            return transcription
            
        except Exception as e:
            logger.error(f"Error transcribiendo audio: {e}", exc_info=True)
            return "[Error al transcribir el audio]"
    
    async def process_document(self, media_id: str, filename: str) -> str:
        """
        Procesa un documento (extrae texto si es posible).
        
        Args:
            media_id: ID del documento en WhatsApp
            filename: Nombre del archivo
            
        Returns:
            Descripción o contenido del documento
        """
        try:
            content = await self.download_media(media_id)
            
            if not content:
                return f"[No se pudo descargar el documento: {filename}]"
            
            # Detectar tipo de archivo
            if filename.lower().endswith('.pdf'):
                mime_type = "application/pdf"
            elif filename.lower().endswith(('.doc', '.docx')):
                return f"[Documento Word recibido: {filename}. Por favor envíalo como PDF para procesarlo]"
            else:
                return f"[Documento recibido: {filename}]"
            
            # Usar Gemini para procesar PDF
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(
                                data=content,
                                mime_type=mime_type
                            ),
                            types.Part.from_text(
                                text="Analiza este documento y extrae la información más importante. Sé conciso."
                            )
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=1024,
                )
            )
            
            analysis = response.text.strip()
            logger.debug(f"Documento procesado: {filename}")
            return f"[Contenido del documento {filename}]:\n{analysis}"
            
        except Exception as e:
            logger.error(f"Error procesando documento: {e}")
            return f"[Error al procesar el documento: {filename}]"


# Instancia global
media_service = MediaService()
