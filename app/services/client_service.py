import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Client, Customer
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class ClientService:
    """
    Servicio para gestionar Clients (tenants) y Customers.
    """
    
    async def get_client_by_phone_id(self, phone_number_id: str) -> Client | None:
        """
        Busca un Client por su WhatsApp Phone Number ID.
        Este es el identificador que viene en cada mensaje de Meta.
        
        Args:
            phone_number_id: ID del número de WhatsApp Business
            
        Returns:
            Client o None si no existe
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Client).where(
                    Client.whatsapp_instance_id == phone_number_id,
                    Client.is_active == True
                )
            )
            return result.scalar_one_or_none()
    
    async def get_or_create_customer(
        self,
        client_id: int,
        phone_number: str,
        full_name: str | None = None
    ) -> Customer:
        """
        Obtiene un Customer existente o crea uno nuevo.
        
        Args:
            client_id: ID del Client (tenant)
            phone_number: Número de WhatsApp del usuario
            full_name: Nombre del contacto (opcional)
            
        Returns:
            Customer existente o nuevo
        """
        async with AsyncSessionLocal() as session:
            # Buscar customer existente
            result = await session.execute(
                select(Customer).where(
                    Customer.client_id == client_id,
                    Customer.phone_number == phone_number
                )
            )
            customer = result.scalar_one_or_none()
            
            if customer:
                # Actualizar nombre si viene y no lo tenía
                if full_name and not customer.full_name:
                    customer.full_name = full_name
                    await session.commit()
                    await session.refresh(customer)
                return customer
            
            # Crear nuevo customer
            customer = Customer(
                client_id=client_id,
                phone_number=phone_number,
                full_name=full_name,
                data={}
            )
            session.add(customer)
            await session.commit()
            await session.refresh(customer)
            
            logger.debug(f"✨ Nuevo customer creado: {phone_number} para client {client_id}")
            return customer
    
    async def update_customer_data(
        self,
        customer_id: int,
        data: dict
    ) -> Customer:
        """
        Actualiza los datos flexibles de un Customer.
        Hace merge con los datos existentes.
        
        Args:
            customer_id: ID del Customer
            data: Diccionario con datos a actualizar/agregar
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Customer).where(Customer.id == customer_id)
            )
            customer = result.scalar_one_or_none()
            
            if customer:
                # Merge de datos
                current_data = customer.data or {}
                current_data.update(data)
                customer.data = current_data
                await session.commit()
                await session.refresh(customer)
            
            return customer
    
    async def get_customer_by_phone(
        self,
        client_id: int,
        phone_number: str
    ) -> Customer | None:
        """
        Busca un Customer por su número de teléfono.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Customer).where(
                    Customer.client_id == client_id,
                    Customer.phone_number == phone_number
                )
            )
            return result.scalar_one_or_none()


# Instancia global
client_service = ClientService()
