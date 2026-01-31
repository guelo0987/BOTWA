# Configuración por tipo de negocio – Ejemplos y variantes

Este README muestra **cómo queda la configuración** (`tools_config` + `system_prompt_template` cuando aplica) para cada **tipo de negocio** y sus **variantes**. Sirve como referencia rápida para armar el JSON en tu app de admin (Next.js).

- **Tipos:** `salon`, `store`, `clinic`, `restaurant`, `general`
- **Variantes:** por ejemplo salon = detailing, taller, spa; store = solo catálogo vs con entregas; clinic = un doctor vs varios; etc.

Los ejemplos están alineados con el bot real (campos que el backend usa).

---

## 1. Tipo `salon` – Negocio con servicios y citas

Genérico: sirve para cualquier rubro (detailing, taller, spa, centro de servicios). El tono se define con `system_prompt_template`.

### 1.1 Variante: Detailing (sin profesionales)

Un solo calendario, lista de servicios, sin preguntar “¿con quién?”.

**`tools_config`:**

```json
{
  "business_type": "salon",
  "calendar_id": "detailing-xyz@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "09:00", "end": "18:00" },
  "working_days": [1, 2, 3, 4, 5, 6],
  "slot_duration": 30,
  "services": [
    { "name": "Lavado básico", "price": 500, "duration_minutes": 30 },
    { "name": "Lavado completo", "price": 800, "duration_minutes": 45 },
    { "name": "Pulido", "price": 2000, "duration_minutes": 120 },
    { "name": "Encerado", "price": 1500, "duration_minutes": 90 }
  ],
  "professionals": []
}
```

**`system_prompt_template` (recomendado):**

```
Eres el asistente de [Detailing XYZ]. Hablas de servicios de detailing automotriz (lavado, pulido, encerado). Sé breve y profesional.
```

---

### 1.2 Variante: Taller / centro de servicios (un profesional)

Un profesional opcional; el bot puede confirmar “con Juan” pero no insiste si el cliente no elige.

**`tools_config`:**

```json
{
  "business_type": "salon",
  "calendar_id": "taller-abc@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "08:00", "end": "17:00" },
  "working_days": [1, 2, 3, 4, 5],
  "services": [
    { "name": "Revisión general", "price": 800, "duration_minutes": 60 },
    { "name": "Cambio de aceite", "price": 1200, "duration_minutes": 45 },
    { "name": "Alineación", "price": 1500, "duration_minutes": 60 }
  ],
  "professionals": [
    { "id": "carlos", "name": "Carlos", "specialty": "Mecánico" }
  ]
}
```

**`system_prompt_template` (opcional):**

```
Eres el asistente de [Taller ABC]. Ofreces servicios de mecánica automotriz. Sé cordial y conciso.
```

---

### 1.3 Variante: Spa / centro con varios profesionales

Varios profesionales; el bot pregunta si quieren uno en específico o “quien esté disponible”. Cada uno puede tener su propio `calendar_id`.

**`tools_config`:**

```json
{
  "business_type": "salon",
  "calendar_id": "spa-general@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "09:00", "end": "20:00" },
  "working_days": [1, 2, 3, 4, 5, 6],
  "slot_duration": 60,
  "services": [
    { "name": "Masaje relajante", "price": 1200, "duration_minutes": 60 },
    { "name": "Facial", "price": 800, "duration_minutes": 45 },
    { "name": "Tratamiento corporal", "price": 1800, "duration_minutes": 90 }
  ],
  "professionals": [
    { "id": "maria", "name": "María", "specialty": "Masajes", "calendar_id": "spa-maria@group.calendar.google.com" },
    { "id": "lucia", "name": "Lucía", "specialty": "Faciales", "calendar_id": "spa-lucia@group.calendar.google.com" }
  ]
}
```

**`system_prompt_template` (opcional):**

```
Eres el asistente de [Spa XYZ]. Ofreces masajes, faciales y tratamientos corporales. Sé amable y profesional.
```

---

## 2. Tipo `store` – Tienda / catálogo (sin citas obligatorias)

Catálogo de productos; “pásate cuando quieras”. Citas solo si configuras entregas a domicilio.

### 2.1 Variante: Solo catálogo (dealer, concesionario)

Sin `calendar_id`. El bot muestra productos/horarios y no pide agendar para visitar.

**`tools_config`:**

```json
{
  "business_type": "store",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "09:00", "end": "19:00" },
  "working_days": [1, 2, 3, 4, 5, 6],
  "catalog": {
    "categories": [
      {
        "name": "Sedanes",
        "products": [
          { "name": "Modelo A 2025", "price": 25000, "description": "Sedán económico, 4 puertas" },
          { "name": "Modelo B 2025", "price": 32000, "description": "Sedán full equipo" }
        ]
      },
      {
        "name": "SUVs",
        "products": [
          { "name": "SUV X 2025", "price": 45000, "description": "SUV 5 plazas" }
        ]
      }
    ]
  }
}
```

**`system_prompt_template` (recomendado):**

```
Eres el asistente de [Concesionario XYZ]. Hablas de autos, modelos y precios. Si el cliente dice que va a pasar a ver, confirma horarios y dile que puede pasar cuando quiera. No obligues a agendar cita para solo ver el catálogo.
```

---

### 2.2 Variante: Tienda con entregas a domicilio

Con `calendar_id` para agendar entregas; opcionalmente `delivery_hours`, `delivery_duration` y `free_delivery_minimum`.

**`tools_config`:**

```json
{
  "business_type": "store",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "09:00", "end": "18:00" },
  "working_days": [1, 2, 3, 4, 5, 6],
  "catalog": {
    "categories": [
      {
        "name": "Colchones",
        "products": [
          { "name": "Colchón estándar", "price": 15000, "description": "Queen size" },
          { "name": "Colchón premium", "price": 28000, "description": "King size, memory foam" }
        ]
      }
    ]
  },
  "calendar_id": "entregas-tienda@group.calendar.google.com",
  "delivery_hours": { "start": "10:00", "end": "17:00" },
  "delivery_duration": 60,
  "free_delivery_minimum": 20000
}
```

---

## 3. Tipo `clinic` – Clínica / consultorio

Citas con profesional. Si hay **varios** profesionales, el bot **obliga** a elegir con quién agendar.

### 3.1 Variante: Un solo doctor

Un profesional; no se insiste en “¿con quién?”. Puede usarse el mismo `calendar_id` para todo.

**`tools_config`:**

```json
{
  "business_type": "clinic",
  "calendar_id": "clinica@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "08:00", "end": "18:00" },
  "working_days": [1, 2, 3, 4, 5],
  "services": [
    { "name": "Consulta General", "price": 50, "duration_minutes": 30 }
  ],
  "professionals": [
    {
      "id": "dr_garcia",
      "name": "Dr. García",
      "specialty": "Medicina General"
    }
  ]
}
```

---

### 3.2 Variante: Varios doctores (calendario por doctor)

Cada doctor con su `calendar_id` y especialidad; el bot pide elegir profesional antes de agendar.

**`tools_config`:**

```json
{
  "business_type": "clinic",
  "calendar_id": "clinica@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "08:00", "end": "18:00" },
  "working_days": [1, 2, 3, 4, 5],
  "services": [
    { "name": "Consulta General", "price": 50, "duration_minutes": 30 },
    { "name": "Consulta Especializada", "price": 100, "duration_minutes": 60 }
  ],
  "professionals": [
    {
      "id": "doc_1",
      "name": "Dr. García",
      "specialty": "Cardiología",
      "calendar_id": "drgarcia@group.calendar.google.com"
    },
    {
      "id": "doc_2",
      "name": "Dra. López",
      "specialty": "Pediatría",
      "calendar_id": "drlopez@group.calendar.google.com"
    }
  ]
}
```

---

## 4. Tipo `restaurant` – Restaurante

Reservas de mesas: nombre, correo, invitados, fecha, hora, área preferida. Sin profesionales.

### 4.1 Variante: Básico (solo reservas)

Sin áreas ni menú; el bot recopila lo mínimo para reservar.

**`tools_config`:**

```json
{
  "business_type": "restaurant",
  "calendar_id": "restaurante@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "business_hours": { "start": "12:00", "end": "23:00" },
  "working_days": [1, 2, 3, 4, 5, 6, 7]
}
```

---

### 4.2 Variante: Con áreas y menú

Áreas para elegir (terraza, salón, VIP) y `menu_url` para cuando pregunten por el menú.

**`tools_config`:**

```json
{
  "business_type": "restaurant",
  "calendar_id": "restaurante@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "12:00", "end": "23:00" },
  "working_days": [1, 2, 3, 4, 5, 6, 7],
  "areas": ["Terraza", "Salón principal", "VIP"],
  "menu_url": "https://restaurante.com/menu"
}
```

---

## 5. Tipo `general` – Negocio genérico

Solo citas básicas: nombre, correo, fecha, hora. Sin servicios ni profesionales.

**`tools_config`:**

```json
{
  "business_type": "general",
  "calendar_id": "negocio@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "business_hours": { "start": "09:00", "end": "18:00" },
  "working_days": [1, 2, 3, 4, 5]
}
```

---

## 6. Resumen rápido por tipo

| Tipo        | Variantes típicas                    | Campos clave extra |
|------------|--------------------------------------|--------------------|
| **salon**  | Detailing, taller, spa               | `services`, `professionals` (opcional), `slot_duration` |
| **store**  | Solo catálogo / Con entregas        | `catalog`, opcional `calendar_id`, `delivery_hours`, `delivery_duration`, `free_delivery_minimum` |
| **clinic** | Un doctor / Varios doctores         | `professionals` (con `calendar_id` si varios), `services` opcional |
| **restaurant** | Básico / Con áreas y menú    | `areas`, `menu_url` |
| **general** | Citas simples                      | Solo `calendar_id`, `business_hours`, `working_days` |

Para el detalle de cada campo y reglas del bot, usa **README_CONFIG_ADMIN.md**.
