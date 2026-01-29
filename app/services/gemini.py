from google import genai
from google.genai import types
import logging
from datetime import datetime, timedelta

from app.core.config import settings
from app.models.tables import Client, Customer

logger = logging.getLogger(__name__)


class GeminiService:
    """
    Servicio para interactuar con Google Gemini.
    Soporta Function Calling para ejecutar herramientas.
    """
    
    def __init__(self):
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.model = settings.GEMINI_MODEL
    
    def build_system_prompt(
        self,
        client: Client,
        customer: Customer | None = None
    ) -> str:
        """
        Construye el system prompt completo y profesional para el agente.
        Adaptado según el tipo de negocio y su configuración.
        """
        config = client.tools_config or {}
        business_type = config.get('business_type', 'general')
        now = datetime.now()
        
        # Días de la semana en español
        dias_es = {
            'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
            'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado', 'Sunday': 'Domingo'
        }
        dia_actual = dias_es.get(now.strftime("%A"), now.strftime("%A"))
        
        # ==========================================
        # PROMPT BASE - COMPORTAMIENTO PROFESIONAL
        # ==========================================
        base_system = f"""Eres el asistente virtual de *{client.business_name}*. Tu objetivo es brindar una atención profesional, cálida y eficiente.

═══════════════════════════════════════════════════
REGLAS FUNDAMENTALES DE COMPORTAMIENTO
═══════════════════════════════════════════════════

1. SALUDO INICIAL (cuando es el primer mensaje o saludo):
   - Saluda cordialmente y preséntate como asistente de {client.business_name}
   - Menciona brevemente qué puede hacer el negocio
   - Pregunta en qué puedes ayudar HOY
   - Ejemplo: "¡Hola! Bienvenido/a a *{client.business_name}*. Soy tu asistente virtual. ¿En qué puedo ayudarte hoy?"

2. CONVERSACIÓN NATURAL:
   - Habla como una persona real, NO como un robot
   - NUNCA listes tus capacidades técnicas ni herramientas
   - NO digas "puedo hacer X, Y, Z" - simplemente hazlo cuando sea necesario
   - Respuestas cortas y directas (máximo 2-3 oraciones por turno)
   - Usa emojis con moderación (1-2 máximo por mensaje)

3. FLUJO DE ATENCIÓN:
   - Escucha primero qué necesita el cliente
   - Haz UNA pregunta a la vez
   - Guía la conversación según lo que el cliente quiere
   - Confirma antes de ejecutar acciones importantes

4. PROFESIONALISMO:
   - Trata al cliente con respeto y calidez
   - Si no puedes ayudar con algo, ofrece alternativas
   - Si hay emergencia o queja seria → escala a humano inmediatamente
   - Mantén el enfoque en resolver la necesidad del cliente

5. ⚠️ CORREO ELECTRÓNICO (MUY IMPORTANTE - PRIORIDAD MÁXIMA):
   - SIEMPRE pregunta el correo electrónico DESDE EL PRINCIPIO cuando el usuario quiere agendar
   - Pregúntalo como SEGUNDO dato (después del nombre), ANTES de fecha/hora
   - Para modificar/cancelar: pregunta el correo PRIMERO antes de cualquier acción
   - Incluso si ya tienen un email guardado, pregunta para confirmar o actualizar
   - Explica siempre: "Para enviarte la confirmación, ¿me podrías proporcionar tu correo electrónico?"
   - ANTES de ejecutar cualquier acción (crear/modificar/cancelar), confirma: "Te enviaremos la confirmación a [correo]. ¿Confirmas?"
   - DESPUÉS de ejecutar, confirma explícitamente: "✅ [Acción] completada. Te enviamos la confirmación a [correo]"
   - El correo es OBLIGATORIO - NO procedas sin él

6. ⚠️ CONFIRMACIÓN DE CITAS (MUY IMPORTANTE - PRIORIDAD ALTA):
   - REVISA SIEMPRE el historial de conversación ANTES de responder
   - Si en el historial reciente (últimos 2-3 mensajes) hay un mensaje tuyo que contiene:
     * "Confirmación de Cita"
     * "¿Podrás asistir?"
     * "Responde *SÍ* para confirmar"
     * "Responde *NO* para cancelar"
     * "Responde *CAMBIAR* para reagendar"
   - Y el usuario responde con: "Sí", "Si", "SÍ", "si", "confirmo", "sí confirmo", "si la confirmo", "claro", "por supuesto", "ok", "está bien", "perfecto", "de acuerdo"
   - ENTONCES el usuario está CONFIRMANDO su asistencia a la cita mencionada en ese mensaje
   - ACCIÓN INMEDIATA: USA la herramienta confirmar_cita SIN PREGUNTAR NADA MÁS
   - NO digas "no estoy segura de qué te refieres" - el contexto está en el historial
   - Si el usuario responde "NO", "no", "cancelar", "no puedo", "no podré" → usa cancelar_cita (pero primero pregunta el email)
   - Si el usuario responde "CAMBIAR", "cambiar", "reagendar", "modificar", "otra fecha" → usa modificar_cita (pero primero pregunta el email)

═══════════════════════════════════════════════════
INFORMACIÓN DEL NEGOCIO
═══════════════════════════════════════════════════

Nombre: {client.business_name}
Fecha actual: {dia_actual} {now.strftime("%d de %B de %Y")}
Hora actual: {now.strftime("%H:%M")}
"""

        # ==========================================
        # AGREGAR INFO SEGÚN TIPO DE NEGOCIO
        # ==========================================
        
        # Horario de atención
        if 'business_hours' in config:
            hours = config['business_hours']
            dias_trabajo = config.get('working_days', [1,2,3,4,5])
            dias_nombres = {1:'Lunes', 2:'Martes', 3:'Miércoles', 4:'Jueves', 5:'Viernes', 6:'Sábado', 7:'Domingo'}
            dias_str = ', '.join([dias_nombres.get(d, '') for d in dias_trabajo])
            base_system += f"""
Horario: {hours.get('start', '08:00')} - {hours.get('end', '18:00')}
Días de atención: {dias_str}
"""

        # Servicios (salón, clínica simple)
        if 'services' in config:
            currency = config.get('currency', '$')
            services_list = []
            for s in config['services']:
                services_list.append(f"  - {s['name']}: {currency}{s['price']:,}")
            base_system += f"""
Servicios y precios:
{chr(10).join(services_list)}
"""

        # Profesionales (clínica multi-doctor)
        if 'professionals' in config:
            profs_list = []
            for p in config['professionals']:
                profs_list.append(f"  - {p['name']} ({p.get('specialty', 'General')})")
            base_system += f"""
Profesionales disponibles:
{chr(10).join(profs_list)}
"""

        # Catálogo (tienda)
        if 'catalog' in config:
            cats = config['catalog'].get('categories', [])
            base_system += f"""
Categorías de productos: {', '.join([c['name'] for c in cats])}
"""
            if config.get('free_delivery_minimum'):
                base_system += f"Envío gratis en compras mayores a {config.get('currency', '$')}{config['free_delivery_minimum']:,}\n"

        # Teléfono de contacto
        if 'contact_phone' in config:
            base_system += f"Teléfono de contacto: {config['contact_phone']}\n"

        # ==========================================
        # INFORMACIÓN DEL CLIENTE (si existe)
        # ==========================================
        if customer:
            nombre_cliente = customer.full_name or "Cliente"
            base_system += f"""
═══════════════════════════════════════════════════
INFORMACIÓN DEL CLIENTE
═══════════════════════════════════════════════════
Nombre: {nombre_cliente}
Teléfono: {customer.phone_number}
"""
            if customer.data:
                for key, value in customer.data.items():
                    base_system += f"{key}: {value}\n"

        # ==========================================
        # INSTRUCCIONES SEGÚN TIPO DE NEGOCIO
        # ==========================================
        
        areas_restaurante = config.get('areas', ['Salón principal'])
        areas_str = ' / '.join(areas_restaurante) if isinstance(areas_restaurante, list) else areas_restaurante
        
        if business_type == 'salon':
            # Verificar si hay profesionales disponibles
            professionals_info = ""
            if config.get('professionals'):
                profs_names = [p['name'] for p in config['professionals']]
                professionals_info = f"""
PROFESIONALES DISPONIBLES:
- El salón tiene los siguientes profesionales: {', '.join(profs_names)}
- ⚠️ IMPORTANTE: SIEMPRE pregunta si el cliente quiere un profesional específico
- Si el cliente NO especifica profesional, puedes agendar sin profesional_id (usará calendario general)
- Si el cliente SÍ quiere un profesional específico, verifica disponibilidad con buscar_disponibilidad usando profesional_id
- Si preguntan "¿Miguel está disponible?" o "¿Matías está disponible?", usa ver_profesionales o buscar_disponibilidad para verificar
"""
            
            base_system += f"""
═══════════════════════════════════════════════════
INSTRUCCIONES ESPECÍFICAS - SALÓN DE BELLEZA
═══════════════════════════════════════════════════

FLUJO DE RESERVACIÓN:
1. Agradece el contacto cordialmente
2. Pregunta qué servicio desea (si no lo mencionó)
3. Recopila los siguientes datos UNO POR UNO (en este orden):
   • Nombre completo
   • ⚠️ Correo electrónico (OBLIGATORIO - pregunta DESDE EL PRINCIPIO, incluso si ya lo tienen guardado)
   • Servicio deseado
   • ⚠️ Profesional específico (SIEMPRE pregunta: "¿Te gustaría agendar con algún profesional en específico o con quien esté disponible?")
   • Fecha preferida
   • Hora preferida
4. Si el cliente quiere un profesional específico:
   - Verifica disponibilidad usando buscar_disponibilidad con profesional_id
   - Si está disponible, procede con crear_cita incluyendo profesional_id
   - Si NO está disponible, ofrece horarios alternativos o sugiere otro profesional
5. Si el cliente NO quiere profesional específico:
   - Procede con crear_cita SIN profesional_id (usará calendario general del salón)
6. Antes de confirmar, resume TODOS los datos incluyendo el correo y confirma: "Te enviaremos la confirmación a [correo]. ¿Confirmas?"
7. Al agendar, confirma explícitamente: "✅ Cita confirmada. Te enviamos la confirmación a [correo]"

CONSULTAS SOBRE PROFESIONALES:
- Si preguntan "¿Miguel está disponible?" o "¿[Nombre] está disponible?":
  → Usa ver_profesionales para mostrar información del profesional
  → Luego pregunta: "¿Te gustaría agendar una cita con [Nombre]?"
  → Si dicen sí, usa buscar_disponibilidad con profesional_id para ver horarios disponibles
- Si preguntan disponibilidad de múltiples profesionales:
  → Muestra información de todos y pregunta con cuál prefiere agendar

PARA MODIFICAR/CANCELAR:
- ⚠️ SIEMPRE pregunta el correo electrónico PRIMERO antes de modificar o cancelar
- Explica: "Para enviarte la confirmación, ¿me podrías proporcionar tu correo electrónico?"
- Busca la cita por fecha/hora/profesional que mencione, no necesitas ID
- Confirma: "Te enviaremos la confirmación de [modificación/cancelación] a [correo]"
{professionals_info}
- Al completar, confirma: "✅ [Acción] completada. Te enviamos la confirmación a [correo]"

PARA CONFIRMAR ASISTENCIA:
- Si el usuario responde "Sí", "Si", "confirmo", etc. a un mensaje de confirmación que enviaste
- USA confirmar_cita INMEDIATAMENTE - NO preguntes "¿de qué estás hablando?"
- El usuario está confirmando su asistencia a la cita más próxima

REGLAS:
- Ofrece los servicios SOLO si preguntan o es relevante
- Si no hay disponibilidad, ofrece alternativas cercanas
- Sé cálido/a y profesional
- Usa emojis con moderación (💇‍♀️ 💅 ✨)
"""

        elif business_type == 'clinic':
            # Verificar si hay múltiples profesionales
            professionals_info = ""
            if config.get('professionals') and len(config['professionals']) > 1:
                profs_names = [p['name'] for p in config['professionals']]
                professionals_info = f"""
PROFESIONALES DISPONIBLES:
- La clínica tiene {len(config['professionals'])} profesionales: {', '.join(profs_names)}
- ⚠️ IMPORTANTE: Si hay múltiples profesionales, SIEMPRE debes preguntar con cuál quieren agendar
- El profesional es OBLIGATORIO cuando hay múltiples opciones
- Si el cliente pregunta "¿qué doctores hay?" o "¿quién atiende?", usa ver_profesionales
- Si preguntan disponibilidad de un profesional específico, usa buscar_disponibilidad con profesional_id
- NO puedes agendar sin especificar profesional cuando hay múltiples profesionales disponibles
"""
            
            base_system += f"""
═══════════════════════════════════════════════════
INSTRUCCIONES ESPECÍFICAS - CLÍNICA/CONSULTORIO
═══════════════════════════════════════════════════

FLUJO DE CITA MÉDICA:
1. Agradece el contacto y pregunta en qué puedes ayudar
2. Recopila los siguientes datos UNO POR UNO (en este orden):
   • Nombre completo del paciente
   • ⚠️ Correo electrónico (OBLIGATORIO - pregunta DESDE EL PRINCIPIO, incluso si ya lo tienen guardado)
   • Tipo de consulta o especialidad requerida
   • ⚠️ Profesional/Doctor (OBLIGATORIO si hay múltiples profesionales - pregunta: "¿Con qué doctor te gustaría agendar?")
   • Fecha preferida
   • Hora preferida
   • Motivo breve de la consulta (opcional)
3. Si hay múltiples profesionales y el cliente NO especifica:
   → Muestra profesionales disponibles usando ver_profesionales
   → Pregunta: "¿Con cuál de nuestros profesionales te gustaría agendar?"
   → NO procedas sin saber el profesional específico
4. Antes de confirmar, resume TODOS los datos incluyendo el correo y confirma: "Te enviaremos la confirmación a [correo]. ¿Confirmas?"
5. Al agendar, confirma explícitamente: "✅ Cita confirmada con [Doctor]. Te enviamos la confirmación a [correo]"

CONSULTAS SOBRE PROFESIONALES:
- Si preguntan "¿qué doctores hay?" o "¿quién atiende?":
  → Usa ver_profesionales para mostrar todos los profesionales con sus especialidades y horarios
- Si preguntan "¿[Doctor] está disponible?":
  → Verifica disponibilidad usando buscar_disponibilidad con profesional_id
  → Muestra horarios disponibles
  → Pregunta si quiere agendar con ese doctor

PARA MODIFICAR/CANCELAR:
- ⚠️ SIEMPRE pregunta el correo electrónico PRIMERO antes de modificar o cancelar
- Explica: "Para enviarte la confirmación, ¿me podrías proporcionar tu correo electrónico?"
- Busca la cita por fecha/hora/profesional que mencione, no necesitas ID
- Confirma: "Te enviaremos la confirmación de [modificación/cancelación] a [correo]"
- Al completar, confirma: "✅ [Acción] completada. Te enviamos la confirmación a [correo]"

PARA CONFIRMAR ASISTENCIA:
- Si el usuario responde "Sí", "Si", "confirmo", etc. a un mensaje de confirmación que enviaste
- USA confirmar_cita INMEDIATAMENTE - NO preguntes "¿de qué estás hablando?"
- El usuario está confirmando su asistencia a la cita más próxima

REGLAS IMPORTANTES:
- NUNCA des consejos médicos, diagnósticos ni recetas
- Emergencias médicas → escala a humano INMEDIATAMENTE
- Sé empático y profesional
- Si hay síntomas urgentes, recomienda acudir a emergencias
- Usa emojis mínimos (🏥 📋 ✅)
{professionals_info}
"""

        elif business_type == 'store':
            # Verificar si hay catálogo configurado
            catalog_info = ""
            if config.get('catalog'):
                categories = config['catalog'].get('categories', [])
                if categories:
                    cat_names = [c['name'] for c in categories]
                    catalog_info = f"""
CATÁLOGO DE PRODUCTOS:
- Categorías disponibles: {', '.join(cat_names)}
- Si el cliente pregunta por productos, usa ver_servicios para mostrar el catálogo
- Puedes filtrar por categoría si el cliente pregunta por algo específico
"""
            
            base_system += f"""
═══════════════════════════════════════════════════
INSTRUCCIONES ESPECÍFICAS - TIENDA/VENTAS
═══════════════════════════════════════════════════

TU PRINCIPAL FUNCIÓN:
- Responder preguntas sobre productos del catálogo
- Ayudar a encontrar productos específicos
- Agendar entregas cuando el cliente quiere comprar (pago contra entrega)

FLUJO DE CONSULTA DE PRODUCTOS:
1. Cliente pregunta por un producto o categoría
2. Usa ver_servicios para mostrar productos disponibles
3. Si pregunta por categoría específica, filtra por categoría
4. Muestra precios, descripciones y disponibilidad

FLUJO DE COMPRA/ENTREGA:
1. Cliente muestra interés en comprar un producto
2. Pregunta: "¿Te gustaría que te lo llevemos a domicilio? Es pago contra entrega"
3. Si acepta, recopila UNO POR UNO (en este orden):
   • Nombre completo
   • ⚠️ Correo electrónico (OBLIGATORIO - pregunta DESDE EL PRINCIPIO)
   • Producto(s) que quiere comprar
   • Dirección completa de entrega
   • Fecha preferida de entrega
   • Hora preferida (horario de entregas)
   • Teléfono de contacto (ya lo tienes, pero confirma)
4. Antes de confirmar, resume pedido con total y confirma: "Te enviaremos la confirmación a [correo]. ¿Confirmas?"
5. Al confirmar, confirma explícitamente: "✅ Entrega agendada. Te enviamos la confirmación a [correo]. El pago será contra entrega."

IMPORTANTE SOBRE ENTREGAS:
- Las entregas se agendan en el calendario de rutas/entregas
- El pago es CONTRA ENTREGA (no se cobra antes)
- Menciona esto claramente: "El pago será contra entrega cuando recibas el producto"
- La entrega se programa según las rutas disponibles

PARA MODIFICAR/CANCELAR ENTREGA:
- ⚠️ SIEMPRE pregunta el correo electrónico PRIMERO antes de modificar o cancelar
- Explica: "Para enviarte la confirmación, ¿me podrías proporcionar tu correo electrónico?"
- Busca la entrega por fecha/hora/producto que mencione
- Confirma: "Te enviaremos la confirmación de [modificación/cancelación] a [correo]"

REGLAS:
- Responde preguntas sobre productos usando ver_servicios
- Ayuda al cliente a encontrar lo que necesita en el catálogo
- Menciona promociones o envío gratis si aplica
- Si preguntan por financiamiento detallado o métodos de pago complejos → escala a humano
- NO agendes entregas sin que el cliente exprese interés en comprar
- Usa emojis moderados (📦 🚚 ✨)
{catalog_info}
"""

        elif business_type == 'restaurant':
            base_system += f"""
═══════════════════════════════════════════════════
INSTRUCCIONES ESPECÍFICAS - RESTAURANTE
═══════════════════════════════════════════════════

¡Gracias por comunicarte con {client.business_name}! 🍽️✨
Este es el contacto para reservaciones.

FLUJO DE RESERVACIÓN:
1. Agradece el contacto cordialmente
2. Recopila los siguientes datos UNO POR UNO (en este orden, no todos de golpe):
   • Nombre y apellido
   • ⚠️ Correo electrónico (OBLIGATORIO - pregunta DESDE EL PRINCIPIO, incluso si ya lo tienen guardado)
   • Cantidad de invitados
   • Fecha de la reservación
   • Hora preferida
   • Área preferida ({areas_str})
   • Ocasión especial (cumpleaños, aniversario, etc.) - opcional
3. Antes de confirmar, resume TODOS los datos incluyendo el correo y confirma: "Te enviaremos la confirmación a [correo]. ¿Confirmas?"
4. Al confirmar la reserva, confirma explícitamente: "✅ Reservación confirmada. Te enviamos la confirmación a [correo]"

PARA MODIFICAR/CANCELAR:
- ⚠️ SIEMPRE pregunta el correo electrónico PRIMERO antes de modificar o cancelar
- Explica: "Para enviarte la confirmación, ¿me podrías proporcionar tu correo electrónico?"
- Busca la reservación por fecha/hora que mencione, no necesitas ID
- Confirma: "Te enviaremos la confirmación de [modificación/cancelación] a [correo]"
- Al completar, confirma: "✅ [Acción] completada. Te enviamos la confirmación a [correo]"

REGLAS:
- Grupos grandes (8+ personas) → escala a humano
- Sé cordial y elegante en el trato
- Usa emojis con elegancia (🍽️ ✨ 🥂)
- Agradece siempre por preferir el restaurante
- Si no hay disponibilidad, ofrece horarios alternativos
"""

        # ==========================================
        # CÁLCULO DE FECHAS RELATIVAS
        # ==========================================
        hoy = now.date()
        manana = hoy + timedelta(days=1)
        pasado_manana = hoy + timedelta(days=2)
        
        # Calcular próximos días de la semana
        dias_semana_es = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
        proximos_dias = {}
        for i in range(1, 8):
            fecha_futura = hoy + timedelta(days=i)
            dia_nombre = dias_semana_es[fecha_futura.weekday()]
            if dia_nombre not in proximos_dias:
                proximos_dias[dia_nombre] = fecha_futura.strftime("%Y-%m-%d")
        
        # ==========================================
        # INSTRUCCIONES TÉCNICAS (invisibles al usuario)
        # ==========================================
        base_system += f"""
═══════════════════════════════════════════════════
INSTRUCCIONES TÉCNICAS (NO MENCIONAR AL USUARIO)
═══════════════════════════════════════════════════

⚠️ FECHAS - MUY IMPORTANTE ⚠️
Hoy es: {hoy.strftime("%Y-%m-%d")} ({dia_actual})
Mañana es: {manana.strftime("%Y-%m-%d")}
Pasado mañana es: {pasado_manana.strftime("%Y-%m-%d")}

Próximos días de la semana:
- Próximo lunes: {proximos_dias.get('lunes', 'N/A')}
- Próximo martes: {proximos_dias.get('martes', 'N/A')}
- Próximo miércoles: {proximos_dias.get('miércoles', 'N/A')}
- Próximo jueves: {proximos_dias.get('jueves', 'N/A')}
- Próximo viernes: {proximos_dias.get('viernes', 'N/A')}
- Próximo sábado: {proximos_dias.get('sábado', 'N/A')}
- Próximo domingo: {proximos_dias.get('domingo', 'N/A')}

⚠️ REGLAS CRÍTICAS DE FECHAS Y HORAS ⚠️

CUANDO EL USUARIO MENCIONA FECHAS RELATIVAS, DEBES CONVERTIRLAS INMEDIATAMENTE:
- "mañana" = {manana.strftime("%Y-%m-%d")} ← USA ESTA FECHA DIRECTAMENTE
- "pasado mañana" = {pasado_manana.strftime("%Y-%m-%d")}
- "el lunes" = {proximos_dias.get('lunes', 'N/A')}
- "el martes" = {proximos_dias.get('martes', 'N/A')}
- "el miércoles" = {proximos_dias.get('miércoles', 'N/A')}
- "el jueves" = {proximos_dias.get('jueves', 'N/A')}
- "el viernes" = {proximos_dias.get('viernes', 'N/A')}
- "el sábado" = {proximos_dias.get('sábado', 'N/A')}
- "el domingo" = {proximos_dias.get('domingo', 'N/A')}

CONVERSIÓN DE HORAS (24 horas):
- "11 de la mañana" / "11 am" / "11:00 am" = 11:00
- "3 de la tarde" / "3 pm" = 15:00
- "8 de la noche" / "8 pm" = 20:00
- "medio día" / "12 pm" = 12:00

🚫 PROHIBIDO:
- NO preguntes "¿qué día es mañana?" - YA LO SABES: es {manana.strftime("%Y-%m-%d")}
- NO pidas formato específico de fecha si el usuario ya dijo "mañana", "el sábado", etc.
- NO uses años anteriores a {hoy.year}
- NO inventes fechas - usa SOLO las calculadas arriba

✅ CORRECTO:
Si el usuario dice "quiero cita para mañana a las 11 de la mañana":
→ Usa buscar_disponibilidad con fecha={manana.strftime("%Y-%m-%d")}, hora=11:00
→ O usa crear_cita con fecha={manana.strftime("%Y-%m-%d")}, hora=11:00

HERRAMIENTAS (no mencionar al usuario):
- buscar_disponibilidad: para ver horarios libres
- crear_cita: para agendar
- ver_mis_citas: para listar citas del cliente (USA cuando pregunten por sus citas/reservas)
- confirmar_cita: para confirmar asistencia cuando el usuario responde "Sí" a un mensaje de confirmación
- cancelar_cita: para cancelar
- modificar_cita: para reagendar
- guardar_datos_usuario: para guardar info del cliente
- escalar_a_humano: para emergencias/quejas

Formato WhatsApp: *negrita* _cursiva_

PROMPT PERSONALIZADO DEL NEGOCIO:
{client.system_prompt_template}
"""
        
        return base_system
    
    async def chat_with_tools(
        self,
        message: str,
        history: list[dict],
        client: Client,
        customer: Customer
    ) -> str:
        """
        Genera una respuesta usando Gemini con Function Calling.
        
        Args:
            message: Mensaje del usuario
            history: Historial de conversación
            client: El Client para obtener configuración
            customer: El Customer para personalización y tools
            
        Returns:
            Respuesta final después de ejecutar tools si es necesario
        """
        try:
            # Import aquí para evitar circular import
            from app.agents.tools.definitions import TOOL_DEFINITIONS, ToolExecutor
            
            # Validar customer
            if not customer or not customer.id:
                logger.error("Customer inválido en chat_with_tools")
                return "No pude identificar tu información. Por favor intenta de nuevo."
            
            system_prompt = self.build_system_prompt(client, customer)
            tool_executor = ToolExecutor(client, customer)
            
            # Construir contenido del chat
            contents = []
            
            # Agregar historial (ya viene formateado de get_context_for_llm)
            for msg in history:
                try:
                    role = msg.get("role", "user")
                    parts = msg.get("parts", [])
                    if parts:
                        text = parts[0].get("text", "") if isinstance(parts[0], dict) else str(parts[0])
                        if text and text.strip():
                            contents.append(
                                types.Content(
                                    role=role,
                                    parts=[types.Part.from_text(text=text[:10000])]  # Limitar longitud
                                )
                            )
                except Exception:
                    continue  # Saltar mensajes problemáticos
            
            # Agregar mensaje actual del usuario
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=message)]
                )
            )
            
            # Generar respuesta con tools Y system_instruction
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                    top_p=0.95,
                    max_output_tokens=1024,
                    tools=TOOL_DEFINITIONS,
                )
            )
            
            # Procesar respuesta
            final_response = await self._process_response(
                response, 
                contents, 
                tool_executor
            )
            
            return self._clean_response(final_response)
            
        except Exception as e:
            logger.error(f"Error en Gemini: {e}", exc_info=True)
            return "Lo siento, tuve un problema procesando tu mensaje. ¿Podrías intentarlo de nuevo?"
    
    async def _process_response(
        self,
        response,
        contents: list,
        tool_executor,
        depth: int = 0
    ) -> str:
        """
        Procesa la respuesta de Gemini, ejecutando tools si es necesario.
        """
        if depth > 5:  # Prevenir loops infinitos
            return "He alcanzado el límite de operaciones. Por favor intenta de nuevo."
        
        # Verificar si hay candidatos
        if not response.candidates:
            logger.warning("No candidates in response")
            return "Lo siento, no pude procesar tu solicitud. ¿Podrías reformularla?"
        
        candidate = response.candidates[0]
        
        # Verificar si hay contenido
        if candidate.content and candidate.content.parts:
            text_response = None
            function_call_part = None
            
            # Primero recolectar texto y function calls
            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text:
                    text_response = part.text
                
                if hasattr(part, 'function_call') and part.function_call:
                    function_call_part = part.function_call
            
            # PRIORIZAR function calls sobre texto
            if function_call_part:
                fc = function_call_part
                function_name = fc.name
                function_args = dict(fc.args) if fc.args else {}
                
                # Ejecutar la herramienta
                result = await tool_executor.execute(function_name, function_args)
                
                # Agregar el function call y resultado al contexto
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part.from_function_call(
                            name=function_name,
                            args=function_args
                        )]
                    )
                )
                
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_function_response(
                            name=function_name,
                            response={"result": result}
                        )]
                    )
                )
                
                # Continuar la conversación con el resultado
                from app.agents.tools.definitions import TOOL_DEFINITIONS as TOOLS
                new_response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=1024,
                        tools=TOOLS,
                    )
                )
                
                # Procesar recursivamente
                return await self._process_response(
                    new_response, 
                    contents, 
                    tool_executor,
                    depth + 1
                )
            
            # Si solo hay texto (sin function call), retornarlo
            if text_response:
                return text_response
        
        # Si no hay partes, intentar extraer texto directamente
        if hasattr(response, 'text') and response.text:
            return response.text
        
        logger.warning("No content found in response")
        return "Lo siento, no pude procesar tu solicitud. ¿Podrías intentarlo de nuevo?"
    
    async def chat_simple(
        self,
        message: str,
        system_prompt: str
    ) -> str:
        """
        Chat simple sin historial ni tools.
        """
        try:
            full_prompt = f"{system_prompt}\n\nUsuario: {message}"
            
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=1024,
                )
            )
            
            return self._clean_response(response.text)
            
        except Exception as e:
            logger.error(f"Error en chat_simple: {e}", exc_info=True)
            return "Error procesando el mensaje."
    
    # Alias para compatibilidad
    async def chat(
        self,
        message: str,
        history: list[dict],
        client: Client,
        customer: Customer | None = None
    ) -> str:
        """Alias que usa chat_with_tools si hay customer."""
        if customer:
            return await self.chat_with_tools(message, history, client, customer)
        else:
            # Fallback sin tools
            return await self.chat_simple(
                message, 
                self.build_system_prompt(client, customer)
            )
    
    def _clean_response(self, text: str) -> str:
        """Limpia la respuesta para WhatsApp."""
        if not text:
            return ""
        
        text = text.replace("**", "*")
        text = text.replace("```", "")
        
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            if line.startswith('#'):
                line = '*' + line.lstrip('#').strip() + '*'
            cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)
        
        return text.strip()


# Instancia global
gemini_service = GeminiService()
