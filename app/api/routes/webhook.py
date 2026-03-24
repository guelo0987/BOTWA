from fastapi import APIRouter, Request, HTTPException, Query, BackgroundTasks
from fastapi.responses import PlainTextResponse
import hmac
import hashlib
import logging
import asyncio
import json
import time

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
        
        import json
        body = json.loads(body_bytes)
        logger.debug("Webhook recibido")
        
        webhook_data = WhatsAppWebhook(**body)
        
        if webhook_data.object != "whatsapp_business_account":
            return {"status": "ignored"}
            
        # --- VERIFICACIÓN DE FIRMA (X-Hub-Signature-256) PER-TENANT ---
        # Extraemos el phone_number_id del primer event (usualmente solo viene 1)
        phone_number_id = None
        for entry in webhook_data.entry:
            for change in entry.changes:
                value = change.value
                if hasattr(value, "metadata") and value.metadata:
                    phone_number_id = value.metadata.phone_number_id
                    break
            if phone_number_id:
                break
                
        if phone_number_id:
            client = await client_service.get_client_by_phone_id(phone_number_id)
            if client and client.whatsapp_app_secret:
                signature = request.headers.get("X-Hub-Signature-256", "")
                expected = "sha256=" + hmac.new(
                    client.whatsapp_app_secret.encode(),
                    body_bytes,
                    hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(signature, expected):
                    logger.warning(f"Webhook con firma inválida rechazado para client_id={client.id}")
                    raise HTTPException(status_code=401, detail="Invalid signature")
        # Si no hay secret, pasa la validación (útil para dev o clientes en setup)
        
        for entry in webhook_data.entry:
            for change in entry.changes:
                value = change.value
                
                # Procesar mensajes entrantes
                if change.field == "messages" and value.messages:
                    msg_count = len(value.messages)
                    msg_types = [m.type for m in value.messages]
                    logger.info(f"Webhook: {msg_count} mensaje(s) recibido(s), tipos={msg_types}")
                    for message in value.messages:
                        # --- DEDUPLICACIÓN ---
                        try:
                            redis = get_redis()
                            dedup_key = f"processed:{message.id}"
                            if await redis.get(dedup_key):
                                logger.info(f"Webhook: mensaje duplicado ignorado: {message.id}")
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
                                
                                # Per-tenant rate limit (100 msgs/min across all senders)
                                tenant_rate_key = f"rate:tenant:{processed.phone_number_id}"
                                tenant_count = await redis.incr(tenant_rate_key)
                                if tenant_count == 1:
                                    await redis.expire(tenant_rate_key, 60)
                                if tenant_count > 100:
                                    logger.warning(f"Tenant rate limit alcanzado para {processed.phone_number_id}")
                                    continue
                            except Exception:
                                pass  # Si Redis falla, no limitar
                            
                            logger.debug(f"[{processed.message_type}] {processed.contact_name}")
                            # Usar debounce para agrupar mensajes rápidos del mismo usuario
                            background_tasks.add_task(debounced_handle_message, processed)
                
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
            maps_link = f"https://maps.google.com/?q={lat},{lon}"
            loc_name = message.location.name or ""
            loc_address = message.location.address or ""
            parts = []
            if loc_name:
                parts.append(f"Nombre: {loc_name}")
            if loc_address:
                parts.append(f"Dirección: {loc_address}")
            parts.append(f"Coordenadas: {lat}, {lon}")
            parts.append(f"Google Maps: {maps_link}")
            content = f"[Ubicación del cliente]\n" + "\n".join(parts)
        
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


# ==========================================
# DEBOUNCE: Agrupa mensajes rápidos del mismo usuario
# ==========================================
DEBOUNCE_SECONDS = 10  # Esperar 10 segundos para agrupar mensajes

async def debounced_handle_message(msg: ProcessedMessage):
    """
    En vez de procesar cada mensaje inmediatamente, espera DEBOUNCE_SECONDS
    para ver si el usuario envía más mensajes. Si los envía, se combinan
    todos en un solo mensaje antes de procesarlos con la IA.
    
    Esto evita que el bot responda a "alma rosa 1" y "f.miguelmatias30@gmail.com"
    como dos conversaciones separadas.
    """
    # Audio y documentos: procesar inmediatamente (no se pueden combinar con texto)
    if msg.message_type in ("audio", "document"):
        logger.info(f"Debounce: bypass para {msg.message_type} de {msg.phone_number} (msg_id={msg.message_id})")
        await handle_message(msg)
        return

    # Imágenes y texto van al mismo debounce para combinarse correctamente
    logger.info(f"Debounce: encolando {msg.message_type} de {msg.phone_number} (msg_id={msg.message_id})")

    try:
        redis = get_redis()
        # Key única por usuario (client_phone_id + user_phone)
        debounce_key = f"debounce:{msg.phone_number_id}:{msg.phone_number}"
        gen_key = f"debounce_gen:{msg.phone_number_id}:{msg.phone_number}"
        
        # Guardar este mensaje en la cola de debounce
        msg_data = json.dumps({
            "content": msg.content,
            "message_id": msg.message_id,
            "message_type": msg.message_type,
            "phone_number": msg.phone_number,
            "phone_number_id": msg.phone_number_id,
            "contact_name": msg.contact_name,
            "media_id": msg.media_id,
            "timestamp": time.time()
        })
        
        await redis.rpush(debounce_key, msg_data)
        await redis.expire(debounce_key, 30)  # TTL de seguridad
        
        # Incrementar generación y capturar nuestro número
        my_gen = await redis.incr(gen_key)
        await redis.expire(gen_key, 30)
        
        logger.info(f"Debounce: msg encolado para {msg.phone_number}, gen={my_gen}, type={msg.message_type}")

        # Esperar a que lleguen más mensajes
        await asyncio.sleep(DEBOUNCE_SECONDS)

        # Verificar si somos la última generación (si no, otro mensaje llegó después)
        current_gen = await redis.get(gen_key)
        if current_gen and int(current_gen) != my_gen:
            logger.info(f"Debounce: gen {my_gen} descartada (actual={current_gen}) para {msg.phone_number}")
            return  # Otro mensaje llegó después, dejamos que ese se encargue

        logger.info(f"Debounce: gen {my_gen} procesando para {msg.phone_number}")
        
        # Somos la última generación: recoger todos los mensajes pendientes
        pending_msgs = await redis.lrange(debounce_key, 0, -1)
        await redis.delete(debounce_key)
        await redis.delete(gen_key)
        
        if not pending_msgs:
            return
        
        # Combinar todos los mensajes en uno solo
        messages = [json.loads(m) for m in pending_msgs]

        # Detectar si hay imágenes en los mensajes agrupados
        image_msgs = [m for m in messages if m["message_type"] == "image"]
        extra_media_ids = None

        if image_msgs:
            # Combinar: imágenes + cualquier texto que las acompañe
            text_parts = [m["content"] for m in messages if m["message_type"] == "text" and m.get("content")]
            caption = image_msgs[0].get("content") or ""
            if text_parts:
                caption = (caption + "\n" + "\n".join(text_parts)).strip()
            combined_content = caption or "[Imagen recibida]"
            combined_type = "image"
            combined_media_id = image_msgs[0].get("media_id")
            # Guardar media_ids adicionales si hay más de una imagen
            extra_media_ids = [m.get("media_id") for m in image_msgs[1:] if m.get("media_id")]
            logger.info(f"Debounce: combinando {len(image_msgs)} imagen(es) + {len(text_parts)} textos de {msg.phone_number}: {combined_content[:100]}...")
        elif len(messages) == 1:
            # Solo un mensaje, procesar normal
            combined_content = messages[0]["content"]
            combined_type = messages[0]["message_type"]
            combined_media_id = messages[0].get("media_id")
            logger.info(f"Debounce: 1 mensaje ({combined_type}) de {msg.phone_number}: {combined_content[:80]}...")
        else:
            # Múltiples mensajes de texto: combinar
            combined_content = "\n".join([m["content"] for m in messages if m["content"]])
            combined_type = "text"
            combined_media_id = None
            logger.info(f"Debounce: combinando {len(messages)} mensajes de {msg.phone_number}: {combined_content[:100]}...")

        # Crear un ProcessedMessage combinado
        combined_msg = ProcessedMessage(
            message_id=messages[-1]["message_id"],
            phone_number=msg.phone_number,
            phone_number_id=msg.phone_number_id,
            contact_name=msg.contact_name,
            message_type=combined_type,
            content=combined_content,
            media_id=combined_media_id,
            extra_media_ids=extra_media_ids or None
        )
        
        # Marcar como leído todos los mensajes individuales
        try:
            client = await client_service.get_client_by_phone_id(msg.phone_number_id)
            if client and client.whatsapp_access_token:
                for m in messages:
                    try:
                        await whatsapp_service.mark_as_read(
                            m["message_id"],
                            access_token=client.whatsapp_access_token,
                            phone_number_id=client.whatsapp_instance_id,
                            api_version=client.whatsapp_api_version or "v24.0",
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        
        await handle_message(combined_msg)
        
    except Exception as e:
        # Si el debounce falla, procesar normalmente
        logger.warning(f"Debounce fallido, procesando directo: {e}")
        await handle_message(msg)


async def handle_message(msg: ProcessedMessage):
    """
    Maneja un mensaje procesado con IA.
    Soporta texto, audio y documentos.
    """
    try:
        # 0. Lock de procesamiento + response guard para evitar respuestas duplicadas
        try:
            redis = get_redis()
            lock_key = f"processing:{msg.phone_number_id}:{msg.phone_number}"
            response_guard_key = f"response_guard:{msg.phone_number_id}:{msg.phone_number}"

            # Response guard: si ya respondimos hace menos de 8s, descartar
            recently_responded = await redis.get(response_guard_key)
            if recently_responded:
                logger.info(f"Response guard activo para {msg.phone_number}, descartando para evitar duplicado")
                return

            # Intentar adquirir lock con TTL de 60s (seguridad)
            acquired = await redis.set(lock_key, "1", nx=True, ex=60)
            if not acquired:
                # Ya hay un mensaje procesándose para este usuario — descartar
                logger.warning(f"Lock ya adquirido para {msg.phone_number}, descartando mensaje duplicado")
                return

            logger.info(f"handle_message: lock adquirido para {msg.phone_number}, type={msg.message_type}, msg_id={msg.message_id}")
        except Exception:
            pass  # Si Redis falla, continuar sin lock
        
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
        
        # 1.5. Verificar horario programado del bot
        tools_config = client.tools_config or {}
        if tools_config.get("bot_schedule_enabled"):
            try:
                import pytz
                from datetime import datetime as dt
                
                tz_name = tools_config.get("timezone", "America/Santo_Domingo")
                tz = pytz.timezone(tz_name)
                now = dt.now(tz)
                current_time_str = now.strftime("%H:%M")
                
                schedule_start = tools_config.get("bot_schedule_start", "08:00")
                schedule_end = tools_config.get("bot_schedule_end", "18:00")
                
                # Comparar como strings HH:MM (funciona para rangos dentro del mismo día)
                is_within_schedule = schedule_start <= current_time_str < schedule_end
                
                if not is_within_schedule:
                    off_hours_mode = tools_config.get("bot_out_of_hours_mode", "off")
                    logger.info(
                        f"Bot fuera de horario para {client.business_name} "
                        f"(actual={current_time_str}, rango={schedule_start}-{schedule_end}, modo={off_hours_mode})"
                    )
                    
                    if off_hours_mode == "message":
                        # Enviar mensaje personalizado de fuera de horario
                        off_hours_message = tools_config.get(
                            "bot_out_of_hours_message",
                            f"Gracias por tu mensaje. Nuestro horario de atención es de {schedule_start} a {schedule_end}. Te responderemos lo antes posible."
                        )
                        
                        # Deduplicar: no enviar el mensaje de fuera de horario si ya se envió recientemente
                        try:
                            redis = get_redis()
                            ooh_key = f"ooh_sent:{client.id}:{msg.phone_number}"
                            already_sent = await redis.get(ooh_key)
                            if not already_sent:
                                await whatsapp_service.send_text_message(
                                    to=msg.phone_number,
                                    message=off_hours_message,
                                    access_token=wa_token,
                                    phone_number_id=wa_phone_id,
                                    api_version=wa_version,
                                    client_id=client.id,
                                )
                                # No volver a enviar el mensaje por 30 minutos
                                await redis.set(ooh_key, "1", ex=1800)
                        except Exception as ooh_err:
                            logger.warning(f"Error enviando mensaje fuera de horario: {ooh_err}")
                    
                    # En ambos modos ("off" y "message"), NO continuar con la IA
                    return
            except Exception as schedule_err:
                logger.error(f"Error verificando horario del bot: {schedule_err}")
                # Si falla la verificación, continuar normalmente para no bloquear el bot
        
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
        
        # Analizar imagen(es) si es necesario
        elif msg.message_type == "image" and msg.media_id:
            # Construir contexto del negocio para el análisis
            business_context = dict(client.tools_config) if client.tools_config else {}
            business_context['business_name'] = client.business_name
            business_context['business_type'] = business_context.get('business_type', 'general')

            # Recopilar todos los media_ids (imagen principal + extras del debounce)
            all_media_ids = [msg.media_id]
            if msg.extra_media_ids:
                all_media_ids.extend(msg.extra_media_ids)

            logger.info(f"Analizando {len(all_media_ids)} imagen(es) para {msg.phone_number}")

            # Analizar todas las imágenes en paralelo
            import asyncio as _aio
            analysis_tasks = [
                media_service.analyze_image(
                    mid,
                    msg.content if i == 0 else "",  # caption solo en la primera
                    business_context,
                    access_token=wa_token,
                    api_version=wa_version,
                )
                for i, mid in enumerate(all_media_ids)
            ]
            analyses = await _aio.gather(*analysis_tasks)

            original_caption = msg.content if msg.content and msg.content != "[Imagen recibida]" else ""

            if len(analyses) == 1:
                # Una sola imagen — flujo original
                image_analysis = analyses[0]
                producto_identificado = "PRODUCTO IDENTIFICADO" in image_analysis.upper()

                if producto_identificado:
                    user_message = (
                        f"[El cliente envió una foto de un producto de nuestro catálogo"
                        f"{' con el mensaje: ' + chr(34) + original_caption + chr(34) if original_caption else ''}]\n\n"
                        f"[Análisis de la imagen: {image_analysis}]\n\n"
                        f"IMPORTANTE: La imagen SÍ es de nuestro catálogo. El producto fue identificado con los precios exactos del análisis. "
                        f"NO envíes saludo de bienvenida ni link del catálogo — el cliente YA tiene el catálogo y está preguntando por un producto específico. "
                        f"Usa los precios y el nombre del producto EXACTAMENTE como aparecen en el análisis de la imagen (no uses otros precios). "
                        f"Responde directamente con la info del producto y ofrece ayuda al cliente."
                    )
                elif original_caption:
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
            else:
                # Múltiples imágenes — combinar análisis numerados
                alguno_identificado = any("PRODUCTO IDENTIFICADO" in a.upper() for a in analyses)
                analyses_text = "\n\n".join(
                    f"[Imagen {i+1} de {len(analyses)}]: {a}" for i, a in enumerate(analyses)
                )

                if alguno_identificado:
                    user_message = (
                        f"[El cliente envió {len(analyses)} fotos de productos de nuestro catálogo"
                        f"{' con el mensaje: ' + chr(34) + original_caption + chr(34) if original_caption else ''}]\n\n"
                        f"{analyses_text}\n\n"
                        f"IMPORTANTE: Las imágenes son de nuestro catálogo. Los productos fueron identificados con los precios exactos del análisis. "
                        f"NO envíes saludo de bienvenida ni link del catálogo — el cliente YA tiene el catálogo y está preguntando por productos específicos. "
                        f"Usa los precios y nombres de los productos EXACTAMENTE como aparecen en cada análisis. "
                        f"Responde sobre TODOS los productos identificados y ofrece ayuda al cliente."
                    )
                else:
                    user_message = (
                        f"[El cliente envió {len(analyses)} imágenes"
                        f"{' con el mensaje: ' + chr(34) + original_caption + chr(34) if original_caption else ''}]\n\n"
                        f"{analyses_text}\n\n"
                        f"Responde al cliente sobre lo que envió en las imágenes, usando los análisis anteriores."
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
        
        # Notificar al dueño si es el primer mensaje de la conversación
        if len(history) == 1 and client.notification_email:
            try:
                from app.services.email_service import email_service
                asyncio.create_task(
                    email_service.send_new_conversation_email(
                        to_email=client.notification_email,
                        business_name=client.business_name,
                        customer_name=customer.full_name or "Cliente",
                        customer_phone=customer.phone_number,
                        first_message=user_message
                    )
                )
            except Exception as e:
                logger.error(f"Error al intentar enviar correo de nueva conversación: {e}")
        
        # 7. Generar respuesta con Gemini
        logger.debug("Generando respuesta con Gemini...")
        
        response_text = await gemini_service.chat(
            message=user_message,
            history=history,
            client=client,
            customer=customer
        )
        
        # 8. Enviar respuesta
        result = await whatsapp_service.send_text_message(
            to=msg.phone_number,
            message=response_text,
            access_token=wa_token,
            phone_number_id=wa_phone_id,
            api_version=wa_version,
            client_id=client.id,
        )
        
        # 8.5 Guardar message_id enviado para evitar auto-respuestas (echo)
        if result and "messages" in result:
            sent_msg_id = result["messages"][0].get("id")
            if sent_msg_id:
                await memory.save_sent_message_id(sent_msg_id)
        
        # 8.6 Response guard: evitar que otro handle_message responda de nuevo
        try:
            redis = get_redis()
            response_guard_key = f"response_guard:{msg.phone_number_id}:{msg.phone_number}"
            await redis.set(response_guard_key, "1", ex=8)  # 8s guard (debounce es 10s)
        except Exception:
            pass

        # 9. Guardar respuesta en memoria
        await memory.add_message("assistant", response_text)

        logger.info(f"handle_message: completado para {msg.phone_number}, type={msg.message_type}")
        
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
    finally:
        # Siempre liberar el lock de procesamiento
        try:
            redis = get_redis()
            lock_key = f"processing:{msg.phone_number_id}:{msg.phone_number}"
            await redis.delete(lock_key)
        except Exception:
            pass
