from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, ConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Configuración centralizada. TODO se carga desde .env"""
    
    ENV_MODE: str
    LOG_LEVEL: str
    
    # --- Base de Datos ---
    DATABASE_URL: str = Field(alias="DATA_BASE_CONNECTION_STRING")
    
    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def convert_connection_string(cls, v: str) -> str:
        """Convierte ADO.NET → SQLAlchemy URI si es necesario."""
        # Convertir esquema
        if v.startswith('postgresql://'):
            v = v.replace('postgresql://', 'postgresql+asyncpg://', 1)
        elif not v.startswith('postgresql+asyncpg://'):
            # Si no empieza con el esquema correcto, intentar parsear estilo ADO.NET (legacy logic)
            params = {}
            for part in v.split(';'):
                if '=' in part:
                    key, value = part.split('=', 1)
                    params[key.strip().lower()] = value.strip()
            host = params.get('host', 'localhost')
            port = params.get('port', '5432')
            database = params.get('database', 'postgres')
            username = params.get('username', 'postgres')
            password = params.get('password', '')
            v = f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"

        # Limpiar parámetros de query que rompen asyncpg
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        
        parsed = urlparse(v)
        query_params = parse_qs(parsed.query)
        
        # asyncpg no soporta 'sslmode', 'channel_binding', ni 'pgbouncer' en kwargs
        # Se deben manejar via connect_args o dejar que el driver negocie
        for bad_param in ['sslmode', 'channel_binding', 'pgbouncer']:
            if bad_param in query_params:
                del query_params[bad_param]
        
        # Reconstruir URL
        new_query = urlencode(query_params, doseq=True)
        v = urlunparse(parsed._replace(query=new_query))
        
        return v
    
    # --- Redis ---
    REDIS_URL: str
    REDIS_CONNECT_TIMEOUT_SECONDS: float
    REDIS_SOCKET_TIMEOUT_SECONDS: float
    REDIS_REQUIRED: bool
    
    # --- WhatsApp (solo webhook global) ---
    WHATSAPP_VERIFY_TOKEN: str
    WHATSAPP_APP_SECRET: str | None = None
    
    # --- Gemini (LLM) ---
    GOOGLE_API_KEY: str = Field(alias="GEMINI_API_KEY")
    GEMINI_MODEL: str
    
    # --- Google Calendar ---
    GOOGLE_CREDENTIALS_PATH: str
    
    # --- Email (SMTP) ---
    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str | None = None
    
    # --- Supabase S3 (catálogos PDF) ---
    SUPABASE_S3_ACCESS_KEY_ID: str | None = None
    SUPABASE_S3_SECRET_ACCESS_KEY: str | None = None
    SUPABASE_S3_ENDPOINT: str | None = None
    SUPABASE_S3_REGION: str | None = None
    SUPABASE_BUCKET_CATALOGS: str | None = None
    CATALOG_PDF_CACHE_TTL_SECONDS: int
    
    # --- Bot ---
    SESSION_EXPIRE_SECONDS: int
    MAX_CONTEXT_MESSAGES: int
    
    # --- Seguridad ---
    SCHEDULER_API_KEY: str | None = None

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
