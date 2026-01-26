from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Client(Base):
    """
    TABLA MAESTRA (SaaS): Define la personalidad y herramientas de cada empresa.
    """
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    
    # Identificación y Seguridad
    business_name = Column(String, nullable=False)   # Ej: "Clínica Moreira"
    whatsapp_instance_id = Column(String, unique=True, index=True) # Ej: "clinica_moreira"
    is_active = Column(Boolean, default=True)        # Interruptor de pago
    
    # EL CEREBRO (Personalidad)
    # Aquí guardas: "Eres una recepcionista amable..."
    system_prompt_template = Column(Text, nullable=False) 
    
    # LA CAJA DE HERRAMIENTAS (Configuración JSON)
    # Aquí guardas IDs de calendarios, horarios, menús, etc.
    # Ejemplo Clínica: {"calendar_id": "c_123...", "timezone": "America/Santo_Domingo", "requires_insurance": true}
    # Ejemplo Pizzería: {"calendar_id": "c_456...", "timezone": "America/New_York", "menu_url": "http..."}
    tools_config = Column(JSON, default={}) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    

    # Relaciones
    customers = relationship("Customer", back_populates="client")
    appointments = relationship("Appointment", back_populates="client")


class Customer(Base):
    """
    TABLA DE USUARIOS (Pacientes / Comensales).
    Antes llamada 'Patient'. Ahora es genérica gracias al campo 'data'.
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id")) # Pertenece a un negocio específico
    
    # Datos universales (todos los negocios necesitan esto)
    phone_number = Column(String, index=True) 
    full_name = Column(String, nullable=True)
    
    # DATOS FLEXIBLES (JSON)
    # Clínica guarda: {"dob": "1990-01-01", "insurance": "Humano", "allergies": ["Nueces"]}
    # Pizzería guarda: {"address": "Calle 123", "favorite_pizza": "Pepperoni"}
    data = Column(JSON, default={})
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    client = relationship("Client", back_populates="customers")
    appointments = relationship("Appointment", back_populates="customer")


class Appointment(Base):
    """
    TABLA DE CITAS / RESERVAS.
    Sincronizada con Google Calendar.
    """
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    
    # Vinculación con Google (Vital para cancelar/reagendar)
    google_event_id = Column(String, unique=True, nullable=True)
    
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    
    status = Column(String, default="CONFIRMED") # CONFIRMED, CANCELLED, NO_SHOW
    
    # Detalles extra (Motivo consulta / Mesa reservada)
    notes = Column(Text, nullable=True)
    
    client = relationship("Client", back_populates="appointments")
    customer = relationship("Customer", back_populates="appointments")
