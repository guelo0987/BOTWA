from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


# ==========================================
# SCHEMAS PARA WEBHOOK DE META WHATSAPP API
# ==========================================

class WhatsAppProfile(BaseModel):
    """Perfil del usuario de WhatsApp"""
    name: str


class WhatsAppContact(BaseModel):
    """Información de contacto"""
    profile: WhatsAppProfile
    wa_id: str  # Número de WhatsApp


class WhatsAppTextMessage(BaseModel):
    """Mensaje de texto"""
    body: str


class WhatsAppImageMessage(BaseModel):
    """Mensaje con imagen"""
    id: str
    mime_type: str
    sha256: str
    caption: str | None = None


class WhatsAppAudioMessage(BaseModel):
    """Mensaje de audio"""
    id: str
    mime_type: str
    sha256: str
    voice: bool = False


class WhatsAppDocumentMessage(BaseModel):
    """Mensaje con documento"""
    id: str
    mime_type: str
    sha256: str
    filename: str | None = None
    caption: str | None = None


class WhatsAppLocationMessage(BaseModel):
    """Mensaje de ubicación"""
    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None


class WhatsAppMessage(BaseModel):
    """Mensaje recibido de WhatsApp"""
    from_: str = Field(..., alias="from")  # Número del remitente
    id: str  # ID del mensaje
    timestamp: str
    type: str  # text, image, audio, document, location, etc.
    
    # Contenido según el tipo
    text: WhatsAppTextMessage | None = None
    image: WhatsAppImageMessage | None = None
    audio: WhatsAppAudioMessage | None = None
    document: WhatsAppDocumentMessage | None = None
    location: WhatsAppLocationMessage | None = None

    model_config = ConfigDict(populate_by_name=True)


class WhatsAppMetadata(BaseModel):
    """Metadata del mensaje"""
    display_phone_number: str
    phone_number_id: str


class WhatsAppValue(BaseModel):
    """Valor del cambio en el webhook"""
    messaging_product: str
    metadata: WhatsAppMetadata
    contacts: list[WhatsAppContact] | None = None
    messages: list[WhatsAppMessage] | None = None
    statuses: list[dict] | None = None  # Para actualizaciones de estado


class WhatsAppChange(BaseModel):
    """Cambio notificado por el webhook"""
    value: WhatsAppValue
    field: str


class WhatsAppEntry(BaseModel):
    """Entrada del webhook"""
    id: str
    changes: list[WhatsAppChange]


class WhatsAppWebhook(BaseModel):
    """
    Estructura completa del webhook de Meta WhatsApp API.
    
    Ejemplo de payload:
    {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "PHONE_NUMBER",
                        "phone_number_id": "PHONE_NUMBER_ID"
                    },
                    "contacts": [{"profile": {"name": "NAME"}, "wa_id": "WHATSAPP_ID"}],
                    "messages": [{"from": "SENDER", "id": "MSG_ID", "timestamp": "TIMESTAMP", "type": "text", "text": {"body": "MESSAGE"}}]
                },
                "field": "messages"
            }]
        }]
    }
    """
    object: str
    entry: list[WhatsAppEntry]


# ==========================================
# SCHEMAS DE RESPUESTA
# ==========================================

class MessageResponse(BaseModel):
    """Respuesta estándar del bot"""
    success: bool
    message: str
    data: dict | None = None


class HealthResponse(BaseModel):
    """Respuesta del health check"""
    status: str
    timestamp: datetime
    services: dict


# ==========================================
# SCHEMAS INTERNOS
# ==========================================

class ProcessedMessage(BaseModel):
    """Mensaje procesado internamente"""
    phone_number: str  # Número del remitente
    phone_number_id: str  # ID del número de WhatsApp Business
    message_id: str  # ID del mensaje
    message_type: str  # text, image, audio, document
    content: str  # Texto o descripción
    contact_name: str  # Nombre del contacto
    media_id: str | None = None  # ID del media si aplica
    raw_data: dict | None = None  # Datos originales
