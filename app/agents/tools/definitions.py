"""
Definición de herramientas (Tools) para el agente.
Soporta múltiples tipos de negocio: salon, clinic, store, restaurant
"""

from google.genai import types
from datetime import datetime, timedelta
import logging
import pytz

from app.models.tables import Client, Customer
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


# ==========================================
# DEFINICIÓN DE TOOLS PARA GEMINI
# ==========================================

TOOL_DEFINITIONS = [
    types.Tool(
        function_declarations=[
            # ----- HERRAMIENTAS DE INFORMACIÓN -----
            types.FunctionDeclaration(
                name="ver_servicios",
                description="""Muestra servicios o productos disponibles según el tipo de negocio.
                - Negocios con SERVICIOS Y CITAS (detailing, taller, spa, centro de servicios, etc.): muestra lista de servicios con precios y duración
                - TIENDA/CATÁLOGO (dealer, tienda): muestra catálogo de productos/modelos con precios
                - Restaurante: menú si está configurado
                Usa cuando pregunten: qué servicios hay, precios, catálogo, modelos disponibles, cuánto cuesta, etc.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "categoria": types.Schema(
                            type=types.Type.STRING,
                            description="Categoría específica a mostrar (opcional). Ej: Colchones, Almohadas, Cortes"
                        ),
                    },
                )
            ),
            types.FunctionDeclaration(
                name="ver_profesionales",
                description="""Muestra los profesionales/doctores disponibles con sus especialidades y horarios.
                Usa cuando el usuario pregunte: qué doctores hay, quién atiende, especialistas disponibles.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "especialidad": types.Schema(
                            type=types.Type.STRING,
                            description="Filtrar por especialidad (opcional). Ej: Pediatría, Cardiología"
                        ),
                    },
                )
            ),
            
            # ----- HERRAMIENTAS DE AGENDA -----
            types.FunctionDeclaration(
                name="buscar_disponibilidad",
                description="""Busca horarios disponibles para agendar cita/entrega/reservación.
                Usa cuando el usuario quiera saber qué horarios hay disponibles.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "fecha": types.Schema(
                            type=types.Type.STRING,
                            description="Fecha en formato YYYY-MM-DD (ej: 2026-01-24)"
                        ),
                        "profesional_id": types.Schema(
                            type=types.Type.STRING,
                            description="ID del profesional/doctor (solo para clínicas con múltiples profesionales)"
                        ),
                        "servicio": types.Schema(
                            type=types.Type.STRING,
                            description="Nombre del servicio para calcular duración"
                        ),
                    },
                    required=["fecha"]
                )
            ),
            types.FunctionDeclaration(
                name="crear_cita",
                description="""Crea una cita, reservación o agenda una entrega.
                Usa cuando el usuario confirme que quiere agendar y tengas todos los datos necesarios.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "fecha": types.Schema(
                            type=types.Type.STRING,
                            description="Fecha en formato YYYY-MM-DD"
                        ),
                        "hora": types.Schema(
                            type=types.Type.STRING,
                            description="Hora en formato HH:MM (24 horas)"
                        ),
                        "servicio": types.Schema(
                            type=types.Type.STRING,
                            description="Servicio, producto o motivo de la cita"
                        ),
                        "profesional_id": types.Schema(
                            type=types.Type.STRING,
                            description="ID o nombre del profesional/atendente (clínicas y negocios con servicios). Si no especifica profesional, usar null para calendario general."
                        ),
                        "direccion": types.Schema(
                            type=types.Type.STRING,
                            description="Dirección de entrega (solo tiendas con delivery)"
                        ),
                        "num_personas": types.Schema(
                            type=types.Type.INTEGER,
                            description="Número de personas/invitados (solo restaurantes)"
                        ),
                        "email": types.Schema(
                            type=types.Type.STRING,
                            description="Correo electrónico del cliente para enviar confirmación"
                        ),
                        "area": types.Schema(
                            type=types.Type.STRING,
                            description="Área preferida para la reservación (solo restaurantes: Terraza, Salón, etc.)"
                        ),
                        "ocasion": types.Schema(
                            type=types.Type.STRING,
                            description="Ocasión especial (cumpleaños, aniversario, reunión de negocios, etc.)"
                        ),
                    },
                    required=["fecha", "hora", "servicio"]
                )
            ),
            types.FunctionDeclaration(
                name="ver_mis_citas",
                description="""Muestra las citas/reservas/pedidos activas del usuario.
                USA ESTA HERRAMIENTA cuando el usuario pregunte:
                - "tengo citas?"
                - "tengo alguna cita activa?"
                - "mis citas"
                - "quiero ver mis citas"
                - "qué citas tengo"
                - "tengo alguna cita programada?"
                - "tengo reservas?"
                - "mis reservaciones"
                - Cualquier variación de preguntar por sus citas/reservas pendientes.
                NO requiere parámetros, solo ejecútala directamente.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={},
                )
            ),
            types.FunctionDeclaration(
                name="confirmar_cita",
                description="""Confirma que el usuario asistirá a su cita próxima.
                Usa cuando el usuario responda "Sí", "Si", "SÍ", "confirmo", "sí confirmo", etc. 
                a un mensaje de confirmación que acabas de enviar o que está en el historial reciente.
                Busca la cita más próxima del usuario y confirma su asistencia.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={},
                )
            ),
            types.FunctionDeclaration(
                name="cancelar_cita",
                description="""Cancela una cita, reservación o pedido existente.
                Puedes usar evento_id, o buscar por fecha/profesional si el usuario describe la cita.
                SIEMPRE necesitas el email del cliente para enviar confirmación.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "evento_id": types.Schema(
                            type=types.Type.STRING,
                            description="ID del evento (opcional si se proporciona fecha)"
                        ),
                        "fecha": types.Schema(
                            type=types.Type.STRING,
                            description="Fecha de la cita a cancelar en formato YYYY-MM-DD (opcional)"
                        ),
                        "hora": types.Schema(
                            type=types.Type.STRING,
                            description="Hora de la cita a cancelar en formato HH:MM (opcional)"
                        ),
                        "profesional_id": types.Schema(
                            type=types.Type.STRING,
                            description="ID o nombre del profesional (solo clínicas, opcional)"
                        ),
                        "email": types.Schema(
                            type=types.Type.STRING,
                            description="Correo electrónico del cliente para enviar confirmación de cancelación (OBLIGATORIO)"
                        ),
                    },
                    required=["email"]
                )
            ),
            types.FunctionDeclaration(
                name="modificar_cita",
                description="""Modifica o reagenda una cita existente a una nueva fecha/hora.
                Busca la cita por fecha/profesional y la actualiza.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "fecha_antigua": types.Schema(
                            type=types.Type.STRING,
                            description="Fecha actual de la cita en formato YYYY-MM-DD"
                        ),
                        "hora_antigua": types.Schema(
                            type=types.Type.STRING,
                            description="Hora actual de la cita en formato HH:MM"
                        ),
                        "fecha_nueva": types.Schema(
                            type=types.Type.STRING,
                            description="Nueva fecha en formato YYYY-MM-DD"
                        ),
                        "hora_nueva": types.Schema(
                            type=types.Type.STRING,
                            description="Nueva hora en formato HH:MM"
                        ),
                        "profesional_id": types.Schema(
                            type=types.Type.STRING,
                            description="ID o nombre del profesional (solo clínicas, opcional)"
                        ),
                        "email": types.Schema(
                            type=types.Type.STRING,
                            description="Correo electrónico para enviar confirmación de modificación"
                        ),
                    },
                    required=["fecha_antigua", "hora_antigua", "fecha_nueva", "hora_nueva"]
                )
            ),
            
            # ----- HERRAMIENTAS DE DATOS -----
            types.FunctionDeclaration(
                name="guardar_datos_usuario",
                description="""Guarda información del usuario: nombre, dirección, teléfono, preferencias, etc.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "campo": types.Schema(
                            type=types.Type.STRING,
                            description="Campo a guardar (ej: direccion, telefono, preferencias)"
                        ),
                        "valor": types.Schema(
                            type=types.Type.STRING,
                            description="Valor a guardar"
                        ),
                    },
                    required=["campo", "valor"]
                )
            ),
            
            # ----- HERRAMIENTAS DE ESCALADO -----
            types.FunctionDeclaration(
                name="escalar_a_humano",
                description="""Transfiere a un agente humano. Usa INMEDIATAMENTE cuando:
                - Emergencia o urgencia
                - Usuario muy molesto
                - Pide hablar con persona
                - Preguntas que no puedes responder
                - Quejas serias
                - Pedidos especiales fuera de lo normal""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "motivo": types.Schema(type=types.Type.STRING, description="Motivo del escalado"),
                        "urgencia": types.Schema(type=types.Type.STRING, description="alta, media, baja"),
                        "resumen": types.Schema(type=types.Type.STRING, description="Resumen de la conversación"),
                    },
                    required=["motivo", "urgencia", "resumen"]
                )
            ),
        ]
    )
]


# ==========================================
# EJECUTOR DE TOOLS
# ==========================================

class ToolExecutor:
    """Ejecuta las herramientas según el tipo de negocio."""
    
    def __init__(self, client: Client, customer: Customer):
        self.client = client
        self.customer = customer
        self.config = client.tools_config or {}
        self.business_type = self.config.get('business_type', 'general')
        self.calendar_id = self.config.get('calendar_id')
        self.escalated = False
        self.escalation_data = None
    
    async def execute(self, function_name: str, args: dict) -> str:
        """Ejecuta una función por nombre."""
        logger.info(f"Ejecutando: {function_name} | Tipo: {self.business_type}")
        
        handlers = {
            "ver_servicios": self._ver_servicios,
            "ver_profesionales": self._ver_profesionales,
            "buscar_disponibilidad": self._buscar_disponibilidad,
            "crear_cita": self._crear_cita,
            "ver_mis_citas": self._ver_mis_citas,
            "confirmar_cita": self._confirmar_cita,
            "cancelar_cita": self._cancelar_cita,
            "modificar_cita": self._modificar_cita,
            "guardar_datos_usuario": self._guardar_datos,
            "escalar_a_humano": self._escalar_a_humano,
        }
        
        handler = handlers.get(function_name)
        if handler:
            return await handler(args)
        return f"Herramienta '{function_name}' no reconocida"
    
    # ==========================================
    # VER SERVICIOS / CATÁLOGO
    # ==========================================
    async def _ver_servicios(self, args: dict) -> str:
        """Muestra servicios/productos según tipo de negocio."""
        categoria = args.get("categoria", "").lower()
        currency = self.config.get("currency", "$")
        
        # CASO: Negocio con servicios (detailing, taller, spa, centro de servicios, etc.)
        # Solo usar este bloque si hay servicios definidos; si services es [] (ej. tienda con productos),
        # dejar que se use el catálogo más abajo.
        if "services" in self.config and self.config["services"]:
            services = self.config["services"]
            if categoria:
                services = [s for s in services if categoria in s["name"].lower()]
            
            if not services:
                return "No encontré servicios con ese nombre."
            
            texto = "📋 *Servicios disponibles:*\n\n"
            for s in services:
                mins = s.get('duration') or s.get('duration_minutes')
                duracion = f"{mins} min" if mins is not None else ""
                texto += f"• *{s['name']}*\n  💰 {currency}{s['price']:,} | ⏱️ {duracion}\n\n"
            return texto
        
        # CASO: Tienda con catálogo (productos; puede tener services: [] en el JSON)
        if "catalog" in self.config:
            catalog = self.config["catalog"]
            categories = catalog.get("categories", [])
            
            if categoria:
                categories = [c for c in categories if categoria in c["name"].lower()]
            
            if not categories:
                todas = catalog.get("categories", [])
                if not todas:
                    logger.warning(
                        "ver_servicios: cliente %s tiene 'catalog' pero categories está vacío. "
                        "Configura catalog.categories con productos en el panel de administración.",
                        self.client.id,
                    )
                    return "Aún no tenemos el catálogo de productos cargado. ¿Te gustaría que te cuente horarios de atención o que un asesor te contacte?"
                return "No encontré esa categoría. Categorías disponibles: " + ", ".join([c["name"] for c in todas])
            
            texto = "🛒 *Catálogo de productos:*\n\n"
            for cat in categories:
                texto += f"*{cat['name']}*\n"
                for p in cat.get("products", []):
                    texto += f"  • {p['name']}: {currency}{p['price']:,}\n"
                    if p.get("description"):
                        texto += f"    _{p['description']}_\n"
                texto += "\n"
            
            # Info de envío
            if self.config.get("free_delivery_minimum"):
                texto += f"\n🚚 Envío gratis en compras mayores a {currency}{self.config['free_delivery_minimum']:,}"
            
            return texto
        
        # CASO: Restaurante
        if "menu_url" in self.config:
            return f"📋 Puedes ver nuestro menú completo aquí: {self.config['menu_url']}"
        
        logger.warning(
            "ver_servicios: cliente %s (%s) no tiene catalog, services ni menu_url en tools_config. "
            "Keys presentes: %s. Configura el catálogo/servicios en el panel de administración.",
            self.client.id,
            getattr(self.client, "business_name", "?"),
            list(self.config.keys()),
        )
        return "Aún no tenemos el catálogo de productos cargado. ¿Te gustaría que te cuente horarios de atención o que un asesor te contacte?"
    
    # ==========================================
    # VER PROFESIONALES (CLÍNICAS)
    # ==========================================
    async def _ver_profesionales(self, args: dict) -> str:
        """Muestra profesionales disponibles (clínicas)."""
        especialidad = args.get("especialidad", "").lower()
        professionals = self.config.get("professionals", [])
        
        if not professionals:
            return "Este negocio no tiene profesionales configurados."
        
        if especialidad:
            professionals = [p for p in professionals if especialidad in p.get("specialty", "").lower()]
        
        if not professionals:
            return "No encontré profesionales con esa especialidad."
        
        dias_semana = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}
        currency = self.config.get("currency", "$")
        
        texto = "👨‍⚕️ *Profesionales disponibles:*\n\n"
        for p in professionals:
            dias = ", ".join([dias_semana.get(d, str(d)) for d in p.get("working_days", [])])
            hours = p.get("business_hours", {})
            horario = f"{hours.get('start', '08:00')} - {hours.get('end', '17:00')}"
            precio = p.get("consultation_price", 0)
            
            texto += f"*{p['name']}*\n"
            texto += f"  📋 {p.get('specialty', 'General')}\n"
            texto += f"  📅 {dias}\n"
            texto += f"  🕐 {horario}\n"
            texto += f"  💰 {currency}{precio:,}\n"
            texto += f"  _ID: {p['id']}_\n\n"
        
        texto += "Para agendar, dime con qué profesional y qué fecha te gustaría."
        return texto
    
    # ==========================================
    # BUSCAR DISPONIBILIDAD
    # ==========================================
    async def _buscar_disponibilidad(self, args: dict) -> str:
        """Busca horarios disponibles."""
        try:
            fecha_str = args.get("fecha")
            profesional_id = args.get("profesional_id")
            servicio = args.get("servicio")
            
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
            tz = pytz.timezone(self.config.get('timezone', 'America/Santo_Domingo'))
            hoy = datetime.now(tz).date()
            
            if fecha.date() < hoy:
                return "No puedo buscar disponibilidad en fechas pasadas."
            
            # Determinar calendario y duración según tipo de negocio
            calendar_id = self.calendar_id
            duration = self.config.get("slot_duration", 30)
            working_hours = self.config.get("business_hours", {"start": "08:00", "end": "18:00"})
            working_days = self.config.get("working_days", [1,2,3,4,5])
            
            # CASO: Clínica con profesionales
            if profesional_id and self.config.get("professionals"):
                # Buscar por ID exacto primero
                prof = next((p for p in self.config["professionals"] if p["id"] == profesional_id), None)
                # Si no lo encuentra, buscar por nombre (parcial, case-insensitive)
                if not prof:
                    profesional_lower = profesional_id.lower()
                    prof = next((p for p in self.config["professionals"] 
                                if profesional_lower in p.get("name", "").lower() 
                                or profesional_lower in p.get("id", "").lower()), None)
                if not prof:
                    # Listar profesionales disponibles
                    profs_list = ", ".join([p["name"] for p in self.config["professionals"]])
                    return f"No encontré a '{profesional_id}'. Los profesionales disponibles son: {profs_list}"
                calendar_id = prof.get("calendar_id")
                duration = prof.get("slot_duration", 30)
                working_hours = prof.get("business_hours", working_hours)
                working_days = prof.get("working_days", working_days)
            
            # CASO: Salón con servicios de diferente duración
            if servicio and self.config.get("services"):
                srv = next((s for s in self.config["services"] if servicio.lower() in s["name"].lower()), None)
                if srv:
                    duration = srv.get("duration", duration)
            
            # CASO: Tienda con delivery
            if self.business_type == "store":
                duration = self.config.get("delivery_duration", 60)
                working_hours = self.config.get("delivery_hours", working_hours)
            
            # Verificar día de la semana
            dia_semana = fecha.isoweekday()
            if dia_semana not in working_days:
                dias = {1:"lunes", 2:"martes", 3:"miércoles", 4:"jueves", 5:"viernes", 6:"sábado", 7:"domingo"}
                dias_trabajo = ", ".join([dias[d] for d in working_days])
                return f"No trabajamos el {dias.get(dia_semana)}. Días disponibles: {dias_trabajo}"
            
            if not calendar_id:
                return "No hay calendario configurado para este servicio."
            
            # Import aquí para evitar circular import
            from app.services.calendar import calendar_service
            
            # Obtener slots
            config_for_calendar = {
                **self.config,
                "business_hours": working_hours,
                "slot_duration": duration
            }
            
            slots = await calendar_service.get_available_slots(
                calendar_id=calendar_id,
                date=fecha,
                duration_minutes=duration,
                config=config_for_calendar
            )
            
            if not slots:
                return f"No hay horarios disponibles para el {fecha.strftime('%d de %B de %Y')}. ¿Probamos otra fecha?"
            
            slots_text = "\n".join([f"• {s['start']} - {s['end']}" for s in slots[:10]])
            return f"📅 Horarios disponibles para el {fecha.strftime('%d de %B de %Y')}:\n\n{slots_text}\n\n¿Cuál prefieres?"
            
        except ValueError:
            return "Formato de fecha inválido. Usa YYYY-MM-DD (ej: 2026-01-24)"
        except Exception as e:
            logger.error(f"Error buscando disponibilidad: {e}", exc_info=True)
            return "Hubo un error buscando disponibilidad. Intenta de nuevo."
    
    # ==========================================
    # CREAR CITA / RESERVACIÓN / ENTREGA
    # ==========================================
    async def _crear_cita(self, args: dict) -> str:
        """Crea una cita según tipo de negocio.
        
        Para CLÍNICAS: profesional_id es OBLIGATORIO si hay múltiples profesionales
        Para SALONES: profesional_id es OPCIONAL (puede ser None para usar calendario general)
        Para TIENDAS: crea entrega/ruta (direccion es requerida)
        Para RESTAURANTES: crea reservación (num_personas es requerida)
        """
        try:
            fecha_str = args.get("fecha")
            hora_str = args.get("hora")
            servicio = args.get("servicio")
            profesional_id = args.get("profesional_id")
            direccion = args.get("direccion")
            num_personas = args.get("num_personas")
            email = args.get("email")
            area = args.get("area")
            ocasion = args.get("ocasion")
            
            # VALIDACIÓN: Para clínicas con múltiples profesionales, profesional_id es obligatorio
            if self.business_type == "clinic" and self.config.get("professionals") and len(self.config["professionals"]) > 1:
                if not profesional_id:
                    profs_list = ", ".join([p["name"] for p in self.config["professionals"]])
                    return f"Para agendar tu cita médica, necesito saber con qué profesional te gustaría agendar. Los profesionales disponibles son: {profs_list}. ¿Con cuál te gustaría?"
            
            tz = pytz.timezone(self.config.get('timezone', 'America/Santo_Domingo'))
            fecha = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
            fecha = tz.localize(fecha)
            
            if fecha < datetime.now(tz):
                return "Esa hora ya pasó. ¿Me puedes dar otro horario?"
            
            # ==========================================
            # VALIDAR HORARIO DE TRABAJO
            # ==========================================
            working_hours = self.config.get("business_hours", {"start": "08:00", "end": "18:00"})
            working_days = self.config.get("working_days", [1, 2, 3, 4, 5])
            # Tienda con delivery: validar y usar horario de entregas
            if self.business_type == "store":
                working_hours = self.config.get("delivery_hours", working_hours)
            
            # Validar día de la semana
            dia_semana = fecha.isoweekday()
            if dia_semana not in working_days:
                dias_nombres = {1: "lunes", 2: "martes", 3: "miércoles", 4: "jueves", 5: "viernes", 6: "sábado", 7: "domingo"}
                dias_trabajo = ", ".join([dias_nombres[d] for d in working_days])
                return f"Ese día no trabajamos. Nuestros días de atención son: {dias_trabajo}. ¿Qué otro día te funciona?"
            
            # Validar hora dentro del horario
            start_hour, start_min = map(int, working_hours['start'].split(':'))
            end_hour, end_min = map(int, working_hours['end'].split(':'))
            
            hora_cita = fecha.hour * 60 + fecha.minute  # Convertir a minutos
            hora_inicio = start_hour * 60 + start_min
            hora_fin = end_hour * 60 + end_min
            
            if hora_cita < hora_inicio or hora_cita >= hora_fin:
                return f"Esa hora está fuera de nuestro horario de atención ({working_hours['start']} - {working_hours['end']}). ¿Te funciona algún horario dentro de ese rango?"
            
            # Determinar calendario y duración
            calendar_id = self.calendar_id
            duration = self.config.get("slot_duration", 30)
            titulo_prefix = ""
            descripcion_extra = ""
            currency = self.config.get("currency", "$")
            profesional_nombre = None
            precio_servicio = None
            
            # CASO: Profesional específico (Clínica o Salón)
            if profesional_id and self.config.get("professionals"):
                # Buscar por ID exacto primero
                prof = next((p for p in self.config["professionals"] if p["id"] == profesional_id), None)
                # Si no lo encuentra, buscar por nombre (parcial, case-insensitive)
                if not prof:
                    profesional_lower = profesional_id.lower()
                    prof = next((p for p in self.config["professionals"] 
                                if profesional_lower in p.get("name", "").lower() 
                                or profesional_lower in p.get("id", "").lower()), None)
                if prof:
                    # Si el profesional tiene su propio calendario, usarlo
                    if prof.get("calendar_id"):
                        calendar_id = prof.get("calendar_id")
                    # Si no tiene calendario propio, usar el general pero marcar el profesional
                    titulo_prefix = f"{prof['name']} - "
                    profesional_nombre = prof['name']
                    descripcion_extra = f"\nProfesional: {prof['name']}"
                    if prof.get("slot_duration"):
                        duration = prof.get("slot_duration", duration)
                else:
                    profs_list = ", ".join([p["name"] for p in self.config["professionals"]])
                    return f"No encontré a '{profesional_id}'. Los profesionales disponibles son: {profs_list}"
            
            # CASO: Salón con servicio
            if self.config.get("services"):
                srv = next((s for s in self.config["services"] if servicio.lower() in s["name"].lower()), None)
                if srv:
                    duration = srv.get("duration", duration)
                    servicio = srv["name"]
                    precio_servicio = f"{currency}{srv['price']:,}"
                    descripcion_extra += f"\nPrecio: {precio_servicio}"
            
            # CASO: Tienda con delivery
            if self.business_type == "store":
                duration = self.config.get("delivery_duration", 60)
                if direccion:
                    descripcion_extra += f"\n📍 Dirección: {direccion}"
                    # Guardar dirección del cliente
                    from app.services.client_service import client_service
                    await client_service.update_customer_data(self.customer.id, {"direccion": direccion})
            
            # CASO: Restaurante
            if num_personas:
                descripcion_extra += f"\n👥 Personas: {num_personas}"
            if area:
                descripcion_extra += f"\n🪑 Área: {area}"
            if ocasion:
                descripcion_extra += f"\n🎉 Ocasión: {ocasion}"
            
            # Guardar email del cliente si lo proporciona
            if email:
                from app.services.client_service import client_service
                await client_service.update_customer_data(self.customer.id, {"email": email})
            
            # ==========================================
            # VERIFICAR DISPONIBILIDAD DEL SLOT ESPECÍFICO
            # (Después de determinar calendario y working_hours del profesional)
            # ==========================================
            from app.services.calendar import calendar_service
            
            # Actualizar working_hours si es un profesional con horario específico
            if profesional_id and self.config.get("professionals"):
                prof = next((p for p in self.config["professionals"] 
                            if profesional_id.lower() in p.get("name", "").lower() 
                            or profesional_id.lower() in p.get("id", "").lower()), None)
                if prof and prof.get("business_hours"):
                    working_hours = prof.get("business_hours", working_hours)
            
            # Obtener configuración para el calendario específico
            config_for_calendar = {
                **self.config,
                "business_hours": working_hours,
                "slot_duration": duration
            }
            
            # Obtener slots disponibles para esa fecha
            fecha_date = fecha.date()
            slots_disponibles = await calendar_service.get_available_slots(
                calendar_id=calendar_id,
                date=fecha_date,
                duration_minutes=duration,
                config=config_for_calendar
            )
            
            # Verificar si el horario solicitado está en los slots disponibles
            hora_solicitada = fecha.strftime('%H:%M')
            slot_disponible = False
            
            for slot in slots_disponibles:
                slot_start = slot.get('start', '')
                # Verificar si el horario solicitado coincide con el inicio de algún slot
                if slot_start == hora_solicitada:
                    slot_disponible = True
                    break
            
            if not slot_disponible:
                # Formatear slots disponibles para mostrar al usuario
                slots_text = "\n".join([f"• {s['start']} - {s['end']}" for s in slots_disponibles[:10]])
                if slots_disponibles:
                    return f"❌ Lo siento, el horario {hora_solicitada} no está disponible para el {fecha.strftime('%d de %B de %Y')}.\n\n📅 Horarios disponibles:\n{slots_text}\n\n¿Cuál prefieres?"
                else:
                    return f"❌ Lo siento, no hay horarios disponibles para el {fecha.strftime('%d de %B de %Y')}. ¿Te funciona otra fecha?"
            
            fin = fecha + timedelta(minutes=duration)
            nombre = self.customer.full_name or "Cliente"
            titulo = f"{titulo_prefix}{servicio} - {nombre}"
            
            # Crear en Google Calendar
            evento = await calendar_service.create_appointment(
                calendar_id=calendar_id,
                title=titulo,
                start_time=fecha,
                end_time=fin,
                description=f"Agendado via WhatsApp\nServicio: {servicio}{descripcion_extra}\nTeléfono: {self.customer.phone_number}" + (f"\nEmail: {email}" if email else ""),
                attendee_phone=self.customer.phone_number,
                config=self.config
            )
            
            if evento:
                # Guardar en BD
                from app.models.tables import Appointment
                async with AsyncSessionLocal() as session:
                    appointment = Appointment(
                        client_id=self.client.id,
                        customer_id=self.customer.id,
                        google_event_id=evento.get('id'),
                        start_time=fecha,
                        end_time=fin,
                        status="CONFIRMED",
                        notes=f"{servicio}{descripcion_extra}"
                    )
                    session.add(appointment)
                    await session.commit()
                
                # ==========================================
                # ENVIAR EMAIL DE CONFIRMACIÓN
                # ==========================================
                email_enviado = False
                if email:
                    try:
                        from app.services.email_service import email_service
                        
                        appointment_details = {
                            "servicio": servicio,
                            "profesional": profesional_nombre,
                            "precio": precio_servicio,
                            "direccion": direccion,
                            "num_personas": num_personas,
                            "area": area,
                            "ocasion": ocasion
                        }
                        
                        email_enviado = await email_service.send_confirmation_email(
                            to_email=email,
                            business_name=self.client.business_name,
                            business_type=self.business_type,
                            customer_name=nombre,
                            appointment_date=fecha,
                            appointment_details=appointment_details
                        )
                    except Exception as e:
                        logger.error(f"Error enviando email de confirmación: {e}")
                
                # ==========================================
                # MENSAJE DE CONFIRMACIÓN SEGÚN TIPO
                # ==========================================
                email_msg = "\n\n📧 Te enviamos confirmación a tu correo." if email_enviado else ""
                
                if self.business_type == "store":
                    return f"✅ *Entrega agendada*\n\n📅 {fecha.strftime('%d de %B de %Y')}\n🕐 {hora_str}\n📦 {servicio}\n📍 {direccion or 'Pendiente'}{email_msg}\n\n¡Te esperamos!"
                elif self.business_type == "restaurant":
                    area_msg = f"\n🪑 Área: {area}" if area else ""
                    ocasion_msg = f"\n🎉 Ocasión: {ocasion}" if ocasion else ""
                    return f"🍽️ *¡Reservación confirmada!*\n\n📅 {fecha.strftime('%d de %B de %Y')}\n🕐 {hora_str}\n👥 {num_personas or 2} personas{area_msg}{ocasion_msg}{email_msg}\n\n¡Será un placer atenderles! 🥂"
                elif self.business_type == "clinic":
                    prof_msg = f"\n👨‍⚕️ {profesional_nombre}" if profesional_nombre else ""
                    return f"🏥 *Cita médica confirmada*\n\n📅 {fecha.strftime('%d de %B de %Y')}\n🕐 {hora_str}\n📋 {servicio}{prof_msg}{email_msg}\n\n¡Le esperamos!"
                else:
                    return f"✅ *Cita confirmada*\n\n📅 {fecha.strftime('%d de %B de %Y')}\n🕐 {hora_str}\n📋 {servicio}{email_msg}\n\n¡Te esperamos! 💖"
            
            return "No pude crear la cita. Intenta de nuevo."
            
        except Exception as e:
            logger.error(f"Error creando cita: {e}", exc_info=True)
            return "Hubo un error al agendar. Intenta de nuevo."
    
    # ==========================================
    # VER MIS CITAS
    # ==========================================
    async def _ver_mis_citas(self, args: dict) -> str:
        """Lista citas del usuario."""
        try:
            from app.models.tables import Appointment
            from sqlalchemy import select, and_
            
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Appointment).where(
                        and_(
                            Appointment.customer_id == self.customer.id,
                            Appointment.status == "CONFIRMED",
                            Appointment.start_time >= datetime.now(pytz.UTC)
                        )
                    ).order_by(Appointment.start_time)
                )
                citas = result.scalars().all()
            
            if not citas:
                return "No tienes citas programadas. ¿Te gustaría agendar una?"
            
            tz = pytz.timezone(self.config.get('timezone', 'America/Santo_Domingo'))
            
            if self.business_type == "store":
                texto = "📦 *Tus entregas programadas:*\n\n"
            elif self.business_type == "restaurant":
                texto = "🍽️ *Tus reservaciones:*\n\n"
            else:
                texto = "📋 *Tus citas programadas:*\n\n"
            
            for cita in citas:
                fecha_local = cita.start_time.astimezone(tz)
                texto += f"• {cita.notes or 'Cita'}\n"
                texto += f"  📅 {fecha_local.strftime('%d/%m/%Y')} a las {fecha_local.strftime('%H:%M')}\n"
                if cita.google_event_id:
                    texto += f"  ID: `{cita.google_event_id}`\n\n"
                else:
                    texto += "\n"
            
            return texto
            
        except Exception as e:
            logger.error(f"Error listando citas: {e}", exc_info=True)
            return "Hubo un error obteniendo tus citas. Por favor intenta de nuevo."
    
    # ==========================================
    # CONFIRMAR CITA
    # ==========================================
    async def _confirmar_cita(self, args: dict) -> str:
        """Confirma la asistencia a la cita más próxima del usuario."""
        try:
            from app.models.tables import Appointment
            from sqlalchemy import select, and_
            
            async with AsyncSessionLocal() as session:
                # Buscar la cita más próxima del usuario
                result = await session.execute(
                    select(Appointment).where(
                        and_(
                            Appointment.customer_id == self.customer.id,
                            Appointment.status == "CONFIRMED",
                            Appointment.start_time >= datetime.now(pytz.UTC)
                        )
                    ).order_by(Appointment.start_time).limit(1)
                )
                appointment = result.scalar_one_or_none()
            
            if not appointment:
                return "No encontré ninguna cita próxima para confirmar. ¿Te gustaría agendar una nueva cita?"
            
            tz = pytz.timezone(self.config.get('timezone', 'America/Santo_Domingo'))
            fecha_local = appointment.start_time.astimezone(tz)
            
            # La cita ya está confirmada, solo informamos
            return (
                f"✅ *¡Perfecto! Tu asistencia está confirmada.*\n\n"
                f"📅 Fecha: {fecha_local.strftime('%d de %B de %Y')}\n"
                f"🕐 Hora: {fecha_local.strftime('%H:%M')}\n"
                f"🏥 {self.client.business_name}\n\n"
                f"Te esperamos. Si necesitas cancelar o modificar, avísame con anticipación."
            )
            
        except Exception as e:
            logger.error(f"Error confirmando cita: {e}", exc_info=True)
            return "Hubo un error al confirmar tu cita. Por favor intenta de nuevo."
    
    # ==========================================
    # CANCELAR CITA
    # ==========================================
    async def _cancelar_cita(self, args: dict) -> str:
        """Cancela una cita, buscando por ID o por fecha/profesional."""
        try:
            from app.services.calendar import calendar_service
            from app.models.tables import Appointment
            from sqlalchemy import select, and_
            
            evento_id = args.get("evento_id")
            fecha_str = args.get("fecha")
            hora_str = args.get("hora")
            profesional_id = args.get("profesional_id")
            email = args.get("email")
            
            # Guardar email del cliente si se proporciona
            if email:
                from app.services.client_service import client_service
                await client_service.update_customer_data(self.customer.id, {"email": email})
            
            appointment = None
            tz = pytz.timezone(self.config.get('timezone', 'America/Santo_Domingo'))
            
            async with AsyncSessionLocal() as session:
                # Si hay evento_id, buscar directamente
                if evento_id:
                    result = await session.execute(
                        select(Appointment).where(
                            and_(
                                Appointment.google_event_id == evento_id,
                                Appointment.customer_id == self.customer.id,
                                Appointment.status == "CONFIRMED"
                            )
                        )
                    )
                    appointment = result.scalar_one_or_none()
                
                # Si no hay evento_id pero hay fecha/hora, buscar por fecha
                elif fecha_str and hora_str:
                    fecha_buscar = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
                    fecha_buscar = tz.localize(fecha_buscar)
                    
                    # Buscar cita en un rango de ±30 minutos
                    fecha_inicio = fecha_buscar - timedelta(minutes=30)
                    fecha_fin = fecha_buscar + timedelta(minutes=30)
                    
                    query = select(Appointment).where(
                        and_(
                            Appointment.customer_id == self.customer.id,
                            Appointment.client_id == self.client.id,
                            Appointment.status == "CONFIRMED",
                            Appointment.start_time >= fecha_inicio,
                            Appointment.start_time <= fecha_fin
                        )
                    )
                    
                    # Si hay profesional_id, filtrar por profesional en notes
                    if profesional_id and self.config.get("professionals"):
                        prof = next((p for p in self.config["professionals"] 
                                    if profesional_id.lower() in p.get("name", "").lower() 
                                    or profesional_id.lower() in p.get("id", "").lower()), None)
                        if prof:
                            query = query.where(Appointment.notes.contains(prof['name']))
                    
                    result = await session.execute(query)
                    appointment = result.scalar_one_or_none()
                
                # Si no se encontró, buscar la próxima cita del cliente
                if not appointment:
                    result = await session.execute(
                        select(Appointment).where(
                            and_(
                                Appointment.customer_id == self.customer.id,
                                Appointment.client_id == self.client.id,
                                Appointment.status == "CONFIRMED",
                                Appointment.start_time >= datetime.now(pytz.UTC)
                            )
                        ).order_by(Appointment.start_time).limit(1)
                    )
                    appointment = result.scalar_one_or_none()
                
                if not appointment:
                    return "No encontré la cita que quieres cancelar. ¿Puedes darme más detalles?"
                
                # Cancelar en Google Calendar
                calendar_id = self.calendar_id
                if self.config.get("professionals") and appointment.notes:
                    # Buscar calendario del profesional
                    for prof in self.config["professionals"]:
                        if prof.get("name") in appointment.notes:
                            calendar_id = prof.get("calendar_id", calendar_id)
                            break
                
                success = await calendar_service.cancel_appointment(
                    calendar_id=calendar_id,
                    event_id=appointment.google_event_id
                )
                
                if success:
                    appointment.status = "CANCELLED"
                    await session.commit()
                    
                    # Usar email proporcionado o el guardado
                    customer_email = email or (self.customer.data.get("email") if self.customer.data else None)
                    email_enviado = False
                    
                    if customer_email:
                        try:
                            from app.services.email_service import email_service
                            email_enviado = await email_service.send_confirmation_email(
                                to_email=customer_email,
                                business_name=self.client.business_name,
                                business_type=self.business_type,
                                customer_name=self.customer.full_name or "Cliente",
                                appointment_date=appointment.start_time,
                                appointment_details={"cancelado": True}
                            )
                            logger.info(f"Email de cancelación {'enviado' if email_enviado else 'falló'} a {customer_email}")
                        except Exception as e:
                            logger.error(f"Error enviando email de cancelación: {e}", exc_info=True)
                    else:
                        logger.warning("No hay email para enviar confirmación de cancelación")
                    
                    fecha_local = appointment.start_time.astimezone(tz)
                    email_msg = f"\n\n📧 Te enviamos confirmación de cancelación a {customer_email}" if email_enviado else ""
                    return f"✅ *Cita cancelada*\n\n📅 {fecha_local.strftime('%d de %B de %Y')}\n🕐 {fecha_local.strftime('%H:%M')}{email_msg}\n\n¿Deseas agendar otra cita?"
                
                return "No pude cancelar la cita en el calendario. Intenta de nuevo."
            
        except Exception as e:
            logger.error(f"Error cancelando: {e}", exc_info=True)
            return "Hubo un error al cancelar. Intenta de nuevo."
    
    # ==========================================
    # MODIFICAR/REAGENDAR CITA
    # ==========================================
    async def _modificar_cita(self, args: dict) -> str:
        """Modifica una cita existente a nueva fecha/hora."""
        try:
            from app.services.calendar import calendar_service
            from app.models.tables import Appointment
            from sqlalchemy import select, and_
            
            fecha_antigua_str = args.get("fecha_antigua")
            hora_antigua_str = args.get("hora_antigua")
            fecha_nueva_str = args.get("fecha_nueva")
            hora_nueva_str = args.get("hora_nueva")
            profesional_id = args.get("profesional_id")
            email = args.get("email")
            
            tz = pytz.timezone(self.config.get('timezone', 'America/Santo_Domingo'))
            
            # Parsear fechas
            fecha_antigua = datetime.strptime(f"{fecha_antigua_str} {hora_antigua_str}", "%Y-%m-%d %H:%M")
            fecha_antigua = tz.localize(fecha_antigua)
            
            fecha_nueva = datetime.strptime(f"{fecha_nueva_str} {hora_nueva_str}", "%Y-%m-%d %H:%M")
            fecha_nueva = tz.localize(fecha_nueva)
            
            # Validar nueva fecha
            if fecha_nueva < datetime.now(tz):
                return "La nueva fecha ya pasó. ¿Me puedes dar otra fecha?"
            
            # Validar horario de trabajo
            working_hours = self.config.get("business_hours", {"start": "08:00", "end": "18:00"})
            working_days = self.config.get("working_days", [1, 2, 3, 4, 5])
            
            dia_semana = fecha_nueva.isoweekday()
            if dia_semana not in working_days:
                dias_nombres = {1: "lunes", 2: "martes", 3: "miércoles", 4: "jueves", 5: "viernes", 6: "sábado", 7: "domingo"}
                dias_trabajo = ", ".join([dias_nombres[d] for d in working_days])
                return f"Ese día no trabajamos. Días disponibles: {dias_trabajo}"
            
            start_hour, start_min = map(int, working_hours['start'].split(':'))
            end_hour, end_min = map(int, working_hours['end'].split(':'))
            hora_cita = fecha_nueva.hour * 60 + fecha_nueva.minute
            hora_inicio = start_hour * 60 + start_min
            hora_fin = end_hour * 60 + end_min
            
            if hora_cita < hora_inicio or hora_cita >= hora_fin:
                return f"Esa hora está fuera del horario ({working_hours['start']} - {working_hours['end']})"
            
            # Buscar cita antigua
            async with AsyncSessionLocal() as session:
                fecha_inicio = fecha_antigua - timedelta(minutes=30)
                fecha_fin = fecha_antigua + timedelta(minutes=30)
                
                query = select(Appointment).where(
                    and_(
                        Appointment.customer_id == self.customer.id,
                        Appointment.client_id == self.client.id,
                        Appointment.status == "CONFIRMED",
                        Appointment.start_time >= fecha_inicio,
                        Appointment.start_time <= fecha_fin
                    )
                )
                
                if profesional_id and self.config.get("professionals"):
                    prof = next((p for p in self.config["professionals"] 
                                if profesional_id.lower() in p.get("name", "").lower()), None)
                    if prof:
                        query = query.where(Appointment.notes.contains(prof['name']))
                
                result = await session.execute(query)
                appointment = result.scalar_one_or_none()
                
                if not appointment:
                    return "No encontré la cita que quieres modificar. ¿Puedes darme más detalles?"
                
                # Calcular nueva duración
                duration = (appointment.end_time - appointment.start_time).total_seconds() / 60
                fecha_nueva_fin = fecha_nueva + timedelta(minutes=duration)
                
                # Determinar calendario
                calendar_id = self.calendar_id
                if self.config.get("professionals") and appointment.notes:
                    for prof in self.config["professionals"]:
                        if prof.get("name") in appointment.notes:
                            calendar_id = prof.get("calendar_id", calendar_id)
                            break
                
                # ==========================================
                # VERIFICAR DISPONIBILIDAD DEL NUEVO SLOT
                # ==========================================
                from app.services.calendar import calendar_service
                
                # Obtener working_hours del profesional si aplica; tienda usa delivery_hours
                working_hours = self.config.get("business_hours", {"start": "08:00", "end": "18:00"})
                if self.business_type == "store":
                    working_hours = self.config.get("delivery_hours", working_hours)
                elif self.config.get("professionals") and appointment.notes:
                    for prof in self.config["professionals"]:
                        if prof.get("name") in appointment.notes:
                            working_hours = prof.get("business_hours", working_hours)
                            break
                
                config_for_calendar = {
                    **self.config,
                    "business_hours": working_hours,
                    "slot_duration": int(duration)
                }
                
                # Obtener slots disponibles para la nueva fecha
                fecha_nueva_date = fecha_nueva.date()
                slots_disponibles = await calendar_service.get_available_slots(
                    calendar_id=calendar_id,
                    date=fecha_nueva_date,
                    duration_minutes=int(duration),
                    config=config_for_calendar
                )
                
                # Verificar si el nuevo horario está disponible
                hora_solicitada = fecha_nueva.strftime('%H:%M')
                slot_disponible = False
                
                for slot in slots_disponibles:
                    slot_start = slot.get('start', '')
                    if slot_start == hora_solicitada:
                        slot_disponible = True
                        break
                
                if not slot_disponible:
                    # Formatear slots disponibles para mostrar al usuario
                    slots_text = "\n".join([f"• {s['start']} - {s['end']}" for s in slots_disponibles[:10]])
                    if slots_disponibles:
                        return f"❌ Lo siento, el horario {hora_solicitada} no está disponible para el {fecha_nueva.strftime('%d de %B de %Y')}.\n\n📅 Horarios disponibles:\n{slots_text}\n\n¿Cuál prefieres?"
                    else:
                        return f"❌ Lo siento, no hay horarios disponibles para el {fecha_nueva.strftime('%d de %B de %Y')}. ¿Te funciona otra fecha?"
                
                # Quitar la cita anterior del calendario y crear la nueva (evita duplicados)
                from googleapiclient.errors import HttpError
                try:
                    old_event_id = appointment.google_event_id
                    # 1) Borrar el evento anterior del calendario
                    deleted = await calendar_service.cancel_appointment(
                        calendar_id=calendar_id,
                        event_id=old_event_id
                    )
                    if not deleted:
                        logger.warning(f"No se pudo borrar evento antiguo {old_event_id}, puede quedar duplicado")
                    
                    # 2) Crear nuevo evento en la nueva fecha/hora
                    title = f"Cita: {self.customer.full_name or 'Cliente'}"
                    if appointment.notes:
                        notes_parts = appointment.notes.split('\n')
                        title = notes_parts[0] if notes_parts else title
                    new_event = await calendar_service.create_appointment(
                        calendar_id=calendar_id,
                        title=title,
                        start_time=fecha_nueva,
                        end_time=fecha_nueva_fin,
                        description=appointment.notes or "",
                        attendee_phone=self.customer.phone_number or "",
                        config=self.config,
                    )
                    if not new_event or not new_event.get("id"):
                        return "No pude crear la nueva cita en el calendario. Intenta de nuevo."
                    
                    # 3) Actualizar en BD con el nuevo event_id y fechas
                    appointment.google_event_id = new_event["id"]
                    appointment.start_time = fecha_nueva
                    appointment.end_time = fecha_nueva_fin
                    await session.commit()
                    
                    # Guardar email si se proporciona
                    if email:
                        from app.services.client_service import client_service
                        await client_service.update_customer_data(self.customer.id, {"email": email})
                    
                    # Extraer profesional para el mensaje de confirmación
                    profesional_nombre = None
                    for prof in self.config.get("professionals", []):
                        if prof.get("name") in (appointment.notes or ""):
                            profesional_nombre = prof.get("name")
                            break
                    
                    # Enviar email de confirmación
                    customer_email = email or (self.customer.data.get("email") if self.customer.data else None)
                    email_enviado = False
                    if customer_email:
                        try:
                            from app.services.email_service import email_service
                            
                            notes_parts = appointment.notes.split('\n') if appointment.notes else []
                            servicio = notes_parts[0] if notes_parts else "Cita"
                            appointment_details = {
                                "servicio": servicio,
                                "profesional": profesional_nombre,
                                "modificada": True
                            }
                            
                            email_enviado = await email_service.send_confirmation_email(
                                to_email=customer_email,
                                business_name=self.client.business_name,
                                business_type=self.business_type,
                                customer_name=self.customer.full_name or "Cliente",
                                appointment_date=fecha_nueva,
                                appointment_details=appointment_details
                            )
                        except Exception as e:
                            logger.error(f"Error enviando email de modificación: {e}")
                    
                    email_msg = "\n\n📧 Te enviamos confirmación a tu correo." if email_enviado else ""
                    
                    # Mensaje de confirmación
                    if self.business_type == "restaurant":
                        return f"🍽️ *¡Reservación modificada!*\n\n📅 {fecha_nueva.strftime('%d de %B de %Y')}\n🕐 {hora_nueva_str}{email_msg}\n\n¡Será un placer atenderles! 🥂"
                    elif self.business_type == "clinic":
                        prof_msg = f"\n👨‍⚕️ {profesional_nombre}" if profesional_nombre else ""
                        return f"🏥 *Cita modificada*\n\n📅 {fecha_nueva.strftime('%d de %B de %Y')}\n🕐 {hora_nueva_str}{prof_msg}{email_msg}\n\n¡Le esperamos!"
                    else:
                        return f"✅ *Cita modificada*\n\n📅 {fecha_nueva.strftime('%d de %B de %Y')}\n🕐 {hora_nueva_str}{email_msg}\n\n¡Te esperamos!"
                
                except HttpError as e:
                    logger.error(f"Error en calendario al modificar cita: {e}")
                    return "No pude modificar la cita en el calendario. Intenta de nuevo."
            
        except Exception as e:
            logger.error(f"Error modificando cita: {e}", exc_info=True)
            return "Hubo un error al modificar. Intenta de nuevo."
    
    # ==========================================
    # GUARDAR DATOS
    # ==========================================
    async def _guardar_datos(self, args: dict) -> str:
        """Guarda datos del usuario."""
        try:
            from app.services.client_service import client_service
            
            campo = args.get("campo")
            valor = args.get("valor")
            
            await client_service.update_customer_data(
                customer_id=self.customer.id,
                data={campo: valor}
            )
            return f"✅ Guardado: {campo}"
        except Exception as e:
            logger.error(f"Error guardando: {e}")
            return "No pude guardar la información."
    
    # ==========================================
    # ESCALAR A HUMANO
    # ==========================================
    async def _escalar_a_humano(self, args: dict) -> str:
        """Escala a agente humano y marca la conversación para que la IA no intervenga."""
        try:
            from app.services.client_service import client_service
            from app.core.redis import ConversationMemory
            
            motivo = args.get("motivo")
            urgencia = args.get("urgencia", "media")
            resumen = args.get("resumen", "")
            
            self.escalated = True
            self.escalation_data = {
                "motivo": motivo,
                "urgencia": urgencia,
                "resumen": resumen,
                "timestamp": datetime.now().isoformat()
            }
            
            # Marcar conversación como escalada en Redis (IA no responderá automáticamente)
            memory = ConversationMemory(self.client.id, self.customer.phone_number)
            await memory.set_escalated(escalated=True, motivo=motivo)
            
            logger.warning(
                f"🚨 ESCALADO - {urgencia.upper()}\n"
                f"   Negocio: {self.client.business_name}\n"
                f"   Cliente: {self.customer.full_name} ({self.customer.phone_number})\n"
                f"   Motivo: {motivo}\n"
                f"   IA pausada para esta conversación"
            )
            
            await client_service.update_customer_data(
                customer_id=self.customer.id,
                data={"ultimo_escalado": datetime.now().isoformat(), "motivo_escalado": motivo}
            )
            
            emoji = "🔴" if urgencia == "alta" else "🟡" if urgencia == "media" else "🟢"
            
            return f"{emoji} *Transferencia a agente*\n\nHe transferido tu conversación a nuestro equipo. Un agente te responderá pronto desde este mismo número.\n\nLa inteligencia artificial ha sido pausada para que puedas hablar directamente con una persona."
            
        except Exception as e:
            logger.error(f"Error escalando: {e}", exc_info=True)
            return "He registrado tu solicitud. Un agente te contactará pronto."
