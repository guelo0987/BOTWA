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


def _format_time_ampm(time_str: str) -> str:
    """Convierte hora 24h (HH:MM) a formato 12h con AM/PM."""
    try:
        h, m = map(int, time_str.split(':'))
        period = 'AM' if h < 12 else 'PM'
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {period}"
    except Exception:
        return time_str


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
                - Negocios con SERVICIOS Y CITAS (detailing, taller, spa, etc.): lista de servicios con precios y duración
                - TIENDA/CATÁLOGO (dealer, tienda): catálogo de productos/modelos con precios (o consulta al PDF si catalog_source=pdf)
                - Restaurante: menú si está configurado
                Si el negocio tiene catálogo en PDF, pasa en 'pregunta' lo que el usuario preguntó (ej. qué tienen, precios de X, cuánto cuesta Y).""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "categoria": types.Schema(
                            type=types.Type.STRING,
                            description="Categoría específica a mostrar (opcional). Ej: Colchones, Almohadas, Cortes"
                        ),
                        "pregunta": types.Schema(
                            type=types.Type.STRING,
                            description="Para catálogo en PDF: la pregunta del usuario (qué tienen, precios de X, cuánto cuesta Y, etc.). Usar cuando catalog_source=pdf."
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
                        "forzar_horario": types.Schema(
                            type=types.Type.BOOLEAN,
                            description="Poner en true SOLO si el system prompt indica que se puede agendar fuera de los horarios/días configurados (ej: profesional que trabaja domingos según instrucciones especiales)"
                        ),
                    },
                    required=["fecha"]
                )
            ),
            types.FunctionDeclaration(
                name="crear_cita",
                description="""Crea una cita, reservación o agenda una entrega.
                Usa cuando el usuario confirme que quiere agendar y tengas todos los datos necesarios.
                Para negocios con precios por tipo de vehículo o variantes (detailing, etc.): pasa en 'detalles' el tipo de vehículo (sedan, SUV, camioneta) y cualquier dato que defina el precio. Si hay varios profesionales, profesional_id es OBLIGATORIO.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "fecha": types.Schema(
                            type=types.Type.STRING,
                            description="Fecha en formato YYYY-MM-DD"
                        ),
                        "hora": types.Schema(
                            type=types.Type.STRING,
                            description="Hora en formato HH:MM en 24 horas. SIEMPRE usa 24h: 6 PM = 18:00, 1 PM = 13:00, 9 AM = 09:00"
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
                        "detalles": types.Schema(
                            type=types.Type.STRING,
                            description="Detalles que definen precio o servicio: tipo de vehículo (sedan, SUV, camioneta), tamaño, variante del servicio, etc. Todo lo que el negocio use para diferenciar precios o anotar en la cita."
                        ),
                        "nombre_factura": types.Schema(
                            type=types.Type.STRING,
                            description="Nombre para la factura/cita/reserva. Para tiendas: a nombre de quién va la factura. Para citas/salones/clínicas: a nombre de quién va la cita. Para restaurantes: a nombre de quién va la reserva. Preguntar al cliente antes de confirmar."
                        ),
                        "precio_producto": types.Schema(
                            type=types.Type.NUMBER,
                            description="Precio del producto en números, sin símbolo de moneda (ej: 25000, 1500.50). Pasar cuando el AI conoce el precio por haberlo leído del catálogo o imagen. Para tiendas con catálogo PDF, es OBLIGATORIO pasarlo si se identificó el precio."
                        ),
                        "forzar_horario": types.Schema(
                            type=types.Type.BOOLEAN,
                            description="Poner en true SOLO si el system prompt indica que se puede agendar fuera de los horarios/días configurados (ej: profesional que trabaja domingos según instrucciones especiales)"
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
                description="""Confirma la ASISTENCIA del usuario a una cita que YA EXISTE en el sistema.
                SOLO usar cuando el usuario pregunta sobre una cita existente, por ejemplo: 
                "¿a qué hora es mi cita?", "confirmo mi asistencia", "¿tengo cita?".
                
                ⚠️ NO usar este tool cuando estás en el proceso de CREAR una cita nueva.
                Si acabas de preguntar "¿Te gustaría confirmar esta cita?" o "¿Es correcto?" 
                y el usuario dice "sí"/"confirmo", debes usar crear_cita para CREAR la cita, NO este tool.""",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={},
                )
            ),
            types.FunctionDeclaration(
                name="cancelar_cita",
                description="""Cancela una cita, reservación o pedido existente.
                Puedes usar evento_id, o buscar por fecha/profesional si el usuario describe la cita.
                IMPORTANTE: Si el usuario menciona una fecha relativa (mañana, el domingo, etc.), DEBES convertirla al formato YYYY-MM-DD y pasarla en el parámetro 'fecha'. También pasa la hora si la conoces. Esto es NECESARIO para cancelar la cita correcta.
                El email es opcional. Si el cliente lo proporciona, se envía confirmación. Si no, se cancela sin email.""",
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
                            description="Correo electrónico del cliente para enviar confirmación de cancelación (opcional)"
                        ),
                    },
                )
            ),
            types.FunctionDeclaration(
                name="modificar_cita",
                description="""Modifica o reagenda una cita existente. Puede cambiar fecha/hora, servicio/producto, o ambos.
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
                            description="Nueva hora en formato HH:MM en 24 horas. SIEMPRE usa 24h: 6 PM = 18:00, 1 PM = 13:00"
                        ),
                        "servicio": types.Schema(
                            type=types.Type.STRING,
                            description="Nuevo servicio o producto si el cliente quiere cambiar lo que tenía agendado (opcional, solo si cambia)"
                        ),
                        "profesional_id": types.Schema(
                            type=types.Type.STRING,
                            description="ID o nombre del profesional (solo clínicas, opcional)"
                        ),
                        "email": types.Schema(
                            type=types.Type.STRING,
                            description="Correo electrónico para enviar confirmación de modificación"
                        ),
                        "nombre_factura": types.Schema(
                            type=types.Type.STRING,
                            description="Nuevo nombre para la factura/cita/reserva, si el cliente quiere cambiarlo"
                        ),
                        "direccion": types.Schema(
                            type=types.Type.STRING,
                            description="Nueva dirección de entrega si el cliente quiere cambiarla (solo tiendas con delivery). Incluir el link de Google Maps si fue compartido."
                        ),
                        "precio_producto": types.Schema(
                            type=types.Type.NUMBER,
                            description="Precio del nuevo producto en números, sin símbolo de moneda. Pasar cuando el AI conoce el precio por haberlo leído del catálogo o imagen (catálogos PDF)."
                        ),
                        "forzar_horario": types.Schema(
                            type=types.Type.BOOLEAN,
                            description="Poner en true SOLO si el system prompt indica que se puede agendar fuera de los horarios/días configurados"
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
    
    def _find_professional(self, profesional_id: str) -> dict | None:
        """Busca un profesional por ID exacto o por nombre parcial (case-insensitive)."""
        profs = self.config.get("professionals", [])
        if not profs:
            return None
        # ID exacto primero
        prof = next((p for p in profs if p["id"] == profesional_id), None)
        if not prof:
            pid = profesional_id.lower()
            prof = next((p for p in profs
                        if pid in p.get("name", "").lower()
                        or pid in p.get("id", "").lower()), None)
        return prof
    
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
        categoria = args.get("categoria", "").strip().lower()
        pregunta = (args.get("pregunta") or "").strip()
        currency = self.config.get("currency", "$")
        
        # CASO: Catálogo en PDF (Supabase bucket) — devolver texto directo
        # El Gemini principal ya tiene el catálogo en su system prompt.
        # Devolvemos el texto crudo para que el Gemini principal lo formatee.
        if self.config.get("catalog_source") == "pdf" and (
            self.config.get("catalog_pdf_key") or self.config.get("catalog_pdf_url")
        ):
            from app.services.catalog_pdf import get_catalog_text
            catalog_text = await get_catalog_text(self.client.id, self.config)
            if not catalog_text:
                logger.warning("ver_servicios PDF: no se pudo obtener texto para client %s", self.client.id)
                return "No pude cargar el catálogo en este momento. ¿Te gustaría que te cuente horarios de atención o que un asesor te contacte?"
            # Devolver el texto del PDF directamente — el Gemini principal lo formateará
            return f"CATÁLOGO COMPLETO DEL NEGOCIO (datos exactos del PDF):\n\n{catalog_text[:50000]}"
        
        # PRIORIZAR catálogo sobre servicios genéricos
        # Si existe catalog con productos, usar eso primero
        has_real_catalog = ("catalog" in self.config and 
                           self.config["catalog"].get("categories") and
                           any(cat.get("products") for cat in self.config["catalog"].get("categories", [])))
        
        # Verificar si los servicios son genéricos/placeholder (precio 0, nombre genérico)
        services_are_placeholder = False
        if "services" in self.config and self.config["services"]:
            # Si todos los servicios tienen precio 0 o nombres genéricos, son placeholder
            services = self.config["services"]
            real_services = [s for s in services if s.get('price', 0) > 0 or s.get('name', '').lower() not in ['servicio', 'service']]
            services_are_placeholder = len(real_services) == 0
        
        # CASO: Tienda con catálogo O negocio con servicios placeholder pero catálogo real
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
        
        # CASO: Negocio con servicios reales (no placeholder)
        if "services" in self.config and self.config["services"] and not services_are_placeholder:
            services = self.config["services"]
            # Filtrar servicios genéricos/placeholder
            real_services = [s for s in services if s.get('price', 0) > 0 or s.get('name', '').lower() not in ['servicio', 'service']]
            if categoria:
                real_services = [s for s in real_services if categoria in s["name"].lower()]
            
            if not real_services:
                return "No encontré servicios con ese nombre."
            
            texto = "📋 *Servicios disponibles:*\n\n"
            for s in real_services:
                mins = s.get('duration') or s.get('duration_minutes')
                duracion = f"{mins} min" if mins is not None else ""
                texto += f"• *{s['name']}*\n  💰 {currency}{s['price']:,} | ⏱️ {duracion}\n\n"
            return texto
        
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
                calendar_id = prof.get("calendar_id") or calendar_id
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
            
            # Verificar día de la semana (a menos que forzar_horario=true)
            forzar = args.get("forzar_horario", False)
            if not forzar:
                dia_semana = fecha.isoweekday()
                if dia_semana not in working_days:
                    dias = {1:"lunes", 2:"martes", 3:"miércoles", 4:"jueves", 5:"viernes", 6:"sábado", 7:"domingo"}
                    dias_trabajo = ", ".join([dias[d] for d in working_days])
                    return f"No trabajamos el {dias.get(dia_semana)}. Días disponibles: {dias_trabajo}"
            
            if not calendar_id:
                return "No hay calendario configurado para este servicio."

            # Import aquí para evitar circular import
            from app.services.calendar import calendar_service

            allow_overlapping = self.config.get("allow_overlapping_appointments", False)

            # Si overlapping está habilitado, generar slots dentro del horario sin consultar Google Calendar
            if allow_overlapping:
                effective_hours = {"start": "06:00", "end": "23:00"} if forzar else working_hours
                start_h, start_m = map(int, effective_hours["start"].split(':'))
                end_h, end_m = map(int, effective_hours["end"].split(':'))
                start_min = start_h * 60 + start_m
                end_min = end_h * 60 + end_m

                slots = []
                current = start_min
                while current + duration <= end_min:
                    slot_end = current + duration
                    slots.append({
                        "start": f"{current // 60:02d}:{current % 60:02d}",
                        "end": f"{slot_end // 60:02d}:{slot_end % 60:02d}",
                    })
                    current = slot_end

                logger.info(f"buscar_disponibilidad: overlapping habilitado, {len(slots)} slots generados sin verificar conflictos")
            else:
                # Obtener slots verificando conflictos en Google Calendar
                # Si forzar_horario, usar ventana amplia para mostrar slots fuera de horario normal
                effective_hours = {"start": "06:00", "end": "23:00"} if forzar else working_hours
                config_for_calendar = {
                    **self.config,
                    "business_hours": effective_hours,
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

            # DEBUG: log completo de slots para diagnosticar
            logger.info(
                f"buscar_disponibilidad: {len(slots)} slots en {fecha_str}. "
                f"calendar_id={calendar_id}, duration={duration}min. "
                f"Slots=[{', '.join(s['start']+'-'+s['end'] for s in slots)}]"
            )

            # Mostrar slots individualmente para que el usuario pueda elegir
            result = f"📅 Horarios disponibles para el {fecha.strftime('%d de %B de %Y')}:\n\n"
            for s in slots:
                result += f"• {_format_time_ampm(s['start'])} - {_format_time_ampm(s['end'])}\n"

            result += "\n¿Cuál de estos horarios te gustaría?"
            return result
            
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
            detalles = args.get("detalles")
            nombre_factura = args.get("nombre_factura")
            precio_producto_param = args.get("precio_producto")

            # Sanitizar inputs: remover HTML tags
            import re as _re
            def _sanitize(val):
                if isinstance(val, str):
                    return _re.sub(r'<[^>]+>', '', val).strip()
                return val
            
            servicio = _sanitize(servicio)
            direccion = _sanitize(direccion)
            detalles = _sanitize(detalles)
            ocasion = _sanitize(ocasion)
            nombre_factura = _sanitize(nombre_factura)
            
            # Validar email si se proporcionó
            if email:
                email = email.strip()
                email_regex = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
                if not _re.match(email_regex, email):
                    return f"El correo '{email}' no parece ser válido. ¿Podrías verificarlo? Ejemplo: nombre@correo.com"
            
            # VALIDACIÓN INNATA: Si el negocio tiene calendario y varios profesionales, profesional_id es obligatorio (cualquier tipo: clinic, salon, etc.)
            if (
                self.config.get("calendar_id")
                and self.config.get("professionals")
                and len(self.config["professionals"]) > 1
                and not profesional_id
            ):
                profs_list = ", ".join([p["name"] for p in self.config["professionals"]])
                return f"Para agendar tu cita, necesito saber con qué profesional te gustaría agendar. Los profesionales disponibles son: {profs_list}. ¿Con cuál te gustaría?"
            
            tz = pytz.timezone(self.config.get('timezone', 'America/Santo_Domingo'))
            fecha = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
            fecha = tz.localize(fecha)
            
            if fecha < datetime.now(tz):
                return "Esa hora ya pasó. ¿Me puedes dar otro horario?"
            
            # ==========================================
            # DETERMINAR CONFIGURACIÓN (global o por profesional)
            # ==========================================
            working_hours = self.config.get("business_hours", {"start": "08:00", "end": "18:00"})
            working_days = self.config.get("working_days", [1, 2, 3, 4, 5])
            calendar_id = self.calendar_id
            duration = self.config.get("slot_duration", 30)
            titulo_prefix = ""
            descripcion_extra = ""
            currency = self.config.get("currency", "$")
            profesional_nombre = None
            precio_servicio = None
            
            # Tienda con delivery: usar horario de entregas
            if self.business_type == "store":
                working_hours = self.config.get("delivery_hours", working_hours)
            
            # CASO: Profesional específico — override con SU horario y días
            prof = None
            if profesional_id and self.config.get("professionals"):
                prof = self._find_professional(profesional_id)
                if prof:
                    calendar_id = prof.get("calendar_id") or calendar_id
                    if prof.get("business_hours"):
                        working_hours = prof["business_hours"]
                    if prof.get("working_days"):
                        working_days = prof["working_days"]
                    if prof.get("slot_duration"):
                        duration = prof["slot_duration"]
                    titulo_prefix = f"{prof['name']} - "
                    profesional_nombre = prof['name']
                    descripcion_extra = f"\nProfesional: {prof['name']}"
                else:
                    profs_list = ", ".join([p["name"] for p in self.config["professionals"]])
                    return f"No encontré a '{profesional_id}'. Los profesionales disponibles son: {profs_list}"
            
            # CASO: Salón/Clínica con servicio
            if self.config.get("services"):
                srv = next((s for s in self.config["services"] if servicio.lower() in s["name"].lower()), None)
                if srv:
                    duration = srv.get("duration", duration)
                    servicio = srv["name"]
                    precio_servicio = f"{currency}{srv['price']:,}"
                    descripcion_extra += f"\nPrecio: {precio_servicio}"

            # CASO: Tienda con delivery
            from app.services.client_service import client_service
            if self.business_type == "store":
                duration = self.config.get("delivery_duration", 60)

                # Buscar precio del producto en el catálogo
                producto_precio = None
                if not precio_servicio and self.config.get("catalog"):
                    for cat in self.config["catalog"].get("categories", []):
                        for prod in cat.get("products", []):
                            if prod["name"].lower() in servicio.lower() or servicio.lower() in prod["name"].lower():
                                producto_precio = prod.get("price")
                                break
                        if producto_precio:
                            break

                # Si no se encontró en catálogo estructurado, usar el precio pasado por el AI
                # (e.g. leído de imagen de catálogo PDF)
                if producto_precio is None and precio_producto_param is not None:
                    try:
                        producto_precio = float(precio_producto_param)
                    except (ValueError, TypeError):
                        pass

                # Extraer costo de envío del campo detalles (el AI pasa "Costo de envío: RD$750")
                delivery_fee = None
                if detalles:
                    fee_match = _re.search(r'(?:envío|envio|delivery|flete)[:\s]*(?:RD)?\$?\s*([\d,\.]+)', detalles, _re.IGNORECASE)
                    if fee_match:
                        try:
                            delivery_fee = float(fee_match.group(1).replace(',', ''))
                        except (ValueError, TypeError):
                            pass

                # Si no se encontró en detalles, intentar con delivery_fee del config
                if delivery_fee is None:
                    delivery_fee = self.config.get("delivery_fee")

                # Calcular precio total: producto + envío
                if producto_precio is not None:
                    total = producto_precio + (delivery_fee or 0)
                    precio_servicio = f"{currency}{total:,.2f}"
                    descripcion_extra += f"\nPrecio producto: {currency}{producto_precio:,.2f}"
                    if delivery_fee:
                        descripcion_extra += f"\nCosto envío: {currency}{delivery_fee:,.2f}"
                    descripcion_extra += f"\nTotal: {precio_servicio}"
                elif delivery_fee:
                    # Solo envío (producto no encontrado en catálogo pero AI lo conoce)
                    precio_servicio = f"{currency}{delivery_fee:,.2f}"
                    descripcion_extra += f"\nCosto envío: {precio_servicio}"

                if direccion:
                    descripcion_extra += f"\n📍 Dirección: {direccion}"
                    await client_service.update_customer_data(self.customer.id, {"direccion": direccion})

            # CASO: Restaurante
            if num_personas:
                descripcion_extra += f"\n👥 Personas: {num_personas}"
            if area:
                descripcion_extra += f"\n🪑 Área: {area}"
            if ocasion:
                descripcion_extra += f"\n🎉 Ocasión: {ocasion}"
            if detalles:
                descripcion_extra += f"\n📋 Detalles: {detalles}"
            if nombre_factura:
                if self.business_type == "store":
                    descripcion_extra += f"\n🧾 Factura a nombre de: {nombre_factura}"
                elif self.business_type == "restaurant":
                    descripcion_extra += f"\n📋 Reserva a nombre de: {nombre_factura}"
                else:
                    descripcion_extra += f"\n📋 Cita a nombre de: {nombre_factura}"

            # Validar horario (a menos que forzar_horario=true)
            forzar = args.get("forzar_horario", False)
            if not forzar:
                dia_semana = fecha.isoweekday()
                if dia_semana not in working_days:
                    dias_nombres = {1: "lunes", 2: "martes", 3: "miércoles", 4: "jueves", 5: "viernes", 6: "sábado", 7: "domingo"}
                    dias_trabajo = ", ".join([dias_nombres[d] for d in working_days])
                    if profesional_nombre:
                        return f"{profesional_nombre} no trabaja el {dias_nombres.get(dia_semana)}. Sus días disponibles son: {dias_trabajo}. ¿Qué otro día te funciona?"
                    return f"Ese día no trabajamos. Nuestros días de atención son: {dias_trabajo}. ¿Qué otro día te funciona?"
                
                # Validar hora dentro del horario
                start_hour, start_min = map(int, working_hours['start'].split(':'))
                end_hour, end_min = map(int, working_hours['end'].split(':'))
                hora_cita = fecha.hour * 60 + fecha.minute
                hora_inicio = start_hour * 60 + start_min
                hora_fin = end_hour * 60 + end_min
                
                if hora_cita < hora_inicio or hora_cita > hora_fin:
                    return f"Esa hora está fuera de nuestro horario de atención ({_format_time_ampm(working_hours['start'])} - {_format_time_ampm(working_hours['end'])}). ¿Te funciona algún horario dentro de ese rango?"
            
            # Guardar email del cliente si lo proporciona
            if email:
                await client_service.update_customer_data(self.customer.id, {"email": email})
            
            # ==========================================
            # VERIFICAR DISPONIBILIDAD DEL SLOT ESPECÍFICO
            # ==========================================
            from app.services.calendar import calendar_service

            allow_overlapping = self.config.get("allow_overlapping_appointments", False)

            if allow_overlapping:
                # Solo validar que esté dentro del horario laboral (no verificar conflictos con otros eventos)
                hora_solicitada = fecha.strftime('%H:%M')
                logger.info(f"crear_cita: overlapping habilitado, saltando verificación de conflictos para {hora_solicitada}")
            else:
                # working_hours ya tiene el override del profesional si aplica

                # Obtener configuración para el calendario específico
                # Si forzar_horario, usar ventana amplia para permitir slots fuera de horario normal
                effective_hours = {"start": "06:00", "end": "23:00"} if forzar else working_hours
                config_for_calendar = {
                    **self.config,
                    "business_hours": effective_hours,
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

                # DEBUG: log completo para diagnosticar problemas de horario
                logger.info(
                    f"crear_cita: verificando {hora_solicitada} en {len(slots_disponibles)} slots disponibles. "
                    f"calendar_id={calendar_id}, fecha={fecha_str}, duration={duration}min"
                )
                if slots_disponibles:
                    logger.info(f"crear_cita: slots=[{', '.join(s['start']+'-'+s['end'] for s in slots_disponibles)}]")

                for slot in slots_disponibles:
                    slot_start = slot.get('start', '')
                    slot_end = slot.get('end', '')
                    # Verificar si la hora solicitada cae dentro de algún slot disponible
                    # Solo validamos que el INICIO esté en un slot libre.
                    # Google Calendar se encarga de validar conflictos reales.
                    if slot_start and slot_end:
                        s_h, s_m = map(int, slot_start.split(':'))
                        e_h, e_m = map(int, slot_end.split(':'))
                        r_h, r_m = map(int, hora_solicitada.split(':'))
                        slot_start_min = s_h * 60 + s_m
                        slot_end_min = e_h * 60 + e_m
                        requested_min = r_h * 60 + r_m
                        # La hora de inicio debe caer dentro de algún slot libre
                        if requested_min >= slot_start_min and requested_min < slot_end_min:
                            slot_disponible = True
                            logger.info(f"crear_cita: MATCH hora={hora_solicitada} en slot {slot_start}-{slot_end}")
                            break

                if not slot_disponible:
                    logger.warning(
                        f"crear_cita: hora {hora_solicitada} NO disponible. "
                        f"Slots disponibles: {[s['start']+'-'+s['end'] for s in slots_disponibles]}"
                    )
                    # Formatear slots disponibles para mostrar al usuario
                    slots_text = "\n".join([f"• {_format_time_ampm(s['start'])} - {_format_time_ampm(s['end'])}" for s in slots_disponibles[:10]])
                    if slots_disponibles:
                        return f"❌ Lo siento, el horario {_format_time_ampm(hora_solicitada)} no está disponible para el {fecha.strftime('%d de %B de %Y')}.\n\n📅 Horarios disponibles:\n{slots_text}\n\n¿Cuál prefieres?"
                    else:
                        return f"❌ Lo siento, no hay horarios disponibles para el {fecha.strftime('%d de %B de %Y')}. ¿Te funciona otra fecha?"

            fin = fecha + timedelta(minutes=duration)
            nombre = self.customer.full_name or "Cliente"
            titulo = f"{titulo_prefix}{servicio} - {nombre}"
            
            # Crear en Google Calendar - incluir precio si está disponible
            precio_str = f"\nPrecio: {precio_servicio}" if precio_servicio else ""
            evento = await calendar_service.create_appointment(
                calendar_id=calendar_id,
                title=titulo,
                start_time=fecha,
                end_time=fin,
                description=f"Agendado via WhatsApp\nServicio: {servicio}{descripcion_extra}{precio_str}\nTeléfono: {self.customer.phone_number}" + (f"\nEmail: {email}" if email else ""),
                attendee_phone=self.customer.phone_number,
                config=self.config,
                location=direccion or ""
            )
            
            if evento:
                # Guardar en BD
                from app.models.tables import Appointment
                from sqlalchemy import select, and_
                async with AsyncSessionLocal() as session:
                    # Dedup: verificar que no exista una cita igual (mismo cliente, mismo horario ±5 min)
                    dedup_window = timedelta(minutes=5)
                    existing = await session.execute(
                        select(Appointment).where(
                            and_(
                                Appointment.customer_id == self.customer.id,
                                Appointment.client_id == self.client.id,
                                Appointment.status == "CONFIRMED",
                                Appointment.start_time >= fecha - dedup_window,
                                Appointment.start_time <= fecha + dedup_window,
                            )
                        )
                    )
                    if existing.scalar_one_or_none():
                        logger.warning(f"Cita duplicada detectada para customer={self.customer.id} en {fecha}")
                        # Borrar el evento duplicado de Google Calendar
                        try:
                            await calendar_service.cancel_appointment(
                                calendar_id=calendar_id,
                                event_id=evento.get('id')
                            )
                        except Exception:
                            pass
                        return "Ya tienes una cita confirmada en ese horario. ¿Deseas ver tus citas o agendar en otro horario?"

                    # Extraer precio numérico de precio_servicio (e.g. "$1,500" → 1500.00)
                    precio_numerico = None
                    if precio_servicio:
                        try:
                            precio_numerico = float(_re.sub(r'[^\d.]', '', precio_servicio))
                        except (ValueError, TypeError):
                            pass

                    appointment = Appointment(
                        client_id=self.client.id,
                        customer_id=self.customer.id,
                        google_event_id=evento.get('id'),
                        start_time=fecha,
                        end_time=fin,
                        status="CONFIRMED",
                        notes=f"{servicio}{descripcion_extra}",
                        total_price=precio_numerico,
                        invoice_name=nombre_factura
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
                            "detalles": detalles,
                            "profesional": profesional_nombre,
                            "precio": precio_servicio,
                            "direccion": direccion,
                            "num_personas": num_personas,
                            "area": area,
                            "ocasion": ocasion,
                            "nombre_factura": nombre_factura
                        }
                        
                        email_enviado = await email_service.send_confirmation_email(
                            to_email=email,
                            business_name=self.client.business_name,
                            business_type=self.business_type,
                            customer_name=nombre,
                            appointment_date=fecha,
                            appointment_details=appointment_details,
                            client_settings=self.client.email_settings
                        )
                    except Exception as e:
                        logger.error(f"Error enviando email de confirmación: {e}")
                
                # ==========================================
                # MENSAJE DE CONFIRMACIÓN SEGÚN TIPO
                # ==========================================
                email_msg = "\n\n📧 Te enviamos confirmación a tu correo." if email_enviado else ""
                
                hora_display = _format_time_ampm(hora_str)
                if self.business_type == "store":
                    factura_msg = f"\n🧾 Factura: {nombre_factura}" if nombre_factura else ""
                    return f"✅ *Entrega agendada*\n\n📅 {fecha.strftime('%d de %B de %Y')}\n🕐 {hora_display}\n📦 {servicio}\n📍 {direccion or 'Pendiente'}{factura_msg}{email_msg}\n\n¡Te esperamos!"
                elif self.business_type == "restaurant":
                    area_msg = f"\n🪑 Área: {area}" if area else ""
                    ocasion_msg = f"\n🎉 Ocasión: {ocasion}" if ocasion else ""
                    reserva_msg = f"\n📋 A nombre de: {nombre_factura}" if nombre_factura else ""
                    return f"🍽️ *¡Reservación confirmada!*\n\n📅 {fecha.strftime('%d de %B de %Y')}\n🕐 {hora_display}\n👥 {num_personas or 2} personas{area_msg}{ocasion_msg}{reserva_msg}{email_msg}\n\n¡Será un placer atenderles! 🥂"
                elif self.business_type == "clinic":
                    prof_msg = f"\n👨‍⚕️ {profesional_nombre}" if profesional_nombre else ""
                    cita_msg = f"\n📋 A nombre de: {nombre_factura}" if nombre_factura else ""
                    return f"🏥 *Cita médica confirmada*\n\n📅 {fecha.strftime('%d de %B de %Y')}\n🕐 {hora_display}\n📋 {servicio}{prof_msg}{cita_msg}{email_msg}\n\n¡Le esperamos!"
                else:
                    det_msg = f"\n📋 {detalles}" if detalles else ""
                    prof_msg = f"\n👤 {profesional_nombre}" if profesional_nombre else ""
                    cita_msg = f"\n📋 A nombre de: {nombre_factura}" if nombre_factura else ""
                    return f"✅ *Cita confirmada*\n\n📅 {fecha.strftime('%d de %B de %Y')}\n🕐 {hora_display}\n📋 {servicio}{det_msg}{prof_msg}{cita_msg}{email_msg}\n\n¡Te esperamos! 💖"
            
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
            
            currency = self.config.get("currency", "$")
            for cita in citas:
                fecha_local = cita.start_time.astimezone(tz)
                texto += f"• {cita.notes or 'Cita'}\n"
                texto += f"  📅 {fecha_local.strftime('%d/%m/%Y')} a las {_format_time_ampm(fecha_local.strftime('%H:%M'))}\n"
                if cita.total_price is not None:
                    texto += f"  💰 {currency}{cita.total_price:,.2f}\n"
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
                f"🕐 Hora: {_format_time_ampm(fecha_local.strftime('%H:%M'))}\n"
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
                        prof = self._find_professional(profesional_id)
                        if prof:
                            query = query.where(Appointment.notes.contains(prof['name']))
                    
                    result = await session.execute(query)
                    appointment = result.scalar_one_or_none()
                
                # Si no se encontró por fecha/hora exacta, buscar por solo fecha (sin hora)
                if not appointment and fecha_str and not hora_str:
                    fecha_dia = datetime.strptime(fecha_str, "%Y-%m-%d")
                    fecha_dia = tz.localize(fecha_dia)
                    fecha_inicio_dia = fecha_dia.replace(hour=0, minute=0, second=0)
                    fecha_fin_dia = fecha_dia.replace(hour=23, minute=59, second=59)
                    
                    query_dia = select(Appointment).where(
                        and_(
                            Appointment.customer_id == self.customer.id,
                            Appointment.client_id == self.client.id,
                            Appointment.status == "CONFIRMED",
                            Appointment.start_time >= fecha_inicio_dia,
                            Appointment.start_time <= fecha_fin_dia
                        )
                    )
                    result = await session.execute(query_dia)
                    appointment = result.scalar_one_or_none()
                
                # Si aún no se encontró, listar citas para que el usuario elija
                if not appointment:
                    result = await session.execute(
                        select(Appointment).where(
                            and_(
                                Appointment.customer_id == self.customer.id,
                                Appointment.client_id == self.client.id,
                                Appointment.status == "CONFIRMED",
                                Appointment.start_time >= datetime.now(pytz.UTC)
                            )
                        ).order_by(Appointment.start_time)
                    )
                    citas = result.scalars().all()
                    
                    if len(citas) == 1:
                        # Solo una cita → usarla directamente
                        appointment = citas[0]
                    elif len(citas) > 1:
                        # Varias citas → pedir al usuario que especifique
                        texto = "Tienes varias citas programadas. ¿Cuál deseas cancelar?\n\n"
                        for cita in citas:
                            fecha_local = cita.start_time.astimezone(tz)
                            texto += f"• {cita.notes or 'Cita'}\n"
                            texto += f"  📅 {fecha_local.strftime('%A %d de %B')} a las {_format_time_ampm(fecha_local.strftime('%H:%M'))}\n\n"
                        texto += "Dime la fecha de la cita que deseas cancelar."
                        return texto
                
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
                    
                    # Usar email proporcionado o el guardado, validar que sea email real
                    customer_email = email or (self.customer.data.get("email") if self.customer.data else None)
                    # Validar que sea un email real (contiene @) y no un teléfono
                    if customer_email and "@" not in customer_email:
                        customer_email = None
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
                                appointment_details={"cancelado": True},
                                client_settings=self.client.email_settings
                            )
                            logger.info(f"Email de cancelación {'enviado' if email_enviado else 'falló'} a {customer_email}")
                        except Exception as e:
                            logger.error(f"Error enviando email de cancelación: {e}", exc_info=True)
                    else:
                        logger.warning("No hay email para enviar confirmación de cancelación")
                    
                    fecha_local = appointment.start_time.astimezone(tz)
                    email_msg = f"\n\n📧 Te enviamos confirmación de cancelación a {customer_email}" if email_enviado else ""
                    return f"✅ *Cita cancelada*\n\n📅 {fecha_local.strftime('%d de %B de %Y')}\n🕐 {_format_time_ampm(fecha_local.strftime('%H:%M'))}{email_msg}\n\n¿Deseas agendar otra cita?"
                
                return "No pude cancelar la cita en el calendario. Intenta de nuevo."
            
        except Exception as e:
            logger.error(f"Error cancelando: {e}", exc_info=True)
            return "Hubo un error al cancelar. Intenta de nuevo."
    
    # ==========================================
    # MODIFICAR/REAGENDAR CITA
    # ==========================================
    async def _modificar_cita(self, args: dict) -> str:
        """Modifica una cita existente a nueva fecha/hora y/o servicio/producto."""
        try:
            from app.services.calendar import calendar_service
            from app.models.tables import Appointment
            from sqlalchemy import select, and_
            import re as _re

            fecha_antigua_str = args.get("fecha_antigua")
            hora_antigua_str = args.get("hora_antigua")
            fecha_nueva_str = args.get("fecha_nueva")
            hora_nueva_str = args.get("hora_nueva")
            nuevo_servicio = args.get("servicio")
            profesional_id = args.get("profesional_id")
            email = args.get("email")
            nombre_factura = args.get("nombre_factura")
            nueva_direccion = args.get("direccion")
            precio_producto_param = args.get("precio_producto")

            tz = pytz.timezone(self.config.get('timezone', 'America/Santo_Domingo'))
            
            # Parsear fechas
            fecha_antigua = datetime.strptime(f"{fecha_antigua_str} {hora_antigua_str}", "%Y-%m-%d %H:%M")
            fecha_antigua = tz.localize(fecha_antigua)
            
            fecha_nueva = datetime.strptime(f"{fecha_nueva_str} {hora_nueva_str}", "%Y-%m-%d %H:%M")
            fecha_nueva = tz.localize(fecha_nueva)
            
            # Validar nueva fecha
            if fecha_nueva < datetime.now(tz):
                return "La nueva fecha ya pasó. ¿Me puedes dar otra fecha?"
            
            # Validar horario (a menos que forzar_horario=true)
            forzar = args.get("forzar_horario", False)
            working_hours = self.config.get("business_hours", {"start": "08:00", "end": "18:00"})
            working_days = self.config.get("working_days", [1, 2, 3, 4, 5])
            
            # Override con datos del profesional si aplica
            if profesional_id and self.config.get("professionals"):
                prof = next((p for p in self.config["professionals"] 
                            if profesional_id.lower() in p.get("name", "").lower()
                            or profesional_id.lower() in p.get("id", "").lower()), None)
                if prof:
                    if prof.get("working_days"):
                        working_days = prof["working_days"]
                    if prof.get("business_hours"):
                        working_hours = prof["business_hours"]
            
            if not forzar:
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
                
                if hora_cita < hora_inicio or hora_cita > hora_fin:
                    return f"Esa hora está fuera del horario ({_format_time_ampm(working_hours['start'])} - {_format_time_ampm(working_hours['end'])})"
            
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

                # Si el servicio/producto cambia, recalcular precio, notes y duración
                nuevo_precio = None
                nuevas_notes = None
                currency = self.config.get("currency", "$")

                if nuevo_servicio:
                    descripcion_extra = ""
                    precio_servicio = None

                    # Buscar en servicios configurados (salon, clinic)
                    if self.config.get("services"):
                        srv = next((s for s in self.config["services"] if nuevo_servicio.lower() in s["name"].lower()), None)
                        if srv:
                            nuevo_servicio = srv["name"]
                            precio_servicio = f"{currency}{srv['price']:,}"
                            descripcion_extra += f"\nPrecio: {precio_servicio}"

                    # Buscar en catálogo (store)
                    if not precio_servicio and self.config.get("catalog"):
                        for cat in self.config["catalog"].get("categories", []):
                            for prod in cat.get("products", []):
                                if prod["name"].lower() in nuevo_servicio.lower() or nuevo_servicio.lower() in prod["name"].lower():
                                    producto_precio = prod.get("price")
                                    if producto_precio is not None:
                                        delivery_fee = self.config.get("delivery_fee")
                                        total = producto_precio + (delivery_fee or 0)
                                        precio_servicio = f"{currency}{total:,.2f}"
                                        descripcion_extra += f"\nPrecio producto: {currency}{producto_precio:,.2f}"
                                        if delivery_fee:
                                            descripcion_extra += f"\nCosto envío: {currency}{delivery_fee:,.2f}"
                                        descripcion_extra += f"\nTotal: {precio_servicio}"
                                    break
                            if precio_servicio:
                                break

                    # Si no se encontró en catálogo estructurado, usar precio pasado por el AI
                    # (e.g. leído de imagen de catálogo PDF)
                    if not precio_servicio and precio_producto_param is not None:
                        try:
                            producto_precio_val = float(precio_producto_param)
                            delivery_fee = self.config.get("delivery_fee")
                            total = producto_precio_val + (delivery_fee or 0)
                            precio_servicio = f"{currency}{total:,.2f}"
                            descripcion_extra += f"\nPrecio producto: {currency}{producto_precio_val:,.2f}"
                            if delivery_fee:
                                descripcion_extra += f"\nCosto envío: {currency}{delivery_fee:,.2f}"
                            descripcion_extra += f"\nTotal: {precio_servicio}"
                        except (ValueError, TypeError):
                            pass

                    # Mantener info del profesional en notes
                    profesional_nombre = None
                    for prof in self.config.get("professionals", []):
                        if prof.get("name") in (appointment.notes or ""):
                            profesional_nombre = prof["name"]
                            descripcion_extra += f"\nProfesional: {profesional_nombre}"
                            break

                    # Dirección: usar la nueva si la AI la pasa, si no preservar la original
                    if nueva_direccion:
                        descripcion_extra += f"\n📍 Dirección: {nueva_direccion}"
                    elif appointment.notes:
                        dir_match = _re.search(r'📍?\s*Dirección:\s*(.+)', appointment.notes)
                        if dir_match:
                            descripcion_extra += f"\n📍 Dirección: {dir_match.group(1).strip()}"

                    # Agregar nombre de factura
                    if nombre_factura:
                        if self.business_type == "store":
                            descripcion_extra += f"\n🧾 Factura a nombre de: {nombre_factura}"
                        elif self.business_type == "restaurant":
                            descripcion_extra += f"\n📋 Reserva a nombre de: {nombre_factura}"
                        else:
                            descripcion_extra += f"\n📋 Cita a nombre de: {nombre_factura}"

                    nuevas_notes = f"{nuevo_servicio}{descripcion_extra}"

                    # Extraer precio numérico
                    if precio_servicio:
                        try:
                            nuevo_precio = float(_re.sub(r'[^\d.]', '', precio_servicio))
                        except (ValueError, TypeError):
                            pass

                # Even if product didn't change, add nombre_factura to existing notes if provided
                if not nuevas_notes and nombre_factura:
                    existing_notes = appointment.notes or ""
                    factura_label = "Factura" if self.business_type == "store" else ("Reserva" if self.business_type == "restaurant" else "Cita")
                    # Remove old factura line if present
                    existing_notes = _re.sub(r'\n[🧾📋]?\s*(Factura|Reserva|Cita) a nombre de:.*', '', existing_notes)
                    if self.business_type == "store":
                        existing_notes += f"\n🧾 Factura a nombre de: {nombre_factura}"
                    elif self.business_type == "restaurant":
                        existing_notes += f"\n📋 Reserva a nombre de: {nombre_factura}"
                    else:
                        existing_notes += f"\n📋 Cita a nombre de: {nombre_factura}"
                    nuevas_notes = existing_notes

                # Calcular nueva duración
                duration = (appointment.end_time - appointment.start_time).total_seconds() / 60
                # Si cambia servicio y tiene duración definida, usar esa
                if nuevo_servicio and self.config.get("services"):
                    srv = next((s for s in self.config["services"] if nuevo_servicio.lower() in s["name"].lower()), None)
                    if srv and srv.get("duration"):
                        duration = srv["duration"]
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

                allow_overlapping = self.config.get("allow_overlapping_appointments", False)

                if not allow_overlapping:
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
                        slot_end = slot.get('end', '')
                        if slot_start and slot_end:
                            s_h, s_m = map(int, slot_start.split(':'))
                            e_h, e_m = map(int, slot_end.split(':'))
                            r_h, r_m = map(int, hora_solicitada.split(':'))
                            slot_start_min = s_h * 60 + s_m
                            slot_end_min = e_h * 60 + e_m
                            requested_min = r_h * 60 + r_m
                            if requested_min >= slot_start_min and requested_min < slot_end_min:
                                slot_disponible = True
                                break

                    if not slot_disponible:
                        slots_text = "\n".join([f"• {_format_time_ampm(s['start'])} - {_format_time_ampm(s['end'])}" for s in slots_disponibles[:10]])
                        if slots_disponibles:
                            return f"❌ Lo siento, el horario {_format_time_ampm(hora_solicitada)} no está disponible para el {fecha_nueva.strftime('%d de %B de %Y')}.\n\n📅 Horarios disponibles:\n{slots_text}\n\n¿Cuál prefieres?"
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
                    
                    # 2) Usar notes actualizadas si cambió el servicio
                    effective_notes = nuevas_notes if nuevas_notes else appointment.notes

                    title = f"Cita: {self.customer.full_name or 'Cliente'}"
                    if effective_notes:
                        notes_parts = effective_notes.split('\n')
                        title = notes_parts[0] if notes_parts else title
                    # Extraer dirección para el campo location de Calendar
                    # Prioridad: nueva dirección pasada por AI > dirección en notes existentes
                    reschedule_location = nueva_direccion or ""
                    if not reschedule_location and effective_notes:
                        loc_match = _re.search(r'Dirección:\s*(.+)', effective_notes)
                        if loc_match:
                            reschedule_location = loc_match.group(1).strip()

                    # Build rich description like _crear_cita
                    customer_email = email or (self.customer.data.get("email") if self.customer.data else None)
                    rich_description = f"Modificado via WhatsApp\nServicio: {effective_notes}"
                    rich_description += f"\nTeléfono: {self.customer.phone_number}"
                    if customer_email:
                        rich_description += f"\nEmail: {customer_email}"

                    new_event = await calendar_service.create_appointment(
                        calendar_id=calendar_id,
                        title=title,
                        start_time=fecha_nueva,
                        end_time=fecha_nueva_fin,
                        description=rich_description,
                        attendee_phone=self.customer.phone_number or "",
                        config=self.config,
                        location=reschedule_location,
                    )
                    if not new_event or not new_event.get("id"):
                        return "No pude crear la nueva cita en el calendario. Intenta de nuevo."

                    # 3) Actualizar en BD con el nuevo event_id, fechas, y servicio/precio si cambiaron
                    appointment.google_event_id = new_event["id"]
                    appointment.start_time = fecha_nueva
                    appointment.end_time = fecha_nueva_fin
                    if nuevas_notes:
                        appointment.notes = nuevas_notes
                    if nuevo_precio is not None:
                        appointment.total_price = nuevo_precio
                    if nombre_factura:
                        appointment.invoice_name = nombre_factura
                    await session.commit()
                    
                    # Guardar email y/o nueva dirección si se proporcionan
                    if email or nueva_direccion:
                        from app.services.client_service import client_service
                        update_data = {}
                        if email:
                            update_data["email"] = email
                        if nueva_direccion:
                            update_data["direccion"] = nueva_direccion
                        await client_service.update_customer_data(self.customer.id, update_data)
                    
                    # Extraer profesional para el mensaje de confirmación
                    profesional_nombre = None
                    for prof in self.config.get("professionals", []):
                        if prof.get("name") in (effective_notes or ""):
                            profesional_nombre = prof.get("name")
                            break

                    # Enviar email de confirmación
                    customer_email = email or (self.customer.data.get("email") if self.customer.data else None)
                    email_enviado = False
                    if customer_email:
                        try:
                            from app.services.email_service import email_service

                            notes_parts = effective_notes.split('\n') if effective_notes else []
                            servicio = notes_parts[0] if notes_parts else "Cita"
                            # Extract price and address from notes for email
                            precio_email = None
                            direccion_email = None
                            for part in notes_parts:
                                if 'Total:' in part or ('Precio:' in part and not precio_email):
                                    precio_email = part.split(':',1)[-1].strip()
                                if 'Dirección:' in part:
                                    direccion_email = part.split(':',1)[-1].strip()
                            appointment_details = {
                                "servicio": servicio,
                                "profesional": profesional_nombre,
                                "modificada": True,
                                "nombre_factura": nombre_factura or appointment.invoice_name,
                                "precio": precio_email,
                                "direccion": direccion_email,
                            }
                            
                            email_enviado = await email_service.send_confirmation_email(
                                to_email=customer_email,
                                business_name=self.client.business_name,
                                business_type=self.business_type,
                                customer_name=self.customer.full_name or "Cliente",
                                appointment_date=fecha_nueva,
                                appointment_details=appointment_details,
                                client_settings=self.client.email_settings
                            )
                        except Exception as e:
                            logger.error(f"Error enviando email de modificación: {e}")
                    
                    email_msg = "\n\n📧 Te enviamos confirmación a tu correo." if email_enviado else ""
                    
                    # Mensaje de confirmación — extraer detalles de las notes
                    hora_nueva_display = _format_time_ampm(hora_nueva_str)
                    mod_notes_parts = effective_notes.split('\n') if effective_notes else []
                    mod_servicio = mod_notes_parts[0] if mod_notes_parts else ""
                    mod_precio = None
                    mod_direccion = None
                    mod_factura = nombre_factura or appointment.invoice_name
                    for part in mod_notes_parts:
                        if 'Total:' in part:
                            mod_precio = part.split(':',1)[-1].strip()
                        elif 'Precio:' in part and not mod_precio:
                            mod_precio = part.split(':',1)[-1].strip()
                        if 'Dirección:' in part:
                            mod_direccion = part.split(':',1)[-1].strip()

                    if self.business_type == "store":
                        servicio_msg = f"\n📦 {mod_servicio}" if mod_servicio else ""
                        precio_msg = f"\n💰 {mod_precio}" if mod_precio else ""
                        dir_msg = f"\n📍 {mod_direccion}" if mod_direccion else ""
                        factura_msg = f"\n🧾 Factura: {mod_factura}" if mod_factura else ""
                        return f"✅ *Entrega modificada*\n\n📅 {fecha_nueva.strftime('%d de %B de %Y')}\n🕐 {hora_nueva_display}{servicio_msg}{precio_msg}{dir_msg}{factura_msg}{email_msg}\n\n¡Te esperamos!"
                    elif self.business_type == "restaurant":
                        reserva_msg = f"\n📋 A nombre de: {mod_factura}" if mod_factura else ""
                        return f"🍽️ *¡Reservación modificada!*\n\n📅 {fecha_nueva.strftime('%d de %B de %Y')}\n🕐 {hora_nueva_display}{reserva_msg}{email_msg}\n\n¡Será un placer atenderles! 🥂"
                    elif self.business_type == "clinic":
                        prof_msg = f"\n👨‍⚕️ {profesional_nombre}" if profesional_nombre else ""
                        cita_msg = f"\n📋 A nombre de: {mod_factura}" if mod_factura else ""
                        return f"🏥 *Cita modificada*\n\n📅 {fecha_nueva.strftime('%d de %B de %Y')}\n🕐 {hora_nueva_display}{prof_msg}{cita_msg}{email_msg}\n\n¡Le esperamos!"
                    else:
                        servicio_msg = f"\n📋 {mod_servicio}" if mod_servicio else ""
                        cita_msg = f"\n📋 A nombre de: {mod_factura}" if mod_factura else ""
                        return f"✅ *Cita modificada*\n\n📅 {fecha_nueva.strftime('%d de %B de %Y')}\n🕐 {hora_nueva_display}{servicio_msg}{cita_msg}{email_msg}\n\n¡Te esperamos!"
                
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
        """Guarda datos del usuario con validación."""
        try:
            import re
            from app.services.client_service import client_service
            
            campo = args.get("campo", "").strip()
            valor = args.get("valor", "").strip()
            
            if not campo or not valor:
                return "No se proporcionaron datos para guardar."
            
            # Sanitizar: remover tags HTML para evitar XSS en admin panel
            valor = re.sub(r'<[^>]+>', '', valor).strip()
            
            # Validación de email
            if campo.lower() in ('email', 'correo', 'correo_electronico', 'e-mail'):
                email_regex = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_regex, valor):
                    return f"El correo '{valor}' no parece ser válido. ¿Podrías verificarlo? Ejemplo: nombre@correo.com"
            
            # Validación de teléfono
            if campo.lower() in ('telefono', 'tel', 'phone', 'celular', 'móvil'):
                digitos = re.sub(r'[^\d+]', '', valor)
                if len(digitos) < 7:
                    return f"El teléfono '{valor}' parece muy corto. ¿Podrías verificarlo?"
                valor = digitos  # Guardar solo dígitos limpios
            
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
            
            # Notificar al dueño por correo
            if self.client.notification_email:
                try:
                    from app.services.email_service import email_service
                    import asyncio
                    asyncio.create_task(
                        email_service.send_escalation_email(
                            to_email=self.client.notification_email,
                            business_name=self.client.business_name,
                            customer_name=self.customer.full_name or "Cliente",
                            customer_phone=self.customer.phone_number,
                            motivo=motivo or "No especificado",
                            resumen=resumen or "El cliente ha solicitado hablar con un agente humano."
                        )
                    )
                except Exception as e:
                    logger.error(f"Error al enviar notificación de escalación: {e}")
            
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
