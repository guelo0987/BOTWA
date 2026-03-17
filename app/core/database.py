from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Motor de base de datos asíncrono
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENV_MODE == "dev",  # Log SQL solo en desarrollo
    future=True,
    pool_pre_ping=True,  # Verifica conexiones antes de usar
    pool_size=3,
    max_overflow=5,
    pool_timeout=10,
    pool_recycle=300,
    connect_args={
        "statement_cache_size": 0,  # Importante para Neon/PgBouncer
        "server_settings": {"jit": "off"}  # Optimización opcional
    }
)

# Fábrica de sesiones asíncronas
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Base para los modelos
Base = declarative_base()


async def init_db():
    """
    Crea todas las tablas en la base de datos.
    Llamar al inicio de la aplicación.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
