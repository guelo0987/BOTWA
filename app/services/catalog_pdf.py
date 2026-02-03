"""
Servicio para catálogo en PDF desde Supabase Storage.
Gemini extrae el texto del PDF (incl. escaneados/imágenes), se cachea en Redis.
"""
import asyncio
import logging

from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

CATALOG_PDF_CACHE_PREFIX = "catalog_pdf_text:"


def _download_pdf_from_s3(bucket: str, key: str) -> bytes:
    """Descarga el PDF desde Supabase Storage vía API S3-compatible (síncrono)."""
    import boto3
    if not settings.SUPABASE_S3_ACCESS_KEY_ID or not settings.SUPABASE_S3_SECRET_ACCESS_KEY or not settings.SUPABASE_S3_ENDPOINT:
        raise ValueError(
            "SUPABASE_S3_ACCESS_KEY_ID, SUPABASE_S3_SECRET_ACCESS_KEY y SUPABASE_S3_ENDPOINT deben estar configurados"
        )
    client = boto3.client(
        "s3",
        endpoint_url=settings.SUPABASE_S3_ENDPOINT,
        region_name=getattr(settings, "SUPABASE_S3_REGION", "us-east-2"),
        aws_access_key_id=settings.SUPABASE_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.SUPABASE_S3_SECRET_ACCESS_KEY,
    )
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


async def get_catalog_text(client_id: int, config: dict) -> str | None:
    """
    Obtiene el texto del catálogo PDF: desde caché (Redis) o descargando
    de Supabase, extrayendo texto con Gemini y cacheando.

    Requiere en config: catalog_source == "pdf" y catalog_pdf_key (path en el bucket).
    Opcional: catalog_pdf_url (si se prefiere descargar por URL pública).

    Returns:
        Texto del catálogo o None si no hay config, error o PDF vacío.
    """
    if config.get("catalog_source") != "pdf":
        return None
    pdf_key = config.get("catalog_pdf_key")
    pdf_url = config.get("catalog_pdf_url")
    if not pdf_key and not pdf_url:
        return None

    redis = get_redis()
    cache_key = f"{CATALOG_PDF_CACHE_PREFIX}{client_id}"
    ttl = getattr(settings, "CATALOG_PDF_CACHE_TTL_SECONDS", 604800)

    # 1) Caché
    try:
        cached = await redis.get(cache_key)
        if cached and len(cached) > 50:
            return cached
    except Exception as e:
        logger.warning("Redis cache catalog_pdf: %s", e)

    # 2) Descargar PDF
    pdf_bytes: bytes | None = None
    if pdf_url:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=30.0) as client_http:
                r = await client_http.get(pdf_url)
                r.raise_for_status()
                pdf_bytes = r.content
        except Exception as e:
            logger.error("Error descargando catalog_pdf_url para client %s: %s", client_id, e)
            return None
    elif pdf_key:
        bucket = getattr(settings, "SUPABASE_BUCKET_CATALOGS", "catalogs")
        try:
            pdf_bytes = await asyncio.to_thread(
                _download_pdf_from_s3, bucket, pdf_key
            )
        except Exception as e:
            logger.error("Error descargando catalog_pdf_key para client %s: %s", client_id, e)
            return None
    else:
        return None

    if not pdf_bytes or len(pdf_bytes) < 100:
        logger.warning("PDF de catálogo vacío o muy pequeño para client %s", client_id)
        return None

    # 3) Extraer texto con Gemini (PDFs nativos y escaneados/imágenes)
    from app.services.gemini import gemini_service
    try:
        text = await gemini_service.extract_text_from_pdf(pdf_bytes)
    except Exception as e:
        logger.error("Error extrayendo texto del PDF con Gemini para client %s: %s", client_id, e)
        return None

    if not text or len(text.strip()) < 50:
        logger.warning("Texto extraído del PDF insuficiente para client %s", client_id)
        return None

    # 4) Cachear (truncar si es enorme)
    if len(text) > 500_000:
        text = text[:500_000] + "\n\n[... catálogo truncado ...]"
    try:
        await redis.set(cache_key, text, ex=ttl)
    except Exception as e:
        logger.warning("No se pudo cachear texto del catálogo: %s", e)

    return text
