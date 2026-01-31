"""
Funciones reutilizables para tareas programadas (recordatorios, confirmaciones).
Los recordatorios se envían solo por correo para evitar spam en WhatsApp.
"""
from datetime import datetime, timedelta
from sqlalchemy import select, and_
import logging
import pytz

from app.core.database import AsyncSessionLocal
from app.models.tables import Client, Customer, Appointment
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


async def send_appointment_reminders_task(hours_before: int = 24) -> dict:
    """
    Envía recordatorios de citas próximas por correo electrónico.
    No se envían por WhatsApp para evitar que Meta considere spam y bloquee la cuenta.
    
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
                    customer_email = (customer.data or {}).get("email") if customer.data else None
                    if not customer_email:
                        logger.debug(f"Sin email para recordatorio: {customer.phone_number}, se omite")
                        continue
                    
                    tz = pytz.timezone(client.tools_config.get('timezone', 'America/Santo_Domingo'))
                    local_time = appointment.start_time.astimezone(tz)
                    
                    notes_parts = (appointment.notes or "").split('\n')
                    servicio = notes_parts[0] if notes_parts else "Cita"
                    profesional_nombre = None
                    for prof in client.tools_config.get("professionals", []):
                        if prof.get("name") in (appointment.notes or ""):
                            profesional_nombre = prof.get("name")
                            break
                    
                    appointment_details = {
                        "servicio": servicio,
                        "profesional": profesional_nombre,
                    }
                    
                    ok = await email_service.send_reminder_email(
                        to_email=customer_email,
                        business_name=client.business_name,
                        business_type=client.tools_config.get("business_type", "salon"),
                        customer_name=customer.full_name or "Cliente",
                        appointment_date=local_time,
                        appointment_details=appointment_details,
                        hours_before=hours_before,
                    )
                    if ok:
                        sent_count += 1
                        logger.debug(f"Recordatorio por email enviado a {customer_email}")
                    
                except Exception as e:
                    error_msg = f"Error enviando recordatorio a {customer.phone_number}: {str(e)}"
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
    Envía solicitudes de confirmación por correo (48h antes).
    No se usa WhatsApp para evitar spam; solo email.
    
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
                    customer_email = (customer.data or {}).get("email") if customer.data else None
                    if not customer_email:
                        logger.debug(f"Sin email para confirmación: {customer.phone_number}, se omite")
                        continue
                    
                    tz = pytz.timezone(client.tools_config.get('timezone', 'America/Santo_Domingo'))
                    local_time = appointment.start_time.astimezone(tz)
                    
                    notes_parts = (appointment.notes or "").split('\n')
                    servicio = notes_parts[0] if notes_parts else "Cita"
                    profesional_nombre = None
                    for prof in client.tools_config.get("professionals", []):
                        if prof.get("name") in (appointment.notes or ""):
                            profesional_nombre = prof.get("name")
                            break
                    
                    appointment_details = {
                        "servicio": servicio,
                        "profesional": profesional_nombre,
                    }
                    
                    ok = await email_service.send_reminder_email(
                        to_email=customer_email,
                        business_name=client.business_name,
                        business_type=client.tools_config.get("business_type", "salon"),
                        customer_name=customer.full_name or "Cliente",
                        appointment_date=local_time,
                        appointment_details=appointment_details,
                        hours_before=hours_before,
                    )
                    if ok:
                        sent_count += 1
                        logger.debug(f"Confirmación por email enviada a {customer_email}")
                    
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
