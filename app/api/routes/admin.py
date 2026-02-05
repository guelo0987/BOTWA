"""
Rutas administrativas para el bot WhatsApp.
Incluye endpoints para gestión de cache, configuración y diagnóstico.
"""

from fastapi import APIRouter, HTTPException, Query
import logging

from app.core.redis import get_redis
from app.core.database import AsyncSessionLocal
from app.models.tables import Client
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter()


@router.delete("/catalog-cache/{client_id}")
async def invalidate_catalog_cache(client_id: int):
    """
    Invalida el cache del catálogo PDF para un cliente específico.
    
    Usar cuando:
    - Se sube un nuevo PDF de catálogo
    - Se cambia de catalog_source=manual a catalog_source=pdf
    - Se actualiza el catalog_pdf_key o catalog_pdf_url
    
    Args:
        client_id: ID del cliente en la base de datos
    
    Returns:
        Estado de la operación
    """
    try:
        redis = get_redis()
        cache_key = f"catalog_pdf_text:{client_id}"
        
        # Verificar si existe el cache
        cached = await redis.get(cache_key)
        if cached:
            await redis.delete(cache_key)
            logger.info(f"Cache de catálogo eliminado para client_id={client_id}")
            return {
                "status": "cache_cleared",
                "client_id": client_id,
                "message": "El cache del catálogo PDF ha sido eliminado. La próxima consulta descargará el PDF nuevamente."
            }
        else:
            return {
                "status": "no_cache",
                "client_id": client_id,
                "message": "No había cache de catálogo para este cliente."
            }
    except Exception as e:
        logger.error(f"Error invalidando cache para client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalog-cache/{client_id}/status")
async def get_catalog_cache_status(client_id: int):
    """
    Obtiene el estado del cache del catálogo PDF para un cliente.
    
    Args:
        client_id: ID del cliente en la base de datos
    
    Returns:
        Información sobre el cache (existe, tamaño aproximado, TTL)
    """
    try:
        redis = get_redis()
        cache_key = f"catalog_pdf_text:{client_id}"
        
        cached = await redis.get(cache_key)
        ttl = await redis.ttl(cache_key)
        
        if cached:
            return {
                "cached": True,
                "size_chars": len(cached),
                "ttl_seconds": ttl if ttl > 0 else None,
                "preview": cached[:200] + "..." if len(cached) > 200 else cached
            }
        else:
            return {
                "cached": False,
                "size_chars": 0,
                "ttl_seconds": None,
                "preview": None
            }
    except Exception as e:
        logger.error(f"Error obteniendo estado de cache para client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client/{client_id}/config")
async def get_client_config(client_id: int):
    """
    Obtiene la configuración actual de un cliente (tools_config).
    Útil para depuración y verificación de configuración de catálogo.
    
    Args:
        client_id: ID del cliente en la base de datos
    
    Returns:
        Configuración del cliente incluyendo catalog_source, catalog_pdf_key, etc.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Client).where(Client.id == client_id)
            )
            client = result.scalar_one_or_none()
        
        if not client:
            raise HTTPException(status_code=404, detail=f"Cliente {client_id} no encontrado")
        
        config = client.tools_config or {}
        
        return {
            "client_id": client_id,
            "business_name": client.business_name,
            "is_active": client.is_active,
            "catalog_source": config.get("catalog_source", "manual"),
            "catalog_pdf_key": config.get("catalog_pdf_key"),
            "catalog_pdf_url": config.get("catalog_pdf_url"),
            "business_type": config.get("business_type", "general"),
            "has_calendar": bool(config.get("calendar_id")),
            "has_professionals": bool(config.get("professionals")),
            "has_services": bool(config.get("services")),
            "has_catalog": bool(config.get("catalog")),
            "business_hours": config.get("business_hours", {"start": "08:00", "end": "18:00"}),
            "working_days": config.get("working_days", [1,2,3,4,5,6]),
            "full_config": config  # DEBUG: ver configuración completa
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo config para client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client/{client_id}/availability/{date}")
async def get_client_availability_debug(client_id: int, date: str):
    """
    Debug endpoint para ver disponibilidad de un cliente en una fecha específica.
    Muestra eventos existentes y slots disponibles.
    
    Args:
        client_id: ID del cliente
        date: Fecha en formato YYYY-MM-DD
    """
    try:
        from datetime import datetime
        from app.services.calendar import calendar_service
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Client).where(Client.id == client_id)
            )
            client = result.scalar_one_or_none()
        
        if not client:
            raise HTTPException(status_code=404, detail=f"Cliente {client_id} no encontrado")
        
        config = client.tools_config or {}
        calendar_id = config.get("calendar_id")
        
        if not calendar_id:
            raise HTTPException(status_code=400, detail="Cliente no tiene calendario configurado")
        
        fecha = datetime.strptime(date, "%Y-%m-%d")
        
        # Obtener slots disponibles
        slots = await calendar_service.get_available_slots(
            calendar_id=calendar_id,
            date=fecha,
            duration_minutes=config.get("slot_duration", 30),
            config=config
        )
        
        business_hours = config.get("business_hours", {"start": "08:00", "end": "18:00"})
        
        return {
            "client_id": client_id,
            "date": date,
            "calendar_id": calendar_id,
            "business_hours": business_hours,
            "slot_duration": config.get("slot_duration", 30),
            "available_slots": slots,
            "slots_count": len(slots),
            "first_slot": slots[0] if slots else None,
            "last_slot": slots[-1] if slots else None,
            "message": f"Si solo hay slots hasta 13:00 pero business_hours es hasta 18:00, hay eventos bloqueando el calendario después de las 13:00"
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usa YYYY-MM-DD")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en debug de disponibilidad: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
