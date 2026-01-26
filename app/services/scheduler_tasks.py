"""
Funciones reutilizables para tareas programadas (recordatorios, confirmaciones).
Estas funciones pueden ser usadas tanto por endpoints HTTP como por el scheduler automático.
"""
from datetime import datetime, timedelta
from sqlalchemy import select, and_
import logging
import pytz

from app.core.database import AsyncSessionLocal
from app.models.tables import Client, Customer, Appointment
from app.services.whatsapp import whatsapp_service
from app.core.redis import ConversationMemory

logger = logging.getLogger(__name__)


async def send_appointment_reminders_task(hours_before: int = 24) -> dict:
    """
    Envía recordatorios de citas próximas.
    
    Args:
        hours_before: Horas de anticipación (default: 24)
    
    Returns:
        dict con status, reminders_sent, errors, window
    """
    try:
        now = datetime.now(pytz.UTC)
        reminder_window_start = now + timedelta(hours=hours_before - 1)
        reminder_window_end = now + timedelta(hours=hours_before + 1)
        
        sent_count = 0
        errors = []
        
        async with AsyncSessionLocal() as session:
            # Buscar citas en la ventana de tiempo
            result = await session.execute(
                select(Appointment, Customer, Client)
                .join(Customer, Appointment.customer_id == Customer.id)
                .join(Client, Appointment.client_id == Client.id)
                .where(
                    and_(
                        Appointment.start_time >= reminder_window_start,
                        Appointment.start_time <= reminder_window_end,
                        Appointment.status == "CONFIRMED",
                        Client.is_active == True
                    )
                )
            )
            
            appointments = result.all()
            
            for appointment, customer, client in appointments:
                try:
                    # Formatear fecha/hora
                    tz = pytz.timezone(client.tools_config.get('timezone', 'America/Santo_Domingo'))
                    local_time = appointment.start_time.astimezone(tz)
                    
                    # Crear mensaje de recordatorio
                    message = (
                        f"📅 *Recordatorio de Cita*\n\n"
                        f"Hola {customer.full_name or 'paciente'},\n\n"
                        f"Te recordamos que tienes una cita programada:\n\n"
                        f"🏥 *{client.business_name}*\n"
                        f"📆 Fecha: {local_time.strftime('%d de %B de %Y')}\n"
                        f"🕐 Hora: {local_time.strftime('%H:%M')}\n"
                    )
                    
                    if appointment.notes:
                        message += f"📋 Motivo: {appointment.notes}\n"
                    
                    message += (
                        f"\n¿Confirmas tu asistencia?\n"
                        f"Responde *CONFIRMAR* o *CANCELAR*"
                    )
                    
                    # Enviar recordatorio
                    await whatsapp_service.send_text_message(
                        to=customer.phone_number,
                        message=message,
                        client_id=client.id
                    )
                    
                    # Guardar el mensaje en Redis para mantener contexto
                    memory = ConversationMemory(client.id, customer.phone_number)
                    await memory.add_message("assistant", message)
                    
                    sent_count += 1
                    logger.debug(f"Recordatorio enviado a {customer.phone_number}")
                    
                except Exception as e:
                    error_msg = f"Error enviando a {customer.phone_number}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)
        
        return {
            "status": "completed",
            "reminders_sent": sent_count,
            "errors": errors,
            "window": {
                "start": reminder_window_start.isoformat(),
                "end": reminder_window_end.isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error en send_reminders: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "reminders_sent": 0,
            "errors": [str(e)]
        }


async def send_confirmation_requests_task(hours_before: int = 48) -> dict:
    """
    Envía solicitudes de confirmación para citas próximas.
    Similar a recordatorios pero con más anticipación.
    
    Args:
        hours_before: Horas de anticipación (default: 48)
    
    Returns:
        dict con status y confirmations_sent
    """
    try:
        now = datetime.now(pytz.UTC)
        window_start = now + timedelta(hours=hours_before - 2)
        window_end = now + timedelta(hours=hours_before + 2)
        
        sent_count = 0
        errors = []
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Appointment, Customer, Client)
                .join(Customer, Appointment.customer_id == Customer.id)
                .join(Client, Appointment.client_id == Client.id)
                .where(
                    and_(
                        Appointment.start_time >= window_start,
                        Appointment.start_time <= window_end,
                        Appointment.status == "CONFIRMED",
                        Client.is_active == True
                    )
                )
            )
            
            for appointment, customer, client in result.all():
                try:
                    tz = pytz.timezone(client.tools_config.get('timezone', 'America/Santo_Domingo'))
                    local_time = appointment.start_time.astimezone(tz)
                    
                    message = (
                        f"👋 *Confirmación de Cita*\n\n"
                        f"Hola {customer.full_name or 'paciente'},\n\n"
                        f"Queremos confirmar tu cita en *{client.business_name}*:\n\n"
                        f"📆 {local_time.strftime('%A %d de %B')}\n"
                        f"🕐 {local_time.strftime('%H:%M')}\n"
                    )
                    
                    if appointment.notes:
                        message += f"📋 {appointment.notes}\n"
                    
                    message += (
                        f"\n¿Podrás asistir?\n"
                        f"• Responde *SÍ* para confirmar\n"
                        f"• Responde *NO* para cancelar\n"
                        f"• Responde *CAMBIAR* para reagendar"
                    )
                    
                    await whatsapp_service.send_text_message(
                        to=customer.phone_number,
                        message=message,
                        client_id=client.id
                    )
                    
                    # Guardar el mensaje en Redis para mantener contexto
                    memory = ConversationMemory(client.id, customer.phone_number)
                    await memory.add_message("assistant", message)
                    
                    sent_count += 1
                    logger.debug(f"Confirmación enviada a {customer.phone_number}")
                    
                except Exception as e:
                    error_msg = f"Error enviando confirmación a {customer.phone_number}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)
        
        return {
            "status": "completed",
            "confirmations_sent": sent_count,
            "errors": errors
        }
        
    except Exception as e:
        logger.error(f"Error en send_confirmations: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "confirmations_sent": 0,
            "errors": [str(e)]
        }
