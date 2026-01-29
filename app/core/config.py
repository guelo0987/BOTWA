from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, ConfigDict
from functools import lru_cache
import re


class Settings(BaseSettings):
    """
    Configuración centralizada del bot.
    Todas las variables se cargan desde .env
    """
    
    ENV_MODE: str = "dev"
    LOG_LEVEL: str = "INFO"
    
    # ==========================================
    # BASE DE DATOS (PostgreSQL)
    # ==========================================
    DATABASE_URL: str = Field(alias="DATA_BASE_CONNECTION_STRING")
    
    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def convert_connection_string(cls, v: str) -> str:
        """
        Convierte connection string de formato ADO.NET a SQLAlchemy URI.
        
        Input:  Host=localhost;Port=5432;Database=mydb;Username=user;Password=pass
        Output: postgresql+asyncpg://user:pass@localhost:5432/mydb
        """
        if v.startswith('postgresql'):
            return v  # Ya está en formato correcto
        
        # Parsear formato ADO.NET
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
    
    # ==========================================
    # REDIS (Memoria de conversaciones)
    # ==========================================
    REDIS_URL: str
    # Timeouts para evitar "cuelgues" al conectar
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 3.0
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 3.0
    # Si es False, la app puede iniciar sin Redis (modo degradado)
    REDIS_REQUIRED: bool = True
    
    # ==========================================
    # WHATSAPP (API Oficial de Meta)
    # ==========================================
    # Token de acceso permanente de Meta
    WHATSAPP_ACCESS_TOKEN: str = Field(alias="WHATSAPP_TOKEN")
    
    # ID del número de teléfono de WhatsApp Business
    WHATSAPP_PHONE_NUMBER_ID: str = Field(alias="WHATSAPP_PHONE_ID")
    
    # Token de verificación para el webhook
    WHATSAPP_VERIFY_TOKEN: str
    
    # Versión de la API de Meta
    WHATSAPP_API_VERSION: str = "v21.0"
    
    # ==========================================
    # LLM (Google Gemini)
    # ==========================================
    GOOGLE_API_KEY: str = Field(alias="GEMINI_API_KEY")
    
    # Modelo de Gemini a usar
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    # ==========================================
    # GOOGLE CALENDAR
    # ==========================================
    GOOGLE_CREDENTIALS_PATH: str = "credentials/google_calendar_service.json"
    GOOGLE_CALENDAR_ID: str | None = None
    
    # ==========================================
    # EMAIL (SMTP) - Opcional
    # ==========================================
    SMTP_HOST: str | None = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str | None = None
    
    # ==========================================
    # CONFIGURACIÓN DEL BOT
    # ==========================================
    # Tiempo de expiración de sesión en Redis (segundos)
    SESSION_EXPIRE_SECONDS: int = 3600  # 1 hora
    
    # Máximo de mensajes en contexto
    MAX_CONTEXT_MESSAGES: int = 20

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True
    )

    @property
    def whatsapp_api_url(self) -> str:
        """URL base de la API de WhatsApp"""
        return f"https://graph.facebook.com/{self.WHATSAPP_API_VERSION}/{self.WHATSAPP_PHONE_NUMBER_ID}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
