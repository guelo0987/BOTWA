from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import asyncio
import logging
import pytz

from app.core.config import settings

logger = logging.getLogger(__name__)

# Scopes necesarios para Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']


class CalendarService:
    """
    Servicio para interactuar con Google Calendar.
    Permite crear, buscar y cancelar citas.
    """
    
    def __init__(self):
        self.credentials = None
        self.service = None
        self._initialize()
    
    def _initialize(self):
        """Inicializa las credenciales y el servicio."""
        try:
            self.credentials = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_CREDENTIALS_PATH,
                scopes=SCOPES
            )
            self.service = build('calendar', 'v3', credentials=self.credentials)
            logger.debug("Google Calendar inicializado")
        except Exception as e:
            logger.error(f"Error inicializando Calendar: {e}")
    
    def _get_timezone(self, config: dict) -> str:
        """Obtiene la zona horaria de la configuración."""
        return config.get('timezone', 'America/Santo_Domingo')
    
    async def get_available_slots(
        self,
        calendar_id: str,
        date: datetime,
        duration_minutes: int = 30,
        config: dict | None = None
    ) -> list[dict]:
        """
        Obtiene los horarios disponibles para una fecha.
        
        Args:
            calendar_id: ID del calendario
            date: Fecha a consultar
            duration_minutes: Duración de cada slot en minutos
            config: Configuración del negocio (business_hours)
            
        Returns:
            Lista de slots disponibles [{"start": "09:00", "end": "09:30"}, ...]
        """
        try:
            config = config or {}
            tz_str = self._get_timezone(config)
            tz = pytz.timezone(tz_str)
            
            # Horarios de negocio
            business_hours = config.get('business_hours', {'start': '08:00', 'end': '18:00'})
            start_hour, start_min = map(int, business_hours['start'].split(':'))
            end_hour, end_min = map(int, business_hours['end'].split(':'))
            
            # Inicio y fin del día
            day_start = tz.localize(datetime(date.year, date.month, date.day, start_hour, start_min))
            day_end = tz.localize(datetime(date.year, date.month, date.day, end_hour, end_min))
            
            # Obtener eventos existentes
            events_result = await asyncio.to_thread(
                self.service.events().list(
                    calendarId=calendar_id,
                    timeMin=day_start.isoformat(),
                    timeMax=day_end.isoformat(),
                    singleEvents=True,
                    orderBy='startTime'
                ).execute
            )
            
            events = events_result.get('items', [])
            
            # Crear lista de slots ocupados
            busy_slots = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                busy_slots.append({
                    'start': datetime.fromisoformat(start.replace('Z', '+00:00')),
                    'end': datetime.fromisoformat(end.replace('Z', '+00:00'))
                })
            
            # Generar slots disponibles
            available = []
            current = day_start
            
            while current + timedelta(minutes=duration_minutes) <= day_end:
                slot_end = current + timedelta(minutes=duration_minutes)
                
                # Verificar si el slot está libre
                is_free = True
                for busy in busy_slots:
                    if not (slot_end <= busy['start'] or current >= busy['end']):
                        is_free = False
                        break
                
                if is_free:
                    available.append({
                        'start': current.strftime('%H:%M'),
                        'end': slot_end.strftime('%H:%M'),
                        'datetime': current.isoformat()
                    })
                
                current = slot_end
            
            return available
            
        except Exception as e:
            logger.error(f"Error obteniendo disponibilidad: {e}")
            return []
    
    async def create_appointment(
        self,
        calendar_id: str,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: str = "",
        attendee_phone: str = "",
        config: dict | None = None
    ) -> dict | None:
        """
        Crea una cita en Google Calendar.
        
        Args:
            calendar_id: ID del calendario
            title: Título del evento
            start_time: Inicio de la cita
            end_time: Fin de la cita
            description: Descripción/notas
            attendee_phone: Teléfono del paciente
            config: Configuración del negocio
            
        Returns:
            Evento creado o None si falla
        """
        try:
            config = config or {}
            tz_str = self._get_timezone(config)
            
            event = {
                'summary': title,
                'description': f"{description}\n\nTeléfono: {attendee_phone}",
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': tz_str,
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': tz_str,
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 60},
                        {'method': 'popup', 'minutes': 15},
                    ],
                },
            }
            
            created_event = await asyncio.to_thread(
                self.service.events().insert(
                    calendarId=calendar_id,
                    body=event
                ).execute
            )
            
            logger.info(f"Cita creada: {created_event.get('id')}")
            return created_event
            
        except Exception as e:
            logger.error(f"Error creando cita: {e}")
            return None
    
    async def cancel_appointment(
        self,
        calendar_id: str,
        event_id: str
    ) -> bool:
        """
        Cancela una cita existente.
        
        Args:
            calendar_id: ID del calendario
            event_id: ID del evento a cancelar
            
        Returns:
            True si se canceló correctamente
        """
        try:
            await asyncio.to_thread(
                self.service.events().delete(
                    calendarId=calendar_id,
                    eventId=event_id
                ).execute
            )
            
            logger.debug(f"Cita cancelada: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelando cita: {e}")
            return False
    
    async def get_appointments(
        self,
        calendar_id: str,
        phone_number: str,
        config: dict | None = None
    ) -> list[dict]:
        """
        Busca citas de un paciente por su teléfono.
        
        Args:
            calendar_id: ID del calendario
            phone_number: Teléfono del paciente
            config: Configuración del negocio
            
        Returns:
            Lista de citas encontradas
        """
        try:
            config = config or {}
            tz_str = self._get_timezone(config)
            tz = pytz.timezone(tz_str)
            
            # Buscar desde hoy en adelante
            now = datetime.now(tz)
            
            events_result = await asyncio.to_thread(
                self.service.events().list(
                    calendarId=calendar_id,
                    timeMin=now.isoformat(),
                    maxResults=10,
                    singleEvents=True,
                    orderBy='startTime',
                    q=phone_number  # Buscar en descripción
                ).execute
            )
            
            events = events_result.get('items', [])
            
            appointments = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                appointments.append({
                    'id': event['id'],
                    'title': event.get('summary', 'Sin título'),
                    'start': start,
                    'description': event.get('description', '')
                })
            
            return appointments
            
        except Exception as e:
            logger.error(f"Error buscando citas: {e}")
            return []


# Instancia global
calendar_service = CalendarService()
