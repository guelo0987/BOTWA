"""
Servicio automático de tareas programadas usando APScheduler.
Este servicio ejecuta recordatorios y confirmaciones automáticamente sin necesidad de cron externo.
"""
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

from app.services.scheduler_tasks import (
    send_appointment_reminders_task,
    send_confirmation_requests_task
)

logger = logging.getLogger(__name__)

# Instancia global del scheduler
scheduler: AsyncIOScheduler = None


def get_scheduler() -> AsyncIOScheduler:
    """Obtiene la instancia global del scheduler."""
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    return scheduler


async def start_scheduler():
    """
    Inicia el scheduler automático con las tareas programadas.
    
    Tareas configuradas:
    - Recordatorios: Cada hora, busca citas que están a 24 horas
    - Confirmaciones: Cada 6 horas, busca citas que están a 48 horas
    """
    global scheduler
    scheduler = get_scheduler()
    
    if scheduler.running:
        logger.warning("Scheduler ya está corriendo")
        return
    
    # Agregar job para recordatorios (cada hora)
    scheduler.add_job(
        _run_reminders_task,
        trigger=CronTrigger(minute=0),  # Cada hora en el minuto 0
        id="send_reminders",
        name="Enviar recordatorios de citas (24h antes)",
        replace_existing=True,
        max_instances=1  # Solo una instancia a la vez
    )
    
    # Agregar job para confirmaciones (cada 6 horas)
    scheduler.add_job(
        _run_confirmations_task,
        trigger=CronTrigger(hour="*/6", minute=0),  # Cada 6 horas
        id="send_confirmations",
        name="Enviar confirmaciones de citas (48h antes)",
        replace_existing=True,
        max_instances=1
    )
    
    scheduler.start()
    logger.info("Scheduler automático iniciado")
    logger.info("   - Recordatorios: cada hora (24h antes de la cita)")
    logger.info("   - Confirmaciones: cada 6 horas (48h antes de la cita)")


async def stop_scheduler():
    """Detiene el scheduler automático."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("🛑 Scheduler automático detenido")
    scheduler = None


async def _run_reminders_task():
    """Wrapper para ejecutar la tarea de recordatorios."""
    try:
        logger.info("⏰ Ejecutando tarea de recordatorios...")
        result = await send_appointment_reminders_task(hours_before=24)
        logger.info(f"Recordatorios completados: {result.get('reminders_sent', 0)} enviados")
        if result.get('errors'):
            logger.warning(f"Errores en recordatorios: {len(result['errors'])}")
    except Exception as e:
        logger.error(f"Error ejecutando tarea de recordatorios: {e}", exc_info=True)


async def _run_confirmations_task():
    """Wrapper para ejecutar la tarea de confirmaciones."""
    try:
        logger.info("⏰ Ejecutando tarea de confirmaciones...")
        result = await send_confirmation_requests_task(hours_before=48)
        logger.info(f"Confirmaciones completadas: {result.get('confirmations_sent', 0)} enviadas")
        if result.get('errors'):
            logger.warning(f"Errores en confirmaciones: {len(result['errors'])}")
    except Exception as e:
        logger.error(f"Error ejecutando tarea de confirmaciones: {e}", exc_info=True)
