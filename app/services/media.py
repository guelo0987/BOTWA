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
    
    async def download_media(self, media_id: str, *, access_token: str, api_version: str) -> bytes | None:
       
        try:
            # Primero obtener la URL del media
            media_url = await whatsapp_service.get_media_url(media_id, access_token=access_token, api_version=api_version)
            
            if not media_url:
                logger.error(f"No se pudo obtener URL para media: {media_id}")
                return None
            
            # Descargar el archivo
            content = await whatsapp_service.download_media(media_url, access_token=access_token)
            return content
            
        except Exception as e:
            logger.error(f"Error descargando media: {e}")
            return None
    
    async def transcribe_audio(self, media_id: str, *, access_token: str, api_version: str) -> str:
        """
        Transcribe un audio de WhatsApp usando Gemini.
        
        Args:
            media_id: ID del audio en WhatsApp
            access_token: Token de acceso de Meta del cliente
            
        Returns:
            Texto transcrito
        """
        try:
            # Descargar el audio
            audio_content = await self.download_media(media_id, access_token=access_token, api_version=api_version)
            
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
    
    async def process_document(self, media_id: str, filename: str, *, access_token: str, api_version: str) -> str:
        """
        Procesa un documento (extrae texto si es posible).
        
        Args:
            media_id: ID del documento en WhatsApp
            filename: Nombre del archivo
            access_token: Token de acceso de Meta del cliente
            
        Returns:
            Descripción o contenido del documento
        """
        try:
            content = await self.download_media(media_id, access_token=access_token, api_version=api_version)
            
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
    
    async def analyze_image(self, media_id: str, caption: str, business_context: dict, *, access_token: str, api_version: str) -> str:
        """
        Analiza una imagen enviada por el usuario usando Gemini Vision.
        Incluye contexto del negocio para dar respuestas inteligentes.
        
        Args:
            media_id: ID de la imagen en WhatsApp
            caption: Texto que acompaña la imagen (si hay)
            business_context: Configuración del negocio (catalog, services, professionals)
            access_token: Token de acceso de Meta del cliente
            
        Returns:
            Descripción/análisis de la imagen con contexto del negocio
        """
        try:
            # Descargar la imagen
            image_content = await self.download_media(media_id, access_token=access_token, api_version=api_version)
            
            if not image_content:
                return f"[No se pudo descargar la imagen]{' - ' + caption if caption else ''}"
            
            # Construir contexto del negocio para el análisis
            context_parts = []
            catalog_is_pdf = business_context.get('catalog_source') == 'pdf'

            # Catálogo de productos (solo si es manual, no PDF)
            if not catalog_is_pdf and 'catalog' in business_context:
                categories = business_context['catalog'].get('categories', [])
                if categories:
                    productos = []
                    for cat in categories:
                        for prod in cat.get('products', []):
                            precio = prod.get('price', 'N/A')
                            if prod['name'] != 'Producto' or precio != 0:  # Ignorar placeholder
                                productos.append(f"- {prod['name']}: ${precio}")
                    if productos:
                        context_parts.append(f"CATÁLOGO DE PRODUCTOS:\n" + "\n".join(productos[:20]))

            # Servicios
            if 'services' in business_context:
                servicios = []
                for s in business_context['services']:
                    if s.get('price', 0) > 0:
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

            context_text = "\n\n".join(context_parts) if context_parts else ""

            # Prompt para Gemini Vision
            user_caption = f'\n\nEl usuario dice: "{caption}"' if caption and caption != "[Imagen recibida]" else ""

            if catalog_is_pdf:
                # Para catálogos PDF: el modelo no tiene la lista de productos,
                # debe leer EXACTAMENTE lo que aparece en la imagen
                prompt = f"""Eres el asistente virtual de {business_name} (tipo: {business_type}).

El catálogo de este negocio está en un PDF. NO tienes la lista de productos aquí.
Tu trabajo es LEER con precisión TODOS los detalles que aparecen en la imagen.

TAREA:
Analiza esta imagen que envió un cliente por WhatsApp.{user_caption}

INSTRUCCIONES CRÍTICAS — LEE TODA LA IMAGEN COMPLETA:
1. Lee el TÍTULO EXACTO del producto tal como aparece en la imagen, incluyendo cualquier variante, modificador o subtipo que se muestre
2. Escribe EXACTAMENTE: "PRODUCTO IDENTIFICADO: [título/nombre exacto como aparece en la imagen]"
3. Lista TODOS los sub-modelos, variantes o líneas del producto visibles en la imagen
4. Copia TODOS los precios exactamente como aparecen escritos (no redondees, no cambies el formato)
5. Copia TODAS las medidas, tamaños, capacidades, especificaciones técnicas o dimensiones visibles
6. Si hay una tabla de precios o variantes, cópiala completa fila por fila

IMPORTANTE: Lee el texto de la imagen LITERALMENTE. No inventes ni omitas ningún dato.
NO respondas de forma breve — incluye ABSOLUTAMENTE TODOS los detalles, modelos, sub-modelos y precios visibles en la imagen."""
            else:
                prompt = f"""Eres el asistente virtual de {business_name} (tipo: {business_type}).

{"CONTEXTO DEL NEGOCIO:" + chr(10) + context_text if context_text else ""}

TAREA:
Analiza esta imagen que envió un cliente por WhatsApp.{user_caption}

INSTRUCCIONES:
1. Describe brevemente qué ves en la imagen
2. Si la imagen muestra un producto, modelo o captura de pantalla de nuestro catálogo, identifícalo con exactitud.
   - Lee el nombre/título EXACTO del producto tal como aparece en la imagen, incluyendo variantes o modificadores.
   - Escribe EXACTAMENTE: "PRODUCTO IDENTIFICADO: [nombre exacto como aparece en la imagen]" seguido del precio.
   - Si ves medidas, tamaños o variantes, inclúyelos
   - IMPORTANTE: Si la imagen es una captura o foto del catálogo del negocio, ES un producto válido. Identifícalo.
3. Si NO puedes identificar el producto exacto pero ves algo similar al catálogo, sugiere las opciones más cercanas
4. Solo di que no reconoces el producto si la imagen claramente NO tiene relación con los productos del negocio

IMPORTANTE: Lee el texto de la imagen LITERALMENTE. No cambies nombres ni precios.

Responde en español, de forma concisa. Tu análisis será usado por el chat principal para ayudar al cliente."""

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
                    temperature=0.2 if catalog_is_pdf else 0.7,
                    max_output_tokens=1500 if catalog_is_pdf else 600,
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
