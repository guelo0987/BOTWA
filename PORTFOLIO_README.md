# 🤖 DLC Bot — WhatsApp AI Assistant Platform

## Para el equipo de Frontend / Portafolio

Este documento describe **todas las funcionalidades** de la plataforma DLC Bot para que el equipo de frontend pueda diseñar y construir las secciones del portafolio/landing page. Cada sección incluye una breve explicación de la funcionalidad, qué mostrar visualmente y sugerencias de contenido.

---

## 🎯 Visión General (Hero Section)

**Qué es:** Una plataforma SaaS de asistentes virtuales por WhatsApp potenciados con Inteligencia Artificial (Google Gemini). Cada negocio recibe su propio bot personalizado que atiende clientes 24/7, agenda citas, responde preguntas y escala a humanos cuando es necesario.

**Puntos clave para el Hero:**
- "Tu negocio, atendido 24/7 por IA"
- Compatible con WhatsApp Business API (Meta)
- Powered by Google Gemini AI
- Multi-inquilino: un solo servidor, múltiples negocios

---

## 🏢 Arquitectura Multi-Inquilino (Multi-Tenant)

**Qué es:** Un solo servidor maneja múltiples negocios simultáneamente. Cada empresa tiene su propia personalidad, configuración, catálogo y credenciales de WhatsApp completamente aislados.

**Qué mostrar:**
- Diagrama visual con un servidor central conectado a múltiples negocios (Clínica, Restaurante, Tienda, Salón, etc.)
- Cada negocio tiene su propio número de WhatsApp, logo, colores y personalidad
- Los datos de clientes están 100% aislados entre negocios

**Ejemplo de copy:**
> "Un restaurante en Santo Domingo y una clínica en Santiago comparten la misma infraestructura, pero cada uno tiene su propia personalidad, catálogo y base de clientes. Cero interferencia."

---

## 🧠 Inteligencia Artificial Conversacional

**Qué es:** El bot usa Google Gemini (modelo de última generación) para mantener conversaciones naturales, entender contexto, y decidir automáticamente cuándo usar herramientas internas (agendar citas, buscar disponibilidad, etc.).

**Qué mostrar:**
- Mockup de conversación de WhatsApp donde el bot responde naturalmente
- Ejemplo: cliente pregunta por servicios → bot muestra catálogo → cliente agenda cita → bot confirma
- Mostrar que entiende mensajes de voz, texto, imágenes y documentos

**Capacidades clave:**
- Conversaciones naturales en español (adaptable a cualquier idioma)
- Memoria de contexto configurable (recuerda la conversación completa)
- Personalidad 100% personalizable por negocio (tono formal, casual, técnico, etc.)
- Function Calling: la IA decide automáticamente qué herramienta usar sin intervención humana

---

## 🎙️ Procesamiento Multimedia

**Qué es:** El bot no solo entiende texto. Procesa audios, imágenes y documentos enviados por los clientes vía WhatsApp.

**Qué mostrar (por cada tipo):**

### 🔊 Notas de Voz
- El cliente envía un audio → Gemini lo transcribe → el bot responde como si fuera texto
- Mockup de conversación con burbuja de audio y respuesta del bot

### 📸 Análisis de Imágenes
- El cliente envía una foto de un producto → el bot la analiza y responde con contexto del negocio
- Ejemplo: foto de un colchón → "¡Ese es nuestro modelo OrthoPlus! Precio: RD$12,500"

### 📄 Documentos / PDFs
- El cliente envía un PDF → Gemini extrae el texto y responde basándose en el contenido
- Útil para recibir recetas médicas, formularios, etc.

---

## 📋 Catálogo Inteligente por PDF

**Qué es:** Los negocios suben su catálogo de productos/servicios como un PDF a Supabase Storage. El bot lo lee con IA multimodal (Gemini Vision), extrae todos los servicios, precios y detalles, y responde preguntas basándose en ese catálogo.

**Qué mostrar:**
- Flujo visual: PDF subido → IA lo lee → Bot responde preguntas del catálogo
- Ejemplo: "¿Cuánto cuesta el servicio X?" → Bot responde con precio exacto del PDF
- Se cachea inteligentemente para no re-procesarlo cada vez (TTL configurable)

---

## 📅 Sistema de Citas y Reservaciones

**Qué es:** Integración directa con Google Calendar. El bot puede buscar disponibilidad, crear citas, modificarlas y cancelarlas, todo desde la conversación de WhatsApp.

**Qué mostrar:**
- Flujo completo de agendamiento: Buscar disponibilidad → Elegir hora → Confirmar → Cita creada
- Mockup de conversación mostrando cada paso
- Vista del evento creado en Google Calendar

**Funcionalidades específicas:**
| Acción | Descripción |
|---|---|
| 🔍 Buscar disponibilidad | Muestra slots libres por día, filtrando por profesional |
| ➕ Crear cita | Bloquea el horario en Google Calendar y registra en la BD |
| 🔄 Modificar cita | Cambia fecha/hora de una cita existente |
| ❌ Cancelar cita | Cancela en Calendar y en la BD, envía email de cancelación |
| 📋 Ver mis citas | Lista las citas futuras del cliente |
| ✅ Confirmar asistencia | El cliente confirma que asistirá |

---

## 🏪 Tipos de Negocio Soportados

**Qué es:** El bot se adapta inteligentemente al tipo de negocio. Cada tipo tiene su propio flujo, vocabulario y herramientas especializadas.

**Qué mostrar:** Una sección tipo "tabs" o carrusel con cada tipo:

### 🏥 Clínicas y Consultorios
- Citas médicas con selección de profesional obligatoria
- Múltiples doctores con calendarios independientes
- Recomendaciones pre-consulta en emails

### 💈 Salones y Servicios Profesionales
- Citas con o sin profesional específico
- Catálogo de servicios con precios
- Ideal para: abogados, contadores, consultores, estéticas

### 🍽️ Restaurantes
- Reservaciones con número de personas
- Selección de área (terraza, salón, barra)
- Ocasiones especiales (cumpleaños, aniversario)

### 🛒 Tiendas y E-Commerce
- Programación de entregas
- Dirección de entrega del cliente
- Seguimiento de pedidos

### 🌐 General
- Configuración flexible para cualquier otro tipo de negocio
- Funcionalidades básicas de conversación e información

---

## 🚨 Escalación a Agente Humano

**Qué es:** Cuando el cliente quiere hablar con una persona real, el bot pausa la IA automáticamente y notifica al dueño del negocio por correo electrónico. El humano responde directamente desde WhatsApp Business Suite.

**Qué mostrar:**
- Flujo visual: Cliente pide humano → Bot pausa IA → Email al dueño → Humano responde → Se devuelve control a la IA
- Mockup del email de escalación (plantilla roja/urgente)
- Datos incluidos: nombre del cliente, teléfono, motivo, resumen de la conversación

---

## 📧 Sistema de Emails Transaccionales

**Qué es:** El bot envía correos automáticos usando la API de Resend. Los correos son HTML responsive con el logo y colores del negocio.

**Tipos de correos (mostrar mockup de cada uno):**

| Correo | Cuándo se envía | Destinatario |
|---|---|---|
| ✅ Confirmación de cita | Al agendar/modificar/cancelar una cita | Cliente |
| ⏰ Recordatorio 24h | 24 horas antes de la cita (automático) | Cliente |
| 📩 Confirmación 48h | 48 horas antes pidiendo confirmar asistencia | Cliente |
| 💬 Nueva conversación | Cuando un cliente nuevo escribe por primera vez | Dueño del negocio |
| 🚨 Escalación a humano | Cuando un cliente pide hablar con un agente | Dueño del negocio |

**Personalización:**
- Logo del negocio (desde Supabase Storage)
- Colores primarios y secundarios
- Texto del pie de página
- Templates de asunto y contenido personalizables por cliente

---

## 🖥️ Panel de Administración

**Qué es:** Un dashboard web separado donde los dueños de negocios pueden configurar su bot, ver estadísticas y gestionar su catálogo.

**Funcionalidades del panel:**
- Gestionar datos del negocio (nombre, tipo, personalidad del bot)
- Configurar credenciales de WhatsApp
- Subir/actualizar catálogo PDF
- Configurar email de notificaciones
- Personalizar colores y logo de los correos
- Ver historial de citas y clientes
- Activar/desactivar el bot (interruptor de pago)

---

## ⏰ Recordatorios Automáticos

**Qué es:** Un sistema de tareas programadas que corre en segundo plano y envía emails automáticos a los clientes antes de sus citas, sin intervención humana.

**Qué mostrar:**
- Timeline visual: Cita creada → 48h antes (confirmación) → 24h antes (recordatorio) → Día de la cita
- Los correos se personalizan con el logo y colores del negocio

---

## 🔒 Seguridad y Privacidad

**Qué mostrar como badges/íconos:**
- Verificación de firmas de webhook (App Secret por negocio)
- Datos aislados por inquilino (multi-tenant seguro)
- Credenciales encriptadas en variables de entorno
- Usuario no-root en contenedores Docker
- Conexiones a base de datos con SSL

---

## ⚡ Stack Tecnológico

**Mostrar como íconos/logos:**

| Capa | Tecnología |
|---|---|
| IA | Google Gemini (gemini-2.5-flash) |
| Backend | Python + FastAPI (async) |
| Base de Datos | PostgreSQL (Neon Serverless) |
| Cache/Sesiones | Redis (Upstash Serverless) |
| Almacenamiento | Supabase Storage (S3) |
| Emails | Resend API |
| Calendario | Google Calendar API |
| Mensajería | WhatsApp Business API (Meta) |
| Hosting | Render (Docker) |
| CI/CD | GitHub → Auto-deploy |

---

## 📊 Métricas / Números para el Portafolio

**Sugerencias de datos a destacar:**
- Tiempo de respuesta promedio: < 5 segundos
- Disponibilidad: 24/7/365
- Tipos de negocio soportados: 5+
- Tipos de media procesados: Texto, Audio, Imágenes, PDFs
- Emails automáticos: 5 tipos diferentes
- Herramientas de IA: 8 (ver servicios, buscar disponibilidad, crear cita, modificar, cancelar, ver citas, guardar datos, escalar a humano)

---

## 🎨 Sugerencias de Diseño

- **Estilo:** Dark mode con acentos en verde WhatsApp (#25D366) y azul IA
- **Animaciones:** Simular burbujas de chat de WhatsApp apareciendo en secuencia
- **Screenshots:** Mockups reales de conversaciones del bot en acción
- **Demo interactiva:** Considerar un mini-chat embebido que simule una conversación
- **Video:** Grabación de pantalla de una conversación real con el bot

---

## 📁 Estructura del Proyecto (Referencia Técnica)

```
COMPLETEAGENT/
├── app/
│   ├── main.py                    # Punto de entrada FastAPI
│   ├── core/
│   │   ├── config.py              # Variables de entorno
│   │   ├── database.py            # PostgreSQL (SQLAlchemy async)
│   │   └── redis.py               # Redis (sesiones + memoria)
│   ├── models/
│   │   └── tables.py              # Modelos: Client, Customer, Appointment
│   ├── services/
│   │   ├── gemini.py              # Google Gemini AI + prompts
│   │   ├── calendar.py            # Google Calendar API
│   │   ├── email_service.py       # Resend API (5 tipos de email)
│   │   ├── media.py               # Audio, imágenes, documentos
│   │   ├── catalog_pdf.py         # Lectura de catálogos PDF
│   │   ├── whatsapp.py            # WhatsApp Business API
│   │   ├── client_service.py      # Lógica de clientes/customers
│   │   ├── scheduler_tasks.py     # Tareas de recordatorios
│   │   └── auto_scheduler.py      # Cron jobs automáticos
│   ├── agents/tools/
│   │   └── definitions.py         # 8 herramientas de IA
│   └── api/routes/
│       ├── webhook.py             # Webhook de WhatsApp
│       └── scheduler.py           # API de tareas programadas
├── Dockerfile                     # Multi-stage, non-root
├── requirements.txt               # Dependencias Python
└── credentials/                   # Google Calendar service account
```
