"""
Endpoints para tareas programadas (recordatorios, confirmaciones).
Estos endpoints pueden ser llamados manualmente o por un cron job externo.
El scheduler automático también ejecuta estas tareas internamente.
"""
from fastapi import APIRouter, HTTPException, Header, status
from datetime import datetime, timedelta
from sqlalchemy import select, and_
import logging
import pytz

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.tables import Client, Customer, Appointment
from app.services.scheduler_tasks import (
    send_appointment_reminders_task,
    send_confirmation_requests_task
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/send-reminders",
    status_code=status.HTTP_200_OK,
    summary="Enviar recordatorios de citas",
    description="Envía recordatorios por correo electrónico para citas próximas (no por WhatsApp para evitar spam).",
    responses={
        200: {
            "description": "Recordatorios enviados correctamente",
            "content": {
                "application/json": {
                    "example": {
                        "status": "completed",
                        "reminders_sent": 5,
                        "errors": [],
                        "window": {
                            "start": "2026-01-23T10:00:00Z",
                            "end": "2026-01-23T12:00:00Z"
                        }
                    }
                }
            }
        },
        403: {"description": "API key inválida"},
        500: {"description": "Error interno del servidor"}
    }
)
async def send_appointment_reminders(
    hours_before: int = 24,
    x_api_key: str | None = Header(None, alias="X-API-Key", description="API key para autenticación")
) -> dict:
    """
    Envía recordatorios de citas próximas por correo electrónico.
    
    Busca citas dentro de la ventana de tiempo y envía recordatorios por email
    (no por WhatsApp para evitar que Meta considere spam).
    
    **Nota:** Esta tarea también se ejecuta automáticamente cada hora.
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/scheduler/send-reminders?hours_before=24" \
         -H "X-API-Key: your-token"
    ```
    """
    # Verificar API key si está configurada
    expected_key = settings.WHATSAPP_VERIFY_TOKEN
    if x_api_key and x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    
    try:
        result = await send_appointment_reminders_task(hours_before=hours_before)
        
        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Unknown error")
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en send_reminders endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/send-confirmations",
    status_code=status.HTTP_200_OK,
    summary="Enviar solicitudes de confirmación",
    description="Envía solicitudes de confirmación por correo para citas próximas (no por WhatsApp).",
    responses={
        200: {
            "description": "Confirmaciones enviadas correctamente",
            "content": {
                "application/json": {
                    "example": {
                        "status": "completed",
                        "confirmations_sent": 3,
                        "errors": []
                    }
                }
            }
        },
        403: {"description": "API key inválida"},
        500: {"description": "Error interno del servidor"}
    }
)
async def send_confirmation_requests(
    hours_before: int = 48,
    x_api_key: str | None = Header(None, alias="X-API-Key", description="API key para autenticación")
) -> dict:
    """
    Envía solicitudes de confirmación por correo para citas próximas.
    
    Similar a recordatorios pero con más anticipación (por defecto 48 horas).
    Se envía solo por email (no por WhatsApp).
    
    **Nota:** Esta tarea también se ejecuta automáticamente cada 6 horas.
    """
    expected_key = settings.WHATSAPP_VERIFY_TOKEN
    if x_api_key and x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    
    try:
        result = await send_confirmation_requests_task(hours_before=hours_before)
        
        if result.get("status") == "error":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.get("error", "Unknown error")
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en send_confirmations endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get(
    "/pending-appointments",
    status_code=status.HTTP_200_OK,
    summary="Listar citas pendientes",
    description="Obtiene una lista de citas confirmadas para los próximos días.",
    responses={
        200: {
            "description": "Lista de citas obtenida correctamente",
            "content": {
                "application/json": {
                    "example": {
                        "total": 10,
                        "days_ahead": 7,
                        "appointments": [
                            {
                                "id": 1,
                                "google_event_id": "event123",
                                "start_time": "2026-01-23T10:00:00Z",
                                "end_time": "2026-01-23T10:30:00Z",
                                "status": "CONFIRMED",
                                "notes": "Consulta general",
                                "customer": {"name": "Juan Pérez", "phone": "18091234567"},
                                "client": {"name": "Clínica Ejemplo"}
                            }
                        ]
                    }
                }
            }
        },
        500: {"description": "Error interno del servidor"}
    }
)
async def get_pending_appointments(
    days_ahead: int = 7,
    x_api_key: str | None = Header(None, alias="X-API-Key", description="API key para autenticación")
) -> dict:
    """
    Lista las citas pendientes para los próximos días.
    
    Útil para dashboards, monitoreo o reportes. Retorna todas las citas
    confirmadas dentro del rango de días especificado.
    """
    try:
        now = datetime.now(pytz.UTC)
        end_date = now + timedelta(days=days_ahead)
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Appointment, Customer, Client)
                .join(Customer, Appointment.customer_id == Customer.id)
                .join(Client, Appointment.client_id == Client.id)
                .where(
                    and_(
                        Appointment.start_time >= now,
                        Appointment.start_time <= end_date,
                        Appointment.status == "CONFIRMED"
                    )
                )
                .order_by(Appointment.start_time)
            )
            
            appointments = []
            for apt, customer, client in result.all():
                appointments.append({
                    "id": apt.id,
                    "google_event_id": apt.google_event_id,
                    "start_time": apt.start_time.isoformat(),
                    "end_time": apt.end_time.isoformat(),
                    "status": apt.status,
                    "notes": apt.notes,
                    "customer": {
                        "name": customer.full_name,
                        "phone": customer.phone_number
                    },
                    "client": {
                        "name": client.business_name
                    }
                })
        
        return {
            "total": len(appointments),
            "days_ahead": days_ahead,
            "appointments": appointments
        }
        
    except Exception as e:
        logger.error(f"Error listando citas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
