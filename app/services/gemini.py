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

        # Servicios (negocio con servicios + citas, clínica simple)
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
            # Negocio con servicios + citas (detailing, taller, spa, centro de servicios, etc.). Profesionales opcionales.
            professionals_info = ""
            if config.get('professionals'):
                profs_names = [p['name'] for p in config['professionals']]
                professionals_info = f"""
PROFESIONALES/ATENDENTES DISPONIBLES:
- El negocio tiene los siguientes: {', '.join(profs_names)}
- Si hay más de uno: pregunta si quieren un profesional específico o con quien esté disponible
- Si el cliente NO especifica, puedes agendar sin profesional_id (calendario general)
- Si SÍ quieren uno específico, verifica disponibilidad con buscar_disponibilidad (profesional_id)
- Si preguntan "¿[Nombre] está disponible?", usa ver_profesionales o buscar_disponibilidad
"""
            
            base_system += f"""
═══════════════════════════════════════════════════
INSTRUCCIONES - NEGOCIO CON SERVICIOS Y CITAS
═══════════════════════════════════════════════════
(Cualquier negocio con servicios y citas: detailing, taller, spa, centro de servicios, etc.)

FLUJO DE RESERVACIÓN:
1. Agradece el contacto cordialmente
2. Pregunta qué servicio desea (si no lo mencionó). Si preguntan precios o catálogo, usa ver_servicios
3. Recopila UNO POR UNO (en este orden):
   • Nombre completo
   • ⚠️ Correo electrónico (OBLIGATORIO - pregunta DESDE EL PRINCIPIO)
   • Servicio deseado
   • Si hay profesionales: "¿Con alguien en específico o con quien esté disponible?" (si solo hay uno, omite o confirma)
   • Fecha preferida
   • Hora preferida
4. Si quieren profesional específico: buscar_disponibilidad con profesional_id → crear_cita con profesional_id
5. Si no: crear_cita SIN profesional_id (calendario general)
6. Antes de confirmar, resume datos y correo: "Te enviaremos la confirmación a [correo]. ¿Confirmas?"
7. Al agendar: "✅ Cita confirmada. Te enviamos la confirmación a [correo]"

CONSULTAS SOBRE PROFESIONALES:
- "¿[Nombre] está disponible?" → ver_profesionales y/o buscar_disponibilidad, luego ofrecer agendar
{professionals_info}

MODIFICAR/CANCELAR:
- ⚠️ Pregunta correo PRIMERO. Busca cita por fecha/hora/profesional. Confirma envío de confirmación a [correo]

CONFIRMAR ASISTENCIA:
- Si responden "Sí", "confirmo", etc. a tu mensaje de confirmación → usa confirmar_cita de inmediato

REGLAS:
- Muestra servicios solo si preguntan o es relevante (ver_servicios)
- Sin disponibilidad → ofrece alternativas. Sé profesional. Emojis con moderación (📅 ✅ ⏱️)
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
            # Tienda / concesionario / dealer: catálogo, sin citas obligatorias. Puede ser solo info + "pásate cuando quieras"
            catalog_info = ""
            if config.get('catalog_source') == 'pdf':
                catalog_info = """
CATÁLOGO (PDF):
- El catálogo del negocio está en un documento PDF. Cuando pregunten por productos, precios, qué tienen, cuánto cuesta X, etc., usa ver_servicios y pasa en el parámetro "pregunta" exactamente lo que el usuario preguntó (ej. "¿Qué colchones tienen?", "precios de almohadas", "cuánto cuesta el modelo Y"). La IA responderá basándose en el PDF.
"""
            elif config.get('catalog'):
                categories = config['catalog'].get('categories', [])
                if categories:
                    cat_names = [c['name'] for c in categories]
                    catalog_info = f"""
CATÁLOGO:
- Categorías: {', '.join(cat_names)}
- Preguntas por productos/modelos → usa ver_servicios (puedes filtrar por categoría)
"""
            # Si tiene calendar_id, el negocio ofrece entrega a domicilio (pago contra entrega); si no, solo catálogo y visita
            delivery_info = ""
            if config.get('calendar_id'):
                delivery_info = """
ENTREGA A DOMICILIO (PAGO CONTRA ENTREGA):
- Este negocio SÍ ofrece entrega a domicilio con pago contra entrega.
- Cuando muestres el catálogo o pregunten por productos, puedes mencionar brevemente: "Todos nuestros productos están disponibles con entrega a domicilio (pago contra entrega). ¿Te gustaría ver opciones o agendar una entrega?"
- Si preguntan "¿hacen envíos?", "¿entregan?", "¿pago contra entrega?": responde que sí y ofrece agendar la entrega (nombre, correo, producto, dirección, fecha/hora).
"""
            else:
                delivery_info = """
ENTREGA A DOMICILIO:
- Este negocio NO tiene entregas a domicilio configuradas. Solo ofrece catálogo y visita al local.
- No ofrezcas agendar entrega. Si preguntan por envíos, indica que pueden pasar al local según horarios de atención.
"""
            
            base_system += f"""
═══════════════════════════════════════════════════
INSTRUCCIONES - TIENDA / CATÁLOGO (SIN CITAS OBLIGATORIAS)
═══════════════════════════════════════════════════
(Tienda, concesionario, colchonería, etc.: mostrar catálogo; visitas sin cita; entregas opcionales con pago contra entrega)

TU PRINCIPAL FUNCIÓN:
- Responder preguntas sobre productos del catálogo (ver_servicios). Los productos están disponibles; si el negocio tiene entregas, también a domicilio con pago contra entrega.
- Si el negocio es de visita física: el cliente puede decir que va a pasar. Responde con horarios y "Puedes pasar cuando quieras", "Te esperamos". NO obligues a agendar solo para informarse o ir a ver.
- Si el negocio ofrece entrega a domicilio: menciónalo al mostrar catálogo y ofrece agendar entrega cuando quieran comprar (pago contra entrega).
{delivery_info}

CONSULTA DE PRODUCTOS:
1. Cliente pregunta por producto, categoría, precios
2. Usa ver_servicios para mostrar opciones, precios, descripciones
3. Si tiene entregas: opcionalmente añade que están disponibles con entrega a domicilio (pago contra entrega)

FLUJO DE COMPRA/ENTREGA (cuando el negocio tiene entregas y el cliente quiere entrega):
1. Cliente muestra interés en comprar y quiere entrega a domicilio
2. Recopila: nombre, correo, producto(s), dirección, fecha/hora entrega
3. Confirma: "Te enviaremos la confirmación a [correo]. Pago contra entrega."
4. NO agendes entrega si solo piden información o ir a ver al local

MODIFICAR/CANCELAR ENTREGA:
- Pregunta correo primero. Busca por fecha/producto. Confirma envío de confirmación

REGLAS:
- Catálogo con ver_servicios. Visitas sin cita: horarios + "puedes pasar cuando quieras" si aplica
- Financiamiento o pagos complejos → escala a humano. Emojis moderados (📦 🚚 ✅)
{catalog_info}
"""

        elif business_type == 'general':
            base_system += """
═══════════════════════════════════════════════════
INSTRUCCIONES - NEGOCIO GENÉRICO (CITAS BÁSICAS)
═══════════════════════════════════════════════════
Este negocio solo ofrece citas básicas. No hay listado de servicios ni profesionales.

FLUJO:
1. Recopila: nombre completo, correo electrónico (OBLIGATORIO), fecha preferida, hora preferida
2. Usa buscar_disponibilidad para la fecha y luego crear_cita con los datos
3. No preguntes por "servicio" ni "profesional" - no aplican
4. Confirma: "Te enviaremos la confirmación a [correo]. ¿Confirmas?"
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
            text_parts = []
            function_call_part = None
            
            # Recolectar todo el texto de las parts (a veces hay varias) y function calls
            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text and part.text.strip():
                    text_parts.append(part.text.strip())
                if hasattr(part, 'function_call') and part.function_call:
                    function_call_part = part.function_call
            
            text_response = " ".join(text_parts) if text_parts else None
            
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
        
        # Si no hay partes, intentar extraer texto directamente del response
        if hasattr(response, 'text') and response.text and response.text.strip():
            return response.text.strip()
        
        # Último recurso: intentar de candidate.content.parts por si no entró arriba
        if response.candidates:
            c0 = response.candidates[0]
            if c0.content and c0.content.parts:
                texts = []
                for p in c0.content.parts:
                    if getattr(p, 'text', None) and str(p.text).strip():
                        texts.append(str(p.text).strip())
                if texts:
                    return " ".join(texts)
            if getattr(c0, 'finish_reason', None):
                logger.debug(f"Gemini finish_reason: {c0.finish_reason}")
        
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

    async def answer_from_context(self, context: str, question: str) -> str:
        """
        Responde una pregunta del usuario basándose solo en el contexto (ej. texto
        extraído del catálogo PDF). Para clientes con catalog_source=pdf.
        """
        if not context or not context.strip():
            return "No tengo el catálogo disponible en este momento. ¿Quieres que te cuente horarios o que un asesor te contacte?"
        if not question or not question.strip():
            question = "Lista todos los productos, servicios, precios y descripciones del catálogo de forma clara y útil para el cliente."
        try:
            system = (
                "Eres un asistente que responde ÚNICAMENTE basándote en el contexto (catálogo del negocio) que te proporciono. "
                "Responde en español, de forma breve y útil para WhatsApp. "
                "Si la información no está en el contexto, dilo amablemente y ofrece alternativas (horarios, contacto). "
                "Para listas de productos o precios usa *negrita* para nombres y montos. "
                "No inventes datos que no aparezcan en el contexto."
            )
            user_content = f"Contexto (catálogo del negocio):\n\n{context[:300000]}\n\n---\nPregunta del cliente: {question}"
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=user_content)]
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.3,
                    max_output_tokens=1024,
                )
            )
            if not response.text or not response.text.strip():
                return "No pude generar una respuesta del catálogo. ¿Quieres que te cuente horarios o que un asesor te contacte?"
            return self._clean_response(response.text.strip())
        except Exception as e:
            logger.error(f"Error en answer_from_context: {e}", exc_info=True)
            return "Tuve un problema al consultar el catálogo. ¿Podrías intentar de nuevo o pedir horarios/contacto?"

    async def extract_text_from_pdf(self, pdf_bytes: bytes) -> str | None:
        """
        Extrae todo el texto de un PDF con Gemini (multimodal).
        Sirve para PDFs nativos y para escaneados/imágenes.
        """
        if not pdf_bytes or len(pdf_bytes) < 100:
            return None
        # Limitar tamaño para evitar timeouts/costes (ej. 15 MB)
        if len(pdf_bytes) > 15 * 1024 * 1024:
            logger.warning("PDF demasiado grande para extracción con Gemini (>15MB)")
            return None
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(
                                data=pdf_bytes,
                                mime_type="application/pdf",
                            ),
                            types.Part.from_text(
                                text=(
                                    "Extrae TODO el texto de este documento PDF de forma literal. "
                                    "Preserva la estructura: títulos, listas, precios, nombres de productos/servicios. "
                                    "Responde ÚNICAMENTE con el texto extraído, sin comentarios ni explicaciones."
                                )
                            ),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                )
            )
            if not response.text or not response.text.strip():
                return None
            return response.text.strip()
        except Exception as e:
            logger.warning("Error extrayendo texto del PDF con Gemini: %s", e)
            return None

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
