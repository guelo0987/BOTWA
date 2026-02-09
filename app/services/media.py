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
            
            if response.text is None:
                logger.warning("Gemini devolvió transcripción vacía (audio corto/silencio o bloqueo)")
                return "[No se pudo transcribir el audio. ¿Podrías repetirlo o escribir tu mensaje?]"
            transcription = response.text.strip()
            if not transcription:
                return "[No se pudo transcribir el audio. ¿Podrías repetirlo o escribir tu mensaje?]"
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
            
            if response.text is None:
                logger.warning(f"Gemini devolvió análisis vacío para documento: {filename}")
                return f"[No se pudo analizar el documento: {filename}]"
            analysis = response.text.strip()
            logger.debug(f"Documento procesado: {filename}")
            return f"[Contenido del documento {filename}]:\n{analysis}"
            
        except Exception as e:
            logger.error(f"Error procesando documento: {e}")
            return f"[Error al procesar el documento: {filename}]"
    
    async def analyze_image(self, media_id: str, caption: str, business_context: dict) -> str:
        """
        Analiza una imagen enviada por el usuario usando Gemini Vision.
        Incluye contexto del negocio para dar respuestas inteligentes.
        
        Args:
            media_id: ID de la imagen en WhatsApp
            caption: Texto que acompaña la imagen (si hay)
            business_context: Configuración del negocio (catalog, services, professionals)
            
        Returns:
            Descripción/análisis de la imagen con contexto del negocio
        """
        try:
            # Descargar la imagen
            image_content = await self.download_media(media_id)
            
            if not image_content:
                return f"[No se pudo descargar la imagen]{' - ' + caption if caption else ''}"
            
            # Construir contexto del negocio para el análisis
            context_parts = []
            
            # Catálogo de productos
            if 'catalog' in business_context:
                categories = business_context['catalog'].get('categories', [])
                if categories:
                    productos = []
                    for cat in categories:
                        for prod in cat.get('products', []):
                            precio = prod.get('price', 'N/A')
                            productos.append(f"- {prod['name']}: ${precio}")
                    if productos:
                        context_parts.append(f"CATÁLOGO DE PRODUCTOS:\n" + "\n".join(productos[:20]))  # Limitar a 20
            
            # Servicios
            if 'services' in business_context:
                servicios = []
                for s in business_context['services']:
                    if s.get('price', 0) > 0:  # Solo servicios reales
                        servicios.append(f"- {s['name']}: ${s['price']}")
                if servicios:
                    context_parts.append(f"SERVICIOS DISPONIBLES:\n" + "\n".join(servicios[:10]))
            
            # Profesionales
            if 'professionals' in business_context:
                profs = []
                for p in business_context['professionals']:
                    profs.append(f"- {p['name']} ({p.get('specialty', 'General')})")
                if profs:
                    context_parts.append(f"PROFESIONALES:\n" + "\n".join(profs))
            
            # Nombre del negocio
            business_name = business_context.get('business_name', 'el negocio')
            business_type = business_context.get('business_type', 'general')
            
            context_text = "\n\n".join(context_parts) if context_parts else "No hay catálogo específico configurado."
            
            # Prompt para Gemini Vision
            user_caption = f'\n\nEl usuario dice: "{caption}"' if caption and caption != "[Imagen recibida]" else ""
            
            prompt = f"""Eres el asistente virtual de {business_name} (tipo: {business_type}).

CONTEXTO DEL NEGOCIO:
{context_text}

TAREA:
Analiza esta imagen que envió un cliente por WhatsApp.{user_caption}

INSTRUCCIONES:
1. Describe brevemente qué ves en la imagen
2. Si es un producto que parece estar en nuestro catálogo, identifícalo y menciona el precio
3. Si es una consulta sobre algo que vendemos/ofrecemos, da información útil
4. Si no puedes identificar el producto exacto, sugiere opciones similares del catálogo
5. Sé amable y ofrece ayuda adicional

Responde en español, de forma concisa y útil para WhatsApp (usa *negritas* y emojis moderadamente)."""

            # Llamar a Gemini con la imagen
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(
                                data=image_content,
                                mime_type="image/jpeg"  # WhatsApp normalmente usa JPEG
                            ),
                            types.Part.from_text(text=prompt)
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=500,
                )
            )
            
            if response.text is None:
                logger.warning("Gemini devolvió análisis vacío para imagen")
                return f"[Imagen recibida]{' - ' + caption if caption else ''}"
            
            analysis = response.text.strip()
            logger.debug("Imagen analizada correctamente")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analizando imagen: {e}", exc_info=True)
            return f"[No pude analizar la imagen]{' - ' + caption if caption else ''}"


# Instancia global
media_service = MediaService()
