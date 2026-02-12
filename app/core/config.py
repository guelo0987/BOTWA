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
        if v.startswith('postgresql'):
            return v
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
        return f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"
    
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
    ADMIN_API_KEY: str | None = None
    ALLOWED_ORIGINS: str

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
