#!/usr/bin/env python3
"""
Script para limpiar la caché de Redis (conversaciones, estados, etc.).
Ejecutar desde la raíz del proyecto: python scripts/clear_redis.py
"""
import asyncio
import sys
from pathlib import Path

# Asegurar que el proyecto esté en el path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


async def main():
    from app.core.config import settings
    import redis.asyncio as redis

    print("Conectando a Redis...")
    client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    try:
        await client.ping()
    except Exception as e:
        print(f"Error: No se pudo conectar a Redis: {e}")
        sys.exit(1)

    try:
        await client.flushdb()
        print("Redis cache limpiado correctamente.")
    except Exception as e:
        print(f"Error al limpiar Redis: {e}")
        sys.exit(1)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
