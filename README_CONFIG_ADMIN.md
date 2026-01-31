# Configuración desde la App de Admin – Guía exhaustiva

**Para quién es:** Tu app de admin (Next.js) que gestiona clientes del bot. Todo lo que aparece aquí está **verificado contra el código del bot**: solo se documentan campos y comportamientos que el backend usa realmente. No incluye cosas que el bot no tenga.

Esta guía explica **paso a paso** cómo configurar cada cliente: tipos de negocio, cada campo de `tools_config`, qué detalles llevan y cómo se comporta el bot. Incluye tipos genéricos (salon/store), tienda sin citas obligatorias y ejemplos completos por tipo.

---

## 1. Dónde se configura todo

En la base de datos, cada **Cliente** tiene (entre otros):

| Campo | Tipo | Uso |
|-------|------|-----|
| `business_name` | string | Nombre del negocio. El bot dice "Eres el asistente de *{business_name}*". |
| `whatsapp_instance_id` | string | ID de la instancia de WhatsApp (Meta). Obligatorio para recibir/enviar mensajes. |
| `is_active` | boolean | Si el cliente está activo (default `true`). Tu panel puede usarlo para mostrar/ocultar o desactivar el bot. |
| `system_prompt_template` | text | Texto que se inyecta en el prompt del bot (puede ser vacío). Sirve para personalidad, tono y contexto (ej. "Eres el asistente de [Detailing XYZ]..."). |
| `tools_config` | JSON | **Configuración principal.** Define `business_type`, calendario, servicios/catálogo, horarios, profesionales, moneda, etc. Ver secciones por tipo. |

Todo lo que sigue detalla **qué poner en `tools_config`** y, cuando aplica, en **`system_prompt_template`**.

---

## 2. Tipos de negocio (`business_type`) – Resumen

En `tools_config` el primer dato es **`business_type`**. Define si hay citas, catálogo, profesionales obligatorios, entregas, etc.

| Valor | Significado | Citas | Catálogo / Servicios | Profesionales | Uso típico |
|-------|-------------|-------|------------------------|---------------|------------|
| **`salon`** | Negocio con **servicios + citas** | Sí (calendario) | Lista de servicios con precio y duración | Opcionales (si hay varios, pregunta; si uno o ninguno, no molesta) | Cualquier índole: detailing, taller, spa, centro de servicios, etc. |
| **`store`** | **Tienda / catálogo** (sin citas obligatorias) | No* | Productos/modelos con precios | No | Dealer de autos, concesionario, tienda; "pásate cuando quieras" |
| **`clinic`** | Clínica / consultorio | Sí (calendario por doctor) | Servicios/consultas | **Obligatorios** si hay más de un doctor | Clínica, consultorio médico |
| **`restaurant`** | Restaurante | Sí (reservas) | Menú opcional (`menu_url`) | No | Restaurante, bar |
| **`general`** | Genérico | Sí (básico) | No | No | Cualquier negocio simple con citas |

\* En `store` las citas solo se usan para **entregas a domicilio** (opcional); no se obliga a agendar para "ir a ver" o consultar catálogo.

---

## 3. Campos comunes (todos los tipos)

Estos campos pueden usarse en **cualquier** `tools_config` según el tipo:

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `business_type` | string | Sí | `salon` \| `store` \| `clinic` \| `restaurant` \| `general` |
| `timezone` | string | Recomendado | Zona horaria (ej. `America/Santo_Domingo`, `America/New_York`). Afecta horarios y fechas. |
| `currency` | string | Recomendado | Símbolo de moneda para precios (ej. `"$"`, `"RD$"`). |
| `business_hours` | object | Sí (salon, clinic, restaurant, general) | `{ "start": "09:00", "end": "18:00" }`. Horario de atención. |
| `working_days` | array | Sí (salon, clinic, restaurant, general) | Días laborables: `[1,2,3,4,5,6]` = lunes a sábado. 1 = lunes, 7 = domingo. |
| `slot_duration` | number | Opcional | Duración por defecto de un slot en minutos (ej. 30). Si no se pone, el bot usa 30. En salon/clinic puede venir también por servicio (`duration_minutes`) o por profesional. |
| `contact_phone` | string | Opcional | Teléfono de contacto del negocio; el bot lo incluye en el prompt para mostrarlo al cliente si aplica. |

---

## 4. Tipo `salon` – Negocio con servicios y citas

**Para qué sirve:** Cualquier negocio que ofrezca **servicios con precios y duración** y **citas**: detailing, taller, spa, centro de servicios, etc. No está atado a un rubro concreto; el tono se adapta con `system_prompt_template`.

**Comportamiento del bot:**
- Muestra servicios con precios y duración cuando preguntan (`ver_servicios`).
- Recopila nombre, correo, servicio, fecha y hora; si hay varios profesionales, pregunta si quieren uno en específico o “quien esté disponible”.
- Agenda en un calendario general o en el calendario del profesional elegido.
- Permite modificar/cancelar/confirmar cita (siempre pide correo para confirmaciones).

### 4.1 Campos de `tools_config` para `salon`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `business_type` | string | Sí | `"salon"` |
| `calendar_id` | string | Sí | ID del calendario de Google (ej. `xxx@group.calendar.google.com`). Donde se crean las citas. |
| `timezone` | string | Recomendado | Ej. `"America/Santo_Domingo"` |
| `currency` | string | Recomendado | Ej. `"$"` |
| `business_hours` | object | Sí | `{ "start": "09:00", "end": "18:00" }` |
| `working_days` | array | Sí | Ej. `[1,2,3,4,5,6]` (lunes a sábado) |
| `slot_duration` | number | Opcional | Duración por defecto del slot en minutos (default 30). Si el servicio tiene `duration_minutes`, se usa ese. |
| `services` | array | Sí | Lista de servicios. Cada elemento: ver tabla abajo. |
| `professionals` | array | Opcional | Lista de profesionales/atendentes. Si está vacío o no existe, el bot no pregunta “¿con quién?”. Si hay más de uno, pregunta pero permite “quien esté disponible”. |

**Cada elemento de `services`:**

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `name` | string | Sí | Nombre del servicio (ej. "Lavado básico", "Consulta 30 min", "Sesión individual"). |
| `price` | number | Sí | Precio (número, sin símbolo). |
| `duration_minutes` | number | Recomendado | Duración en minutos (ej. 30, 60). También se acepta `duration` en algunos flujos. |

**Cada elemento de `professionals` (opcional):**

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `id` | string | Sí | Identificador único (ej. `"juan"`, `"prof_1"`). Se usa en herramientas. |
| `name` | string | Sí | Nombre mostrado al cliente (ej. "Juan", "María López"). |
| `specialty` | string | Opcional | Especialidad o rol (ej. "Detailing", "Colorista"). |
| `calendar_id` | string | Opcional | Si se omite, se usa el `calendar_id` general. Si cada profesional tiene su calendario, ponlo aquí. |
| `business_hours` | object | Opcional | Horario propio del profesional; si no, se usa el general. |
| `working_days` | array | Opcional | Días laborables del profesional; si no, se usa el general. |
| `slot_duration` | number | Opcional | Duración del slot en minutos para ese profesional (default 30). |

### 4.2 Ejemplo completo `salon` (detailing)

```json
{
  "business_type": "salon",
  "calendar_id": "detailing-calendar@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "09:00", "end": "18:00" },
  "working_days": [1, 2, 3, 4, 5, 6],
  "services": [
    { "name": "Lavado básico", "price": 500, "duration_minutes": 30 },
    { "name": "Lavado completo", "price": 800, "duration_minutes": 45 },
    { "name": "Pulido", "price": 2000, "duration_minutes": 120 },
    { "name": "Encerado", "price": 1500, "duration_minutes": 90 }
  ],
  "professionals": []
}
```

Con un solo profesional (opcional):

```json
"professionals": [
  { "id": "juan", "name": "Juan", "specialty": "Detailing" }
]
```

### 4.3 `system_prompt_template` – Adaptar al tipo de negocio

El tipo `salon` es **genérico**: no asume rubro. Usa `system_prompt_template` para que el bot hable de tu negocio (detailing, taller, spa, etc.):

Ejemplo detailing:
```
Eres el asistente de [Nombre del Negocio]. Hablas de servicios de detailing automotriz (lavado, pulido, encerado). Sé breve y profesional.
```

Ejemplo taller/centro de servicios:
```
Eres el asistente de [Nombre del Negocio]. Ofreces servicios de [tu rubro]. Sé cordial y conciso.
```

### 4.4 Comportamiento del tipo `salon`

- Tipo **genérico**: sirve para **cualquier negocio con servicios + citas** (detailing, taller, spa, centro de servicios, etc.).
- Textos del bot neutros: “servicios”, “cita”, “profesional/atendente” (solo si hay varios).
- Si `professionals` está vacío o hay un solo profesional, no se insiste en “¿con quién?”.
- Listado con título neutro: “Servicios disponibles”, con precios y duración.

---

## 5. Tipo `store` – Tienda / catálogo (sin citas obligatorias)

**Para qué sirve:** Dealer de autos, concesionario, tienda: **catálogo de productos/modelos con precios**. El cliente puede preguntar por modelos, precios, y decir “voy a pasar ahora” **sin tener que agendar cita**. Opcionalmente se puede agendar **entrega a domicilio** (pago contra entrega).

**Comportamiento del bot:**
- Responde preguntas del catálogo con `ver_servicios` (por categoría si aplica).
- Si el cliente dice que va a pasar a ver: confirma horarios y responde tipo “Puedes pasar cuando quieras”, “Pásate ahora mismo”, “Te esperamos”. **No obliga a agendar cita.**
- Solo si el cliente quiere **compra con entrega a domicilio**, recopila datos y agenda entrega (pago contra entrega). Para eso sí se usa calendario si lo configuras.

### 5.1 Campos de `tools_config` para `store`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `business_type` | string | Sí | `"store"` |
| `timezone` | string | Recomendado | Ej. `"America/Santo_Domingo"` |
| `currency` | string | Recomendado | Ej. `"$"` |
| `business_hours` | object | Recomendado | Para decir horarios cuando pregunten o digan “voy a pasar”. |
| `working_days` | array | Recomendado | Mismo formato que en otros tipos. |
| `catalog` | object | Sí | Catálogo con categorías y productos. Ver estructura abajo. |
| `calendar_id` | string | Opcional | Solo si agendan **entregas** a domicilio. Para solo catálogo y visita sin cita no es obligatorio. |
| `delivery_hours` | object | Opcional | Si hay `calendar_id`, horario para slots de entrega (ej. `{ "start": "09:00", "end": "18:00" }`). Si no se pone, se usa `business_hours`. |
| `delivery_duration` | number | Opcional | Duración en minutos de cada slot de entrega (default 60). Solo aplica cuando hay `calendar_id`. |
| `free_delivery_minimum` | number | Opcional | Monto mínimo para envío gratis (ej. 3000). El bot lo muestra al listar catálogo. |

**Estructura de `catalog`:**

```json
"catalog": {
  "categories": [
    {
      "name": "Nombre de la categoría",
      "products": [
        {
          "name": "Nombre del producto o modelo",
          "price": 25000,
          "description": "Descripción opcional"
        }
      ]
    }
  ]
}
```

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `categories` | array | Sí | Lista de categorías. |
| `categories[].name` | string | Sí | Nombre de la categoría (ej. "Sedanes", "SUVs", "Colchones"). |
| `categories[].products` | array | Sí | Productos de esa categoría. |
| `products[].name` | string | Sí | Nombre del producto/modelo. |
| `products[].price` | number | Sí | Precio (número). |
| `products[].description` | string | Opcional | Descripción que el bot puede mostrar. |

### 5.2 Ejemplo completo `store` (dealer de autos)

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

Si además tienen entregas a domicilio (ej. tienda de colchones), añade `calendar_id` (y opcionalmente `free_delivery_minimum`).

### 5.3 `system_prompt_template` recomendado para dealer

```
Eres el asistente de [Nombre del Concesionario]. Hablas de autos, modelos y precios. Si el cliente dice que va a pasar a ver, confirma horarios y dile que puede pasar cuando quiera. No obligues a agendar cita para solo ver el catálogo.
```

### 5.4 Cambios recientes en tipo `store`

- **Visita sin cita**: el bot puede decir “Puedes pasar cuando quieras”, “Pásate ahora mismo”, según horarios. **No** obliga a agendar para informarse o ir a ver.
- Entregas a domicilio solo cuando el cliente quiera comprar y llevarlo; pago contra entrega.
- Sin `calendar_id` el negocio puede ser solo catálogo + visita sin cita.

---

## 6. Tipo `clinic` – Clínica / consultorio

**Para qué sirve:** Clínicas o consultorios con uno o varios doctores. Citas **con profesional**. Si hay **más de un profesional**, el bot **obliga** a elegir con quién agendar (no permite “cualquiera” como en `salon`).

**Comportamiento del bot:**
- Muestra profesionales con `ver_profesionales` (especialidad, etc.).
- Recopila nombre, correo, tipo de consulta, **profesional** (obligatorio si hay varios), fecha y hora.
- Si hay múltiples profesionales y el cliente no elige, el bot no agenda hasta que elija; puede mostrar lista de profesionales.
- Agenda en el calendario del profesional (cada uno puede tener `calendar_id` propio) o en el general.

### 6.1 Campos de `tools_config` para `clinic`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `business_type` | string | Sí | `"clinic"` |
| `calendar_id` | string | Sí | Calendario por defecto (si un profesional no tiene `calendar_id`, se usa este). |
| `timezone` | string | Recomendado | Ej. `"America/Santo_Domingo"` |
| `currency` | string | Opcional | Para precios de consultas si aplica. |
| `business_hours` | object | Sí | Horario general. |
| `working_days` | array | Sí | Días de atención. |
| `professionals` | array | Sí (múltiples) | Lista de doctores/profesionales. Si hay más de uno, **cada uno debe tener** `id`, `name`, y normalmente `calendar_id` y `specialty`. |
| `services` | array | Opcional | Servicios/consultas (nombre, precio, duración) para mostrar y calcular slots. |

**Cada elemento de `professionals`:**

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `id` | string | Sí | ID único (ej. `"doc_1"`, `"dr_garcia"`). |
| `name` | string | Sí | Nombre (ej. "Dr. García", "Dra. López"). |
| `specialty` | string | Recomendado | Especialidad (ej. "Cardiología", "Pediatría"). |
| `calendar_id` | string | Recomendado si hay varios | Calendario de ese doctor. Si no, se usa el general. |

### 6.2 Ejemplo completo `clinic`

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

### 6.3 Detalles importantes

- Con **un solo** profesional, el bot puede no preguntar “¿con quién?”.
- Con **varios** profesionales, el bot **no** permite agendar sin elegir profesional; validación en backend.
- Nunca da consejos médicos ni diagnósticos; emergencias → escalar a humano.

---

## 7. Tipo `restaurant` – Restaurante

**Para qué sirve:** Reservas de mesas: fecha, hora, número de personas, área preferida, ocasión opcional. No hay “profesionales”; el flujo es reservación.

**Comportamiento del bot:**
- Recopila nombre, correo, cantidad de invitados, fecha, hora, área preferida (ej. Terraza, Salón), ocasión especial (opcional).
- Confirma reservación y envía confirmación por correo.
- Si hay `menu_url`, al preguntar por menú/servicios el bot puede dar ese enlace.

### 7.1 Campos de `tools_config` para `restaurant`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `business_type` | string | Sí | `"restaurant"` |
| `calendar_id` | string | Sí | Donde se crean las reservaciones. |
| `timezone` | string | Recomendado | Ej. `"America/Santo_Domingo"` |
| `currency` | string | Opcional | Si mencionan precios. |
| `business_hours` | object | Sí | Horario de atención (ej. 12:00–23:00). |
| `working_days` | array | Sí | Días abiertos. |
| `areas` | array | Recomendado | Áreas para reservar (ej. `["Terraza", "Salón principal", "VIP"]`). El bot las incluye en el flujo de reservación. |
| `menu_url` | string | Opcional | URL del menú; el bot la puede dar cuando pregunten por menú o “qué tienen”. |
| `occasions` | array | No usado por el bot | El bot pide "ocasión especial" como texto libre. Este array no se lee en el backend; tu panel puede usarlo solo para sugerencias en la UI si quieres. |

### 7.2 Ejemplo completo `restaurant`

```json
{
  "business_type": "restaurant",
  "calendar_id": "restaurante@group.calendar.google.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": { "start": "12:00", "end": "23:00" },
  "working_days": [1, 2, 3, 4, 5, 6, 7],
  "areas": ["Terraza", "Salón principal", "VIP"],
  "menu_url": "https://restaurante.com/menu",
  "occasions": ["Cumpleaños", "Aniversario", "Reunión de negocios"]
}
```

### 7.3 Detalles importantes

- Grupos grandes (ej. 8+ personas) el bot puede escalar a humano (según instrucciones del prompt).
- Tono cordial y elegante; agradecer por preferir el restaurante.

---

## 8. Tipo `general` – Negocio genérico

**Para qué sirve:** Cualquier negocio que solo necesite **citas básicas** (fecha, hora, nombre, correo), sin catálogo de servicios ni productos ni profesionales.

**Comportamiento del bot:**
- Ofrece agendar cita recopilando nombre, correo, fecha y hora.
- Usa un solo calendario. Sin listado de servicios ni profesionales.

### 8.1 Campos de `tools_config` para `general`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `business_type` | string | Sí | `"general"` |
| `calendar_id` | string | Sí | Calendario donde se crean las citas. |
| `timezone` | string | Recomendado | Ej. `"America/Santo_Domingo"` |
| `business_hours` | object | Sí | Horario de atención. |
| `working_days` | array | Sí | Días laborables. |

### 8.2 Ejemplo completo `general`

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

## 9. Tabla comparativa de tipos

| Característica | salon | store | clinic | restaurant | general |
|----------------|-------|-------|--------|------------|---------|
| **Citas / reservas** | Sí (servicios) | No* | Sí (con doctor) | Sí (mesas) | Sí (básico) |
| **Catálogo / servicios** | Servicios con precio y duración | Productos/modelos con precio | Servicios/consultas (opcional) | Menú (opcional, `menu_url`) | No |
| **Profesionales** | Opcionales (pregunta si hay varios) | No | Obligatorios si hay varios | No | No |
| **Dirección** | No | Solo si hay entregas | No | No | No |
| **Nº personas** | No | No | No | Sí | No |
| **Área preferida** | No | No | No | Sí (`areas`) | No |
| **calendar_id** | Sí | Opcional (solo entregas) | Sí | Sí | Sí |
| **Visita sin cita** | No | Sí (“pásate cuando quieras”) | No | No | No |

\* En store las “citas” son solo para entregas a domicilio si se configura.

---

## 10. Resumen de modificaciones recientes (para tu admin)

1. **Tipo `salon`**  
   - **Genérico**: sirve para **cualquier negocio con servicios + citas** (detailing, taller, spa, centro de servicios, etc.), sin asumir rubro.  
   - Textos neutros; pregunta por profesional solo si hay más de uno.  
   - Listado: “Servicios disponibles” con precios y duración.  
   - El tono y el rubro se definen con `system_prompt_template`.

2. **Tipo `store`**  
   - **Catálogo sin citas obligatorias**: ideal para dealer, concesionario, tienda.  
   - Cliente puede decir “voy a pasar ahora” y el bot responde con horarios y “puedes pasar cuando quieras” **sin** obligar a agendar.  
   - Entregas a domicilio (y por tanto `calendar_id`) son opcionales.

3. **Campos de servicios**  
   - En `salon` (y donde aplique): cada servicio puede llevar `duration_minutes` o `duration` para mostrar duración.

4. **Catálogo en store**  
   - `catalog.categories[]` con `name` y `products[]` (`name`, `price`, `description` opcional).

---

## 11. Checklist por tipo en tu app de admin

### Salon
- [ ] `business_type: "salon"`
- [ ] `calendar_id` configurado
- [ ] `services` con `name`, `price`, `duration_minutes` (o `duration`)
- [ ] `professionals` opcional (vacío, uno o varios; si varios, pueden tener `calendar_id`)
- [ ] `business_hours`, `working_days`, `timezone`, `currency`
- [ ] `system_prompt_template` opcional (ej. detailing, taller)

### Store
- [ ] `business_type: "store"`
- [ ] `catalog.categories` con `name` y `products` (`name`, `price`, `description` opcional)
- [ ] `business_hours`, `working_days`, `timezone`, `currency`
- [ ] `calendar_id` solo si hay entregas a domicilio; si hay, opcionalmente `delivery_hours` y `delivery_duration` (default 60 min)
- [ ] `free_delivery_minimum` opcional
- [ ] `system_prompt_template` opcional (ej. dealer, “puedes pasar cuando quieras”)

### Clinic
- [ ] `business_type: "clinic"`
- [ ] `calendar_id` (general)
- [ ] `professionals` con `id`, `name`, `specialty`; cada uno con `calendar_id` si tienen calendario propio
- [ ] `services` opcional (consultas con precio/duración)
- [ ] `business_hours`, `working_days`, `timezone`

### Restaurant
- [ ] `business_type: "restaurant"`
- [ ] `calendar_id`
- [ ] `areas` (array de strings)
- [ ] `business_hours`, `working_days`, `timezone`
- [ ] `menu_url` opcional. `occasions` no lo usa el bot (solo texto libre); opcional en UI si quieres sugerencias

### General
- [ ] `business_type: "general"`
- [ ] `calendar_id`
- [ ] `business_hours`, `working_days`, `timezone`

---

## 12. Troubleshooting

**El bot usa un lenguaje que no encaja con tu negocio (ej. habla de otro rubro).**  
→ El tipo `salon` es genérico. Usa `system_prompt_template` para definir el rubro y tono (ej. “Eres el asistente de [Nombre]. Hablas de servicios de detailing automotriz…” o el rubro que corresponda).

**En una tienda/dealer el bot pide agendar cita para “ir a ver”.**  
→ Verifica `business_type: "store"`. Con los cambios recientes el bot no debe obligar a agendar para solo informarse o visitar; responde con horarios y “puedes pasar cuando quieras”.

**En una clínica con varios doctores el bot agenda sin profesional.**  
→ Verifica que `business_type: "clinic"` y que `professionals` tenga más de un elemento. El backend valida y no permite agendar sin profesional en ese caso.

**No se muestran servicios o precios.**  
→ En `salon`: revisa que `services` exista y tenga `name` y `price`. En `store`: revisa `catalog.categories` y que cada categoría tenga `products` con `name` y `price`.

**Las fechas u horarios salen mal.**  
→ Revisa `timezone` en `tools_config` (ej. `America/Santo_Domingo`) y que `business_hours` y `working_days` coincidan con el negocio.

Con esta guía puedes configurar desde tu app de admin todos los tipos de negocio y cada detalle de `tools_config` de forma consistente con el comportamiento del bot.
