from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
import logging

from app.core.config import settings
from app.core.database import init_db
from app.core.redis import init_redis, close_redis
from app.api.routes import webhook
from app.api.routes import scheduler
from app.services.auto_scheduler import start_scheduler, stop_scheduler

# Configurar logging
import sys
from logging.handlers import RotatingFileHandler

# Crear directorio de logs si no existe
import os
os.makedirs("logs", exist_ok=True)

# Configurar logging a archivo Y consola
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
log_level = logging.DEBUG if settings.ENV_MODE == "dev" else logging.WARNING

# Handler para archivo (rotativo, máximo 10MB, 5 archivos de backup)
file_handler = RotatingFileHandler(
    "logs/app.log",
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setLevel(log_level)
file_handler.setFormatter(logging.Formatter(log_format))

# Handler para consola
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(log_level)
console_handler.setFormatter(logging.Formatter(log_format))

# Configurar root logger
root_logger = logging.getLogger()
root_logger.setLevel(log_level)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Maneja el ciclo de vida de la aplicación.
    Se ejecuta al iniciar y al cerrar.
    """
    # ===== STARTUP =====
    logger.info("🚀 Iniciando aplicación...")
    
    # Inicializar base de datos
    logger.info("📦 Conectando a PostgreSQL...")
    await init_db()
    logger.info("PostgreSQL conectado")
    
    # Inicializar Redis
    logger.info("🔴 Conectando a Redis...")
    await init_redis()
    logger.info("Redis conectado")
    
    # Iniciar scheduler automático
    logger.info("⏰ Iniciando scheduler automático...")
    await start_scheduler()
    
    logger.info("🤖 Bot WhatsApp listo!")
    logger.info(f"📱 Phone Number ID: {settings.WHATSAPP_PHONE_NUMBER_ID}")
    
    yield
    
    # ===== SHUTDOWN =====
    logger.info("Cerrando aplicación...")
    
    # Detener scheduler automático
    await stop_scheduler()
    
    await close_redis()
    logger.info("Conexiones cerradas")


# Crear aplicación FastAPI
app = FastAPI(
    title="WhatsApp Bot API",
    description="Bot de WhatsApp con IA usando Gemini, PostgreSQL y Redis",
    version="1.0.0",
    lifespan=lifespan
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar dominios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# RUTAS
# ==========================================

# Incluir routers
app.include_router(webhook.router, prefix="/webhook", tags=["WhatsApp"])
app.include_router(scheduler.router, prefix="/scheduler", tags=["Scheduler"])


@app.get("/", tags=["Root"])
async def root():
    """Ruta raíz"""
    return {
        "message": "WhatsApp Bot API",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check para verificar el estado de los servicios.
    Útil para monitoreo y load balancers.
    """
    from app.core.redis import get_redis
    
    services = {
        "api": "healthy",
        "redis": "unknown",
        "database": "unknown"
    }
    
    # Verificar Redis
    try:
        redis = get_redis()
        await redis.ping()
        services["redis"] = "healthy"
    except Exception as e:
        services["redis"] = f"unhealthy: {str(e)}"
    
    # Verificar Database (simple check)
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        services["database"] = "healthy"
    except Exception as e:
        services["database"] = f"unhealthy: {str(e)}"
    
    all_healthy = all(v == "healthy" for v in services.values())
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": settings.ENV_MODE,
        "services": services
    }


# ==========================================
# MANEJO DE ERRORES
# ==========================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Manejador global de excepciones"""
    logger.error(f"Error no manejado: {exc}", exc_info=True)
    return {
        "error": "Internal server error",
        "detail": str(exc) if settings.ENV_MODE == "dev" else "An error occurred"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENV_MODE == "dev"
    )
