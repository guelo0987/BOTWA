from fastapi import APIRouter, Request, HTTPException, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
import hmac
import hashlib
import logging

from app.core.config import settings
from app.schemas.webhook import WhatsAppWebhook, ProcessedMessage
from app.services.whatsapp import whatsapp_service
from app.services.client_service import client_service
from app.services.gemini import gemini_service
from app.services.media import media_service
from app.core.redis import ConversationMemory, get_redis

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge")
):
    """Verificación del webhook de Meta."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge)
    
    logger.warning("Verificación fallida - token inválido")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post(
    "",
    status_code=200,
    summary="Recibir webhook de WhatsApp",
    description="Endpoint que recibe notificaciones de mensajes de WhatsApp desde Meta.",
    responses={
        200: {
            "description": "Webhook procesado correctamente",
            "content": {
                "application/json": {
                    "example": {"status": "received"}
                }
            }
        },
        422: {"description": "Payload inválido"},
        500: {"description": "Error interno del servidor"}
    }
)
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks
) -> dict[str, str]:
    """
    Recibe y procesa mensajes del webhook de WhatsApp.
    
    Este endpoint es llamado por Meta cada vez que se recibe un mensaje.
    Los mensajes se procesan de forma asíncrona en background tasks.
    """
    try:
        body_bytes = await request.body()
        
        # --- VERIFICACIÓN DE FIRMA (X-Hub-Signature-256) ---
        if settings.WHATSAPP_APP_SECRET:
            signature = request.headers.get("X-Hub-Signature-256", "")
            expected = "sha256=" + hmac.new(
                settings.WHATSAPP_APP_SECRET.encode(),
                body_bytes,
                hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                logger.warning("Webhook con firma inválida rechazado")
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        import json
        body = json.loads(body_bytes)
        logger.debug("Webhook recibido")
        
        webhook_data = WhatsAppWebhook(**body)
        
        if webhook_data.object != "whatsapp_business_account":
            return {"status": "ignored"}
        
        for entry in webhook_data.entry:
            for change in entry.changes:
                value = change.value
                
                # Procesar mensajes entrantes
                if change.field == "messages" and value.messages:
                    for message in value.messages:
                        # --- DEDUPLICACIÓN ---
                        try:
                            redis = get_redis()
                            dedup_key = f"processed:{message.id}"
                            if await redis.get(dedup_key):
                                logger.debug(f"Mensaje duplicado ignorado: {message.id}")
                                continue
                            await redis.set(dedup_key, "1", ex=300)  # 5 min TTL
                        except Exception:
                            pass  # Si Redis falla, procesar de todos modos
                        
                        processed = process_incoming_message(message, value)
                        
                        if processed:
                            # --- RATE LIMITING (10 msgs/min por teléfono) ---
                            try:
                                redis = get_redis()
                                rate_key = f"rate:{processed.phone_number}"
                                count = await redis.incr(rate_key)
                                if count == 1:
                                    await redis.expire(rate_key, 60)
                                if count > 10:
                                    logger.warning(f"Rate limit alcanzado para {processed.phone_number}")
                                    if count == 11:  # Solo avisar una vez
                                        # Buscar client para poder responder
                                        try:
                                            rl_client = await client_service.get_client_by_phone_id(processed.phone_number_id)
                                            if rl_client and rl_client.whatsapp_access_token:
                                                await whatsapp_service.send_text_message(
                                                    to=processed.phone_number,
                                                    message="⚠️ Estás enviando mensajes muy rápido. Por favor espera un momento antes de continuar.",
                                                    access_token=rl_client.whatsapp_access_token,
                                                    phone_number_id=rl_client.whatsapp_instance_id,
                                                    api_version=rl_client.whatsapp_api_version or "v21.0",
                                                    client_id=rl_client.id,
                                                )
                                        except Exception:
                                            pass
                                    continue
                            except Exception:
                                pass  # Si Redis falla, no limitar
                            
                            logger.debug(f"[{processed.message_type}] {processed.contact_name}")
                            background_tasks.add_task(handle_message, processed)
                
                # Procesar statuses (para detectar mensajes desde Business Suite)
                elif change.field == "messages" and value.statuses:
                    for status in value.statuses:
                        message_id = status.get("id")
                        status_type = status.get("status")  # sent, delivered, read, failed
                        recipient_id = status.get("recipient_id")
                        
                        # Si el mensaje fue enviado pero NO lo enviamos nosotros, es de Business Suite
                        if status_type == "sent" and message_id and recipient_id:
                            background_tasks.add_task(
                                detect_business_suite_message,
                                value.metadata.phone_number_id,
                                recipient_id,
                                message_id
                            )
        
        return {"status": "received"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing webhook")


def process_incoming_message(message, value) -> ProcessedMessage | None:
    """Procesa un mensaje entrante."""
    try:
        phone_number = message.from_
        message_id = message.id
        message_type = message.type
        phone_number_id = value.metadata.phone_number_id
        
        contact_name = "Usuario"
        if value.contacts:
            contact_name = value.contacts[0].profile.name
        
        content = ""
        media_id = None
        
        if message_type == "text" and message.text:
            content = message.text.body
            
        elif message_type == "image" and message.image:
            media_id = message.image.id
            content = message.image.caption or "[Imagen recibida]"
            
        elif message_type == "audio" and message.audio:
            media_id = message.audio.id
            content = "[AUDIO_PENDING_TRANSCRIPTION]"
            
        elif message_type == "document" and message.document:
            media_id = message.document.id
            content = f"[DOCUMENT:{message.document.filename or 'archivo'}]"
            
        elif message_type == "location" and message.location:
            lat = message.location.latitude
            lon = message.location.longitude
            content = f"[Ubicación: {lat}, {lon}]"
        
        elif message_type in ("sticker", "reaction", "contacts", "ephemeral", "unsupported"):
            # Tipos que no requieren procesamiento por IA
            logger.debug(f"Tipo de mensaje ignorado: {message_type}")
            return None
            
        else:
            content = f"[Mensaje tipo {message_type}]"
        
        return ProcessedMessage(
            phone_number=phone_number,
            phone_number_id=phone_number_id,
            message_id=message_id,
            message_type=message_type,
            content=content,
            contact_name=contact_name,
            media_id=media_id,
            raw_data=message.model_dump() if hasattr(message, 'model_dump') else None
        )
        
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        return None


async def detect_business_suite_message(
    phone_number_id: str,
    recipient_id: str,
    message_id: str
):
    """
    Detecta si un mensaje fue enviado desde Meta Business Suite (no desde nuestro bot).
    Si es así, marca la conversación como manejada por humano.
    """
    try:
        client = await client_service.get_client_by_phone_id(phone_number_id)
        if not client:
            return
        
        memory = ConversationMemory(client.id, recipient_id)
        is_ours = await memory.is_message_sent_by_bot(message_id)
        
        if not is_ours:
            # Mensaje enviado desde Business Suite - marcar como human_handled
            await memory.set_human_handled(handled=True, admin_user="Meta Business Suite")
            logger.info(f"Detectado mensaje desde Business Suite: {recipient_id} - IA pausada")
    except Exception as e:
        logger.debug(f"Error detectando mensaje Business Suite: {e}")


async def handle_message(msg: ProcessedMessage):
    """
    Maneja un mensaje procesado con IA.
    Soporta texto, audio y documentos.
    """
    try:
        # 1. Identificar el Client (tenant)
        client = await client_service.get_client_by_phone_id(msg.phone_number_id)
        
        if not client:
            logger.warning(f"Client no encontrado: {msg.phone_number_id}")
            return
        
        # Verificar que el client tenga token de WhatsApp configurado
        if not client.whatsapp_access_token:
            logger.error(f"Client {client.business_name} sin whatsapp_access_token configurado")
            return
        
        # Extraer credenciales del client (usadas en todo el handler)
        wa_token = client.whatsapp_access_token
        wa_phone_id = client.whatsapp_instance_id
        wa_version = client.whatsapp_api_version or "v24.0"
        
        logger.debug(f"Client: {client.business_name}")
        
        # 2. Obtener o crear Customer
        customer = await client_service.get_or_create_customer(
            client_id=client.id,
            phone_number=msg.phone_number,
            full_name=msg.contact_name
        )
        
        logger.debug(f"Customer: {customer.full_name or customer.phone_number}")
        
        # 3. Marcar como leído inmediatamente (✓✓ azules)
        await whatsapp_service.mark_as_read(
            msg.message_id,
            access_token=wa_token,
            phone_number_id=wa_phone_id,
            api_version=wa_version,
        )
        
        # 4. Indicador de "escribiendo..." nativo de WhatsApp
        try:
            await whatsapp_service.send_typing_indicator(
                to=msg.phone_number,
                message_id=msg.message_id,
                access_token=wa_token,
                phone_number_id=wa_phone_id,
                api_version=wa_version,
            )
        except Exception:
            pass  # No es crítico
        
        # 5. Procesar contenido según tipo
        user_message = msg.content
        
        # Transcribir audio si es necesario
        if msg.message_type == "audio" and msg.media_id:
            logger.debug("Transcribiendo audio...")
            user_message = await media_service.transcribe_audio(
                msg.media_id, access_token=wa_token, api_version=wa_version
            )
        
        # Procesar documento si es necesario
        elif msg.message_type == "document" and msg.media_id:
            filename = msg.content.replace("[DOCUMENT:", "").replace("]", "")
            logger.debug(f"Procesando documento: {filename}")
            user_message = await media_service.process_document(
                msg.media_id, filename, access_token=wa_token, api_version=wa_version
            )
        
        # Analizar imagen si es necesario
        elif msg.message_type == "image" and msg.media_id:
            logger.debug("Analizando imagen...")
            # Construir contexto del negocio para el análisis
            business_context = dict(client.tools_config) if client.tools_config else {}
            business_context['business_name'] = client.business_name
            business_context['business_type'] = business_context.get('business_type', 'general')
            
            # Analizar la imagen con contexto del negocio
            image_analysis = await media_service.analyze_image(
                msg.media_id, 
                msg.content,  # caption original
                business_context,
                access_token=wa_token,
                api_version=wa_version,
            )
            
            # Construir mensaje con contexto claro para el chat principal
            original_caption = msg.content if msg.content and msg.content != "[Imagen recibida]" else ""
            if original_caption:
                user_message = (
                    f"[El cliente envió una imagen con el mensaje: \"{original_caption}\"]\n\n"
                    f"[Análisis de la imagen enviada por el cliente: {image_analysis}]\n\n"
                    f"Responde al cliente sobre lo que envió en la imagen, usando el análisis anterior. "
                    f"Si identificaste un producto del catálogo, da precios, disponibilidad y ofrece ayuda."
                )
            else:
                user_message = (
                    f"[El cliente envió una imagen sin texto adicional]\n\n"
                    f"[Análisis de la imagen enviada por el cliente: {image_analysis}]\n\n"
                    f"Responde al cliente sobre lo que envió en la imagen, usando el análisis anterior. "
                    f"Si identificaste un producto del catálogo, da precios, disponibilidad y ofrece ayuda."
                )
        
        # 6. Cargar historial de conversación
        memory = ConversationMemory(client.id, msg.phone_number)
        
        # ⚠️ VERIFICAR SI HAY INTERVENCIÓN HUMANA (desde Business Suite o Panel Admin)
        is_human_handled = await memory.is_human_handled()
        
        if is_human_handled:
            # Si hay intervención humana, solo guardar el mensaje pero NO responder con IA
            await memory.add_message("user", user_message)
            logger.info(f"Conversación manejada por humano - IA pausada para {msg.phone_number}")
            # No generar respuesta automática - el humano responderá desde el panel o Business Suite
            return
        
        # Si no hay intervención humana, procesar normalmente con IA
        # Agregar el mensaje actual del usuario al historial
        await memory.add_message("user", user_message)
        # Cargar historial completo (incluye el mensaje que acabamos de agregar)
        history = await memory.get_context_for_llm()
        
        # 7. Generar respuesta con Gemini
        logger.debug("Generando respuesta con Gemini...")
        
        response_text = await gemini_service.chat(
            message=user_message,
            history=history,
            client=client,
            customer=customer
        )
        
        # 8. Enviar respuesta
        await whatsapp_service.send_text_message(
            to=msg.phone_number,
            message=response_text,
            access_token=wa_token,
            phone_number_id=wa_phone_id,
            api_version=wa_version,
            client_id=client.id,
        )
        
        # 9. Guardar respuesta en memoria
        await memory.add_message("assistant", response_text)
        
        logger.debug(f"Conversación completada con {msg.phone_number}")
        
    except Exception as e:
        logger.error(f"Error manejando mensaje: {e}", exc_info=True)
        try:
            # Intentar enviar mensaje de error (necesitamos el client)
            client = await client_service.get_client_by_phone_id(msg.phone_number_id)
            if client and client.whatsapp_access_token:
                await whatsapp_service.send_text_message(
                    to=msg.phone_number,
                    message="Lo siento, ocurrió un error. Por favor intenta de nuevo en unos momentos.",
                    access_token=client.whatsapp_access_token,
                    phone_number_id=client.whatsapp_instance_id,
                    api_version=client.whatsapp_api_version or "v21.0",
                    client_id=client.id,
                )
        except Exception as send_err:
            logger.warning(f"No se pudo enviar mensaje de error al usuario: {send_err}")
