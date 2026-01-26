# 🤖 WhatsApp Bot - Arquitectura y Configuración Completa

Este documento explica la arquitectura completa del bot, cómo funciona el sistema multi-inquilino, y **cómo configurar correctamente cada cliente** con sus personalidades, servicios y herramientas.

---

## 📋 Tabla de Contenidos

1. [Arquitectura General](#arquitectura-general)
2. [Sistema Multi-Inquilino](#sistema-multi-inquilino)
3. [Estructura de Base de Datos](#estructura-de-base-de-datos)
4. [Configuración del Cliente (tools_config)](#configuración-del-cliente-tools_config)
5. [Personalidad del Bot (system_prompt_template)](#personalidad-del-bot-system_prompt_template)
6. [Tipos de Negocio Soportados](#tipos-de-negocio-soportados)
7. [Ejemplos de Configuración Completa](#ejemplos-de-configuración-completa)
8. [Flujo de Funcionamiento](#flujo-de-funcionamiento)
9. [Guía de Implementación](#guía-de-implementación)

---

## 🏗️ Arquitectura General

### Componentes Principales

```
┌─────────────────────────────────────────────────────────┐
│                    WhatsApp Business API                │
│                    (Meta/Facebook)                      │
└────────────────────┬────────────────────────────────────┘
                     │ Webhook (mensajes entrantes)
                     ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend (Python)                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Webhook Handler → Process Message               │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │                                   │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │  GeminiService → build_system_prompt()          │  │
│  │  (Personalidad + Configuración)                 │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │                                   │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │  ToolExecutor → execute()                        │  │
│  │  (Herramientas según business_type)             │  │
│  └──────────────────┬───────────────────────────────┘  │
└─────────────────────┼───────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
┌──────────────┐          ┌──────────────────┐
│  PostgreSQL  │          │      Redis       │
│  (Datos)     │          │  (Conversación)  │
│              │          │                  │
│ - Client     │          │ - Historial      │
│ - Customer   │          │ - Estado         │
│ - Appointment│          │ - TTL: 1 hora    │
└──────────────┘          └──────────────────┘
```

### Flujo de un Mensaje

```
1. Usuario envía mensaje → WhatsApp API
2. WhatsApp API → Webhook POST a FastAPI
3. FastAPI identifica Client por phone_number_id
4. Obtiene/Crea Customer
5. Carga historial de Redis
6. GeminiService:
   - Construye system_prompt (personalidad + config)
   - Llama a Gemini con historial + tools
7. Gemini decide usar tool → ToolExecutor
8. ToolExecutor ejecuta según business_type
9. Respuesta enviada por WhatsApp API
10. Mensaje guardado en Redis
```

---

## 🏢 Sistema Multi-Inquilino

### Concepto

**Cada cliente (empresa) tiene:**
- Su propia configuración (`tools_config`)
- Su propia personalidad (`system_prompt_template`)
- Sus propios datos (customers, appointments)
- Su propio WhatsApp Business Number ID

### Identificación del Cliente

El bot identifica qué cliente es mediante el **`phone_number_id`** que viene en el webhook de Meta:

```python
# En webhook.py
phone_number_id = value.metadata.phone_number_id
client = await client_service.get_client_by_phone_id(phone_number_id)
```

**Cada cliente debe tener un `whatsapp_instance_id` único** que corresponde a su Phone Number ID en Meta.

### Aislamiento de Datos

- **Client**: Cada empresa es un registro separado
- **Customer**: Pertenece a un `client_id` específico
- **Appointment**: Pertenece a un `client_id` específico
- **Redis**: Keys incluyen `client_id`: `chat:{client_id}:{phone_number}`

---

## 💾 Estructura de Base de Datos

### Tabla: `clients` (Tabla Maestra)

```sql
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    business_name VARCHAR NOT NULL,              -- "Clínica Moreira"
    whatsapp_instance_id VARCHAR UNIQUE,         -- "1234567890" (Phone Number ID de Meta)
    is_active BOOLEAN DEFAULT TRUE,              -- Interruptor de pago
    system_prompt_template TEXT NOT NULL,        -- Personalidad del bot
    tools_config JSON DEFAULT '{}',              -- ⚠️ CONFIGURACIÓN PRINCIPAL
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Campos Clave:**

1. **`business_name`**: Nombre del negocio (usado en prompts)
2. **`whatsapp_instance_id`**: ID del número de WhatsApp en Meta (para identificar cliente)
3. **`system_prompt_template`**: Personalidad y comportamiento del bot (texto)
4. **`tools_config`**: ⚠️ **CONFIGURACIÓN JSON** - Define servicios, horarios, profesionales, etc.

### Tabla: `customers` (Usuarios)

```sql
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),    -- Pertenece a un cliente
    phone_number VARCHAR,                        -- "18091234567"
    full_name VARCHAR,                           -- "María García"
    data JSON DEFAULT '{}',                      -- Datos flexibles según negocio
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Campo `data` (JSON flexible):**
- **Clínica**: `{"dob": "1990-01-01", "insurance": "Humano", "allergies": ["Nueces"]}`
- **Restaurante**: `{"address": "Calle 123", "favorite_dish": "Pizza"}`
- **Tienda**: `{"shipping_address": "...", "preferences": {...}}`

### Tabla: `appointments` (Citas/Reservas)

```sql
CREATE TABLE appointments (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    customer_id INTEGER REFERENCES customers(id),
    google_event_id VARCHAR UNIQUE,              -- ID del evento en Google Calendar
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR DEFAULT 'CONFIRMED',           -- CONFIRMED, CANCELLED, NO_SHOW
    notes TEXT                                   -- Motivo consulta / Mesa reservada
);
```

---

## ⚙️ Configuración del Cliente (tools_config)

### ⚠️ IMPORTANTE: Este es el campo más crítico

El campo `tools_config` es un **JSON** que define TODO lo que el bot necesita saber sobre el negocio:

- Tipo de negocio (`business_type`)
- Servicios/productos disponibles
- Profesionales/doctores
- Horarios de atención
- Calendario de Google
- Zona horaria
- Y más...

### Estructura Base de `tools_config`

```json
{
  "business_type": "clinic" | "salon" | "restaurant" | "store" | "general",
  "calendar_id": "google_calendar_id@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": {
    "start": "08:00",
    "end": "18:00"
  },
  "working_days": [1, 2, 3, 4, 5],  // Lunes a Viernes
  // ... más campos según business_type
}
```

---

## 🎭 Personalidad del Bot (system_prompt_template)

### ¿Qué es?

Es un **texto** que define cómo se comporta el bot:
- Tono de voz
- Estilo de comunicación
- Qué información menciona
- Cómo saluda
- Cómo se despide

### Ejemplo Básico

```
Eres el asistente virtual de *{business_name}*. 
Tu objetivo es brindar una atención profesional, cálida y eficiente.

REGLAS:
- Saluda cordialmente
- Habla como una persona real
- Respuestas cortas y directas
- Usa emojis con moderación
```

### Variables Dinámicas

El sistema automáticamente reemplaza:
- `{business_name}` → Nombre del negocio
- `{fecha_actual}` → Fecha actual
- `{hora_actual}` → Hora actual
- Y agrega información de `tools_config` (servicios, horarios, etc.)

---

## 🏪 Tipos de Negocio Soportados

### 1. `clinic` (Clínica Médica)

**Características:**
- Múltiples doctores/especialistas
- Citas médicas con duración variable
- Requiere seguro médico (opcional)
- Áreas/especialidades

**`tools_config` ejemplo:**

```json
{
  "business_type": "clinic",
  "calendar_id": "clinica_moreira@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": {
    "start": "08:00",
    "end": "18:00"
  },
  "working_days": [1, 2, 3, 4, 5],
  "professionals": [
    {
      "id": "doc_1",
      "name": "Dr. Juan Pérez",
      "specialty": "Cardiología",
      "calendar_id": "dr_juan@group.calendar.google.com"
    },
    {
      "id": "doc_2",
      "name": "Dra. Ana García",
      "specialty": "Pediatría",
      "calendar_id": "dra_ana@group.calendar.google.com"
    }
  ],
  "services": [
    {
      "name": "Consulta General",
      "duration_minutes": 30,
      "price": 50
    },
    {
      "name": "Consulta Especializada",
      "duration_minutes": 60,
      "price": 100
    }
  ],
  "requires_insurance": true,
  "contact_phone": "18091234567"
}
```

**Campos Específicos:**
- `professionals`: Array de doctores con sus calendarios
- `services`: Servicios con duración y precio
- `requires_insurance`: Si requiere seguro médico

### 2. `salon` (Salón de Belleza)

**Características:**
- Servicios con duración variable
- Un solo profesional o múltiples
- Precios por servicio

**`tools_config` ejemplo:**

```json
{
  "business_type": "salon",
  "calendar_id": "salon_belleza@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": {
    "start": "09:00",
    "end": "20:00"
  },
  "working_days": [1, 2, 3, 4, 5, 6],
  "services": [
    {
      "name": "Corte de Cabello",
      "duration_minutes": 30,
      "price": 25
    },
    {
      "name": "Tinte",
      "duration_minutes": 120,
      "price": 80
    },
    {
      "name": "Manicure",
      "duration_minutes": 45,
      "price": 20
    }
  ],
  "professionals": [
    {
      "id": "stylist_1",
      "name": "María López",
      "specialty": "Colorista"
    }
  ]
}
```

### 3. `restaurant` (Restaurante)

**Características:**
- Reservas de mesas
- Capacidad por área (terraza, salón)
- Ocasiones especiales

**`tools_config` ejemplo:**

```json
{
  "business_type": "restaurant",
  "calendar_id": "restaurante_central@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": {
    "start": "12:00",
    "end": "23:00"
  },
  "working_days": [1, 2, 3, 4, 5, 6, 7],
  "areas": [
    {
      "name": "Terraza",
      "capacity": 20
    },
    {
      "name": "Salón Principal",
      "capacity": 40
    }
  ],
  "occasions": [
    "Cena Romántica",
    "Cumpleaños",
    "Reunión de Negocios",
    "Celebración Especial"
  ],
  "menu_url": "https://restaurante.com/menu"
}
```

**Campos Específicos:**
- `areas`: Áreas del restaurante con capacidad
- `occasions`: Ocasiones especiales disponibles
- `menu_url`: URL del menú (opcional)

### 4. `store` (Tienda/E-commerce)

**Características:**
- Catálogo de productos
- Categorías
- Entrega a domicilio

**`tools_config` ejemplo:**

```json
{
  "business_type": "store",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": {
    "start": "09:00",
    "end": "20:00"
  },
  "working_days": [1, 2, 3, 4, 5, 6],
  "catalog": {
    "categories": [
      {
        "name": "Colchones",
        "products": [
          {
            "name": "Colchón Ortopédico Premium",
            "price": 500,
            "description": "Colchón de alta calidad..."
          },
          {
            "name": "Colchón Memory Foam",
            "price": 350,
            "description": "Colchón con tecnología..."
          }
        ]
      },
      {
        "name": "Almohadas",
        "products": [
          {
            "name": "Almohada Ergonómica",
            "price": 50,
            "description": "Almohada diseñada para..."
          }
        ]
      }
    ]
  },
  "delivery_available": true,
  "delivery_fee": 10
}
```

**Campos Específicos:**
- `catalog`: Catálogo con categorías y productos
- `delivery_available`: Si ofrece entrega
- `delivery_fee`: Costo de entrega

### 5. `general` (Negocio General)

**Características:**
- Configuración mínima
- Solo citas básicas

**`tools_config` ejemplo:**

```json
{
  "business_type": "general",
  "calendar_id": "negocio_general@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "business_hours": {
    "start": "09:00",
    "end": "18:00"
  },
  "working_days": [1, 2, 3, 4, 5]
}
```

---

## 📝 Ejemplos de Configuración Completa

### Ejemplo 1: Clínica Médica Completa

#### SQL para crear el cliente:

```sql
INSERT INTO clients (
    business_name,
    whatsapp_instance_id,
    system_prompt_template,
    tools_config,
    is_active
) VALUES (
    'Clínica Moreira',
    '1234567890',  -- Phone Number ID de Meta
    'Eres el asistente virtual de *Clínica Moreira*. 
     Somos una clínica especializada en atención médica integral.
     Tu objetivo es ayudar a los pacientes a agendar citas de manera eficiente.
     
     IMPORTANTE:
     - Siempre pregunta el nombre completo
     - Pregunta el correo electrónico (obligatorio)
     - Pregunta si tiene seguro médico
     - Ofrece los doctores disponibles según la especialidad necesaria',
    '{
        "business_type": "clinic",
        "calendar_id": "clinica_moreira@group.calendar.google.com",
        "timezone": "America/Santo_Domingo",
        "currency": "$",
        "business_hours": {
            "start": "08:00",
            "end": "18:00"
        },
        "working_days": [1, 2, 3, 4, 5],
        "professionals": [
            {
                "id": "doc_1",
                "name": "Dr. Juan Pérez",
                "specialty": "Cardiología",
                "calendar_id": "dr_juan@group.calendar.google.com"
            },
            {
                "id": "doc_2",
                "name": "Dra. Ana García",
                "specialty": "Pediatría",
                "calendar_id": "dra_ana@group.calendar.google.com"
            },
            {
                "id": "doc_3",
                "name": "Dr. Carlos Rodríguez",
                "specialty": "Medicina General",
                "calendar_id": "dr_carlos@group.calendar.google.com"
            }
        ],
        "services": [
            {
                "name": "Consulta General",
                "duration_minutes": 30,
                "price": 50
            },
            {
                "name": "Consulta Especializada",
                "duration_minutes": 60,
                "price": 100
            },
            {
                "name": "Consulta de Seguimiento",
                "duration_minutes": 20,
                "price": 30
            }
        ],
        "requires_insurance": true,
        "contact_phone": "18091234567"
    }'::jsonb,
    true
);
```

#### Explicación de cada campo:

- **`business_name`**: "Clínica Moreira" - Aparece en todos los mensajes
- **`whatsapp_instance_id`**: "1234567890" - Debe coincidir con el Phone Number ID en Meta
- **`system_prompt_template`**: Define la personalidad y comportamiento
- **`tools_config.business_type`**: "clinic" - Activa lógica de clínica
- **`tools_config.professionals`**: Array de doctores con sus calendarios
- **`tools_config.services`**: Servicios con duración y precio
- **`tools_config.calendar_id`**: Calendario principal (backup si no hay profesional específico)

### Ejemplo 2: Restaurante

```sql
INSERT INTO clients (
    business_name,
    whatsapp_instance_id,
    system_prompt_template,
    tools_config,
    is_active
) VALUES (
    'Central Gastronómica',
    '9876543210',
    'Eres el asistente virtual de *Central Gastronómica*.
     Somos un restaurante de alta cocina especializado en platos internacionales.
     
     IMPORTANTE:
     - Pregunta nombre completo
     - Pregunta correo electrónico (obligatorio)
     - Pregunta cantidad de invitados
     - Pregunta área preferida (Terraza o Salón)
     - Pregunta ocasión especial si aplica',
    '{
        "business_type": "restaurant",
        "calendar_id": "central_gastronomica@group.calendar.google.com",
        "timezone": "America/Santo_Domingo",
        "currency": "$",
        "business_hours": {
            "start": "12:00",
            "end": "23:00"
        },
        "working_days": [1, 2, 3, 4, 5, 6, 7],
        "areas": [
            {
                "name": "Terraza",
                "capacity": 20
            },
            {
                "name": "Salón Principal",
                "capacity": 40
            },
            {
                "name": "Salón Privado",
                "capacity": 15
            }
        ],
        "occasions": [
            "Cena Romántica",
            "Cumpleaños",
            "Reunión de Negocios",
            "Celebración Especial",
            "Aniversario"
        ],
        "menu_url": "https://centralgastronomica.com/menu",
        "contact_phone": "18099876543"
    }'::jsonb,
    true
);
```

### Ejemplo 3: Salón de Belleza

```sql
INSERT INTO clients (
    business_name,
    whatsapp_instance_id,
    system_prompt_template,
    tools_config,
    is_active
) VALUES (
    'Salón Glamour',
    '5555555555',
    'Eres el asistente virtual de *Salón Glamour*.
     Somos un salón de belleza especializado en cortes modernos, coloración y tratamientos.
     
     IMPORTANTE:
     - Pregunta nombre completo
     - Pregunta correo electrónico (obligatorio)
     - Muestra servicios disponibles con precios
     - Pregunta qué servicio desea',
    '{
        "business_type": "salon",
        "calendar_id": "salon_glamour@group.calendar.google.com",
        "timezone": "America/Santo_Domingo",
        "currency": "$",
        "business_hours": {
            "start": "09:00",
            "end": "20:00"
        },
        "working_days": [1, 2, 3, 4, 5, 6],
        "services": [
            {
                "name": "Corte de Cabello",
                "duration_minutes": 30,
                "price": 25
            },
            {
                "name": "Corte + Peinado",
                "duration_minutes": 60,
                "price": 45
            },
            {
                "name": "Tinte Completo",
                "duration_minutes": 120,
                "price": 80
            },
            {
                "name": "Mechas",
                "duration_minutes": 150,
                "price": 100
            },
            {
                "name": "Manicure",
                "duration_minutes": 45,
                "price": 20
            },
            {
                "name": "Pedicure",
                "duration_minutes": 60,
                "price": 25
            }
        ],
        "professionals": [
            {
                "id": "stylist_1",
                "name": "María López",
                "specialty": "Colorista"
            },
            {
                "id": "stylist_2",
                "name": "Ana Martínez",
                "specialty": "Cortes"
            }
        ],
        "contact_phone": "18095555555"
    }'::jsonb,
    true
);
```

---

## 🔄 Flujo de Funcionamiento

### 1. Usuario Envía Mensaje

```
Usuario: "Hola, quiero agendar una cita"
```

### 2. Bot Identifica Cliente

```python
# webhook.py
phone_number_id = "1234567890"  # Del webhook de Meta
client = await get_client_by_phone_id(phone_number_id)
# → Encuentra: Clínica Moreira (id=1)
```

### 3. Bot Construye Personalidad

```python
# gemini.py
system_prompt = build_system_prompt(client, customer)
# → Incluye:
#   - Nombre del negocio: "Clínica Moreira"
#   - Servicios disponibles (de tools_config)
#   - Profesionales (de tools_config)
#   - Horarios (de tools_config)
#   - Reglas de comportamiento (de system_prompt_template)
```

### 4. Bot Procesa con Gemini

```python
# Gemini recibe:
# - system_prompt (personalidad + info del negocio)
# - historial de conversación (de Redis)
# - mensaje del usuario
# - tools disponibles (ver_servicios, crear_cita, etc.)
```

### 5. Gemini Decide Usar Tool

```python
# Gemini decide: "Necesito crear una cita"
# Llama a: crear_cita(fecha="2026-01-25", hora="10:00", ...)
```

### 6. ToolExecutor Ejecuta

```python
# tools/definitions.py
tool_executor = ToolExecutor(client, customer)
# → Lee tools_config
# → business_type = "clinic"
# → Ejecuta lógica específica de clínica
# → Busca disponibilidad en Google Calendar
# → Crea cita
```

### 7. Bot Responde

```
Bot: "✅ Perfecto, he agendado tu cita con Dr. Juan Pérez 
     para el 25 de enero a las 10:00 AM. 
     Te envié la confirmación a tu correo."
```

---

## 🛠️ Guía de Implementación

### Paso 1: Crear Cliente en Base de Datos

```sql
-- 1. Crear registro en clients
INSERT INTO clients (
    business_name,
    whatsapp_instance_id,
    system_prompt_template,
    tools_config,
    is_active
) VALUES (
    'Mi Negocio',
    'TU_PHONE_NUMBER_ID',  -- ⚠️ IMPORTANTE: De Meta
    'Tu personalidad aquí...',
    '{"business_type": "general", ...}'::jsonb,
    true
);
```

### Paso 2: Configurar WhatsApp en Meta

1. Ve a [Meta for Developers](https://developers.facebook.com/)
2. Crea/Selecciona tu app
3. Ve a WhatsApp → Configuration
4. Copia el **Phone Number ID** → Úsalo en `whatsapp_instance_id`
5. Configura webhook: `https://tu-dominio.com/webhook`
6. Verifica token

### Paso 3: Configurar Google Calendar (si aplica)

1. Crea calendario en Google Calendar
2. Comparte con el service account (del archivo JSON de credenciales)
3. Copia el **Calendar ID** → Úsalo en `tools_config.calendar_id`

### Paso 4: Configurar `tools_config`

**⚠️ IMPORTANTE: El JSON debe ser válido**

Usa este template según tu tipo de negocio:

```json
{
  "business_type": "clinic",
  "calendar_id": "tu_calendario@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": {
    "start": "08:00",
    "end": "18:00"
  },
  "working_days": [1, 2, 3, 4, 5]
}
```

### Paso 5: Configurar `system_prompt_template`

Escribe la personalidad del bot. Incluye:
- Cómo saluda
- Qué información menciona
- Tono de voz
- Reglas específicas

**Ejemplo:**

```
Eres el asistente virtual de *{business_name}*.
Tu objetivo es ayudar a los clientes de manera profesional y amable.

REGLAS:
- Saluda cordialmente
- Pregunta el correo electrónico siempre
- Confirma antes de agendar
```

---

## ⚠️ Errores Comunes y Soluciones

### Error 1: "Client no encontrado"

**Causa:** El `whatsapp_instance_id` no coincide con el Phone Number ID de Meta.

**Solución:**
```sql
-- Verificar
SELECT id, business_name, whatsapp_instance_id FROM clients;

-- Actualizar
UPDATE clients 
SET whatsapp_instance_id = 'NUEVO_PHONE_ID' 
WHERE id = 1;
```

### Error 2: "No hay disponibilidad"

**Causa:** El `calendar_id` no existe o no tiene permisos.

**Solución:**
1. Verificar que el calendario existe en Google Calendar
2. Verificar que el service account tiene acceso
3. Verificar formato: `calendario@group.calendar.google.com`

### Error 3: "business_type no reconocido"

**Causa:** El `business_type` en `tools_config` no es válido.

**Solución:**
```sql
-- Verificar
SELECT tools_config->>'business_type' FROM clients WHERE id = 1;

-- Debe ser uno de: "clinic", "salon", "restaurant", "store", "general"
```

### Error 4: JSON inválido en `tools_config`

**Causa:** El JSON tiene errores de sintaxis.

**Solución:**
```sql
-- Validar JSON
SELECT tools_config::text FROM clients WHERE id = 1;

-- Usar herramienta online: https://jsonlint.com/
-- Corregir y actualizar
UPDATE clients 
SET tools_config = '{"business_type": "clinic", ...}'::jsonb 
WHERE id = 1;
```

---

## 📊 Estructura de Datos JSON - Referencia Rápida

### `tools_config` - Campos Comunes

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `business_type` | string | ✅ | "clinic", "salon", "restaurant", "store", "general" |
| `calendar_id` | string | ⚠️ | ID de Google Calendar (requerido si usa citas) |
| `timezone` | string | ✅ | "America/Santo_Domingo", "America/New_York", etc. |
| `currency` | string | ❌ | "$", "€", "RD$" (default: "$") |
| `business_hours` | object | ❌ | `{"start": "08:00", "end": "18:00"}` |
| `working_days` | array | ❌ | `[1,2,3,4,5]` (1=Lunes, 7=Domingo) |

### `tools_config` - Campos por Tipo

#### `clinic`
- `professionals`: Array de doctores
- `services`: Array de servicios
- `requires_insurance`: boolean

#### `salon`
- `services`: Array de servicios
- `professionals`: Array de estilistas (opcional)

#### `restaurant`
- `areas`: Array de áreas
- `occasions`: Array de ocasiones
- `menu_url`: string (opcional)

#### `store`
- `catalog`: Object con categorías y productos
- `delivery_available`: boolean
- `delivery_fee`: number

---

## 🔍 Verificación y Testing

### Verificar Configuración de un Cliente

```sql
-- Ver configuración completa
SELECT 
    id,
    business_name,
    whatsapp_instance_id,
    is_active,
    tools_config->>'business_type' as business_type,
    tools_config->>'calendar_id' as calendar_id,
    tools_config->>'timezone' as timezone
FROM clients
WHERE id = 1;
```

### Verificar Customers de un Cliente

```sql
SELECT 
    c.id,
    c.phone_number,
    c.full_name,
    c.data
FROM customers c
WHERE c.client_id = 1;
```

### Verificar Appointments

```sql
SELECT 
    a.id,
    a.start_time,
    a.end_time,
    a.status,
    cu.full_name as customer_name
FROM appointments a
JOIN customers cu ON a.customer_id = cu.id
WHERE a.client_id = 1
ORDER BY a.start_time DESC;
```

---

## 📚 Recursos Adicionales

- [Google Calendar API](https://developers.google.com/calendar)
- [WhatsApp Business API](https://developers.facebook.com/docs/whatsapp)
- [PostgreSQL JSON Functions](https://www.postgresql.org/docs/current/functions-json.html)
- [Timezone Database](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones)

---

## ✅ Checklist de Configuración

- [ ] Cliente creado en base de datos
- [ ] `whatsapp_instance_id` configurado (coincide con Meta)
- [ ] `system_prompt_template` escrito (personalidad)
- [ ] `tools_config` configurado (JSON válido)
- [ ] `business_type` correcto
- [ ] `calendar_id` configurado (si usa citas)
- [ ] Google Calendar compartido con service account
- [ ] `timezone` correcta
- [ ] `business_hours` configurados
- [ ] Webhook configurado en Meta
- [ ] Probado con mensaje de prueba

---

**¿Preguntas?** Revisa los ejemplos de configuración arriba o consulta el código fuente en `app/services/gemini.py` y `app/agents/tools/definitions.py`.
