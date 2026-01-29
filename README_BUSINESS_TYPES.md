# 🏢 Guía Completa: Tipos de Negocio y Casos de Uso

Esta guía explica cómo funciona cada tipo de negocio y cómo configurarlos correctamente en tu app de gestión.

---

## 📋 Tipos de Negocio Soportados

1. **`salon`** - Salón de Belleza
2. **`clinic`** - Clínica Médica
3. **`store`** - Tienda/Ventas
4. **`restaurant`** - Restaurante
5. **`general`** - Negocio General (sin tipo específico)

---

## 💇 SALÓN DE BELLEZA (`salon`)

### Características Principales

- **Profesionales:** OPCIONALES (puede agendar con o sin profesional específico)
- **Servicios:** Cortes, tintes, tratamientos, etc.
- **Flujo:** Cliente puede elegir profesional específico O cualquier profesional disponible

### Flujo de Agendamiento

```
1. Cliente: "Quiero un corte de pelo"
2. Bot: "¿Te gustaría agendar con algún profesional en específico o con quien esté disponible?"
3. Cliente puede responder:
   - "Con Miguel" → Verifica disponibilidad de Miguel → Agenda con él
   - "Con quien esté disponible" → Agenda en calendario general → Cualquiera puede atender
```

### Configuración JSON

```json
{
  "business_type": "salon",
  "calendar_id": "salon@example.com",
  "services": [
    {
      "name": "Corte de pelo",
      "price": 500,
      "duration_minutes": 60
    }
  ],
  "professionals": [
    {
      "id": "prof_1",
      "name": "Miguel",
      "specialty": "Peluquero"
      // calendar_id opcional - si no tiene, usa el general
    }
  ]
}
```

### Reglas Importantes

- ✅ **SIEMPRE pregunta** si quiere profesional específico
- ✅ Permite agendar **sin profesional** (usa calendario general)
- ✅ Permite agendar **con profesional** (verifica disponibilidad)
- ✅ Si pregunta "¿Miguel está disponible?", muestra info y horarios

---

## 🏥 CLÍNICA MÉDICA (`clinic`)

### Características Principales

- **Profesionales:** **OBLIGATORIOS** si hay múltiples doctores
- **Servicios:** Consultas médicas, especialidades
- **Flujo:** Cliente **DEBE** especificar con qué doctor quiere agendar

### Flujo de Agendamiento

```
1. Cliente: "Quiero agendar una cita"
2. Bot: "¿Con qué doctor te gustaría agendar?"
   → Muestra lista de doctores disponibles
3. Cliente: "Con el Dr. García"
4. Bot: Verifica disponibilidad del Dr. García
5. Bot: Muestra horarios disponibles
6. Cliente: Selecciona horario
7. Bot: Agenda la cita
```

### Configuración JSON

```json
{
  "business_type": "clinic",
  "calendar_id": "clinica@example.com",
  "professionals": [
    {
      "id": "doc_1",
      "name": "Dr. García",
      "specialty": "Cardiología",
      "calendar_id": "drgarcia@example.com"  // Cada doctor tiene su calendario
    },
    {
      "id": "doc_2",
      "name": "Dra. López",
      "specialty": "Pediatría",
      "calendar_id": "drlopez@example.com"
    }
  ]
}
```

### Reglas Importantes

- ⚠️ **NO puede agendar sin especificar doctor** si hay múltiples profesionales
- ✅ **SIEMPRE pregunta** con qué doctor quiere agendar
- ✅ Si hay solo 1 profesional, puede omitir la pregunta
- ✅ Cada doctor puede tener su propio `calendar_id` para disponibilidad independiente

### Validación Automática

El bot **rechazará** intentos de agendar sin profesional si hay múltiples:

```
Cliente intenta agendar sin especificar doctor
→ Bot: "Para agendar tu cita médica, necesito saber con qué profesional te gustaría agendar. 
       Los profesionales disponibles son: Dr. García, Dra. López. ¿Con cuál te gustaría?"
```

---

## 🛒 TIENDA/VENTAS (`store`)

### Características Principales

- **NO es sobre agendar citas con profesionales**
- **Es sobre:** Responder preguntas del catálogo de productos
- **Entrega:** Si el cliente quiere comprar, se agenda una entrega/ruta
- **Pago:** Contra entrega (no se cobra antes)

### Flujo Principal

#### 1. Consulta de Productos

```
Cliente: "¿Qué productos tienen?"
Bot: Usa ver_servicios → Muestra catálogo completo

Cliente: "¿Tienen colchones?"
Bot: Usa ver_servicios con categoria="colchones" → Muestra solo colchones
```

#### 2. Compra/Entrega

```
Cliente: "Quiero comprar un colchón"
Bot: "¿Te gustaría que te lo llevemos a domicilio? Es pago contra entrega"
Cliente: "Sí"
Bot: Recopila:
   - Nombre completo
   - Email
   - Producto(s)
   - Dirección de entrega
   - Fecha y hora de entrega
Bot: "✅ Entrega agendada. El pago será contra entrega cuando recibas el producto."
```

### Configuración JSON

```json
{
  "business_type": "store",
  "calendar_id": "rutas@example.com",  // Calendario de rutas/entregas
  "currency": "$",
  "delivery_hours": {
    "start": "09:00",
    "end": "18:00"
  },
  "delivery_duration": 60,  // Duración estimada de entrega
  "catalog": {
    "categories": [
      {
        "name": "Colchones",
        "products": [
          {
            "name": "Colchón Ortopédico",
            "price": 5000,
            "description": "Colchón de alta calidad..."
          }
        ]
      },
      {
        "name": "Almohadas",
        "products": [
          {
            "name": "Almohada Memory Foam",
            "price": 800
          }
        ]
      }
    ]
  },
  "free_delivery_minimum": 3000  // Envío gratis en compras mayores a $3000
}
```

### Reglas Importantes

- ✅ **NO agendar entregas** sin que el cliente exprese interés en comprar
- ✅ **SIEMPRE mencionar** "pago contra entrega" al agendar entrega
- ✅ Usar `ver_servicios` para responder preguntas sobre productos
- ✅ Las entregas se agendan en el calendario de rutas
- ✅ Si preguntan por financiamiento complejo → escalar a humano

### Herramientas Usadas

- **`ver_servicios`**: Para mostrar catálogo de productos
- **`crear_cita`**: Para agendar entrega (con `direccion` requerida)

---

## 🍽️ RESTAURANTE (`restaurant`)

### Características Principales

- **Reservaciones:** Mesas, no citas con profesionales
- **Datos requeridos:** Número de personas, área preferida, ocasión especial
- **Flujo:** Similar a salón pero enfocado en experiencia gastronómica

### Flujo de Reservación

```
1. Cliente: "Quiero hacer una reservación"
2. Bot recopila:
   - Nombre completo
   - Email
   - Número de personas
   - Fecha
   - Hora
   - Área preferida (Terraza/Salón)
   - Ocasión especial (opcional)
3. Bot confirma reservación
```

### Configuración JSON

```json
{
  "business_type": "restaurant",
  "calendar_id": "restaurante@example.com",
  "currency": "$",
  "business_hours": {
    "start": "12:00",
    "end": "23:00"
  },
  "working_days": [1, 2, 3, 4, 5, 6],
  "areas": ["Terraza", "Salón principal", "VIP"],
  "occasions": ["Cumpleaños", "Aniversario", "Reunión de negocios"]
}
```

### Reglas Importantes

- ✅ Pregunta por área preferida si hay múltiples áreas
- ✅ Pregunta por ocasión especial (opcional pero recomendado)
- ✅ Grupos grandes (8+ personas) → escalar a humano
- ✅ Tono cordial y elegante

---

## 📊 Comparación de Casos de Uso

| Característica | Salón | Clínica | Tienda | Restaurante |
|---------------|-------|---------|--------|-------------|
| **Profesionales** | Opcional | Obligatorio* | No aplica | No aplica |
| **Servicios** | Sí (cortes, tintes) | Sí (consultas) | No (productos) | No (menú) |
| **Catálogo** | No | No | Sí | No |
| **Dirección** | No | No | Sí (entrega) | No |
| **Personas** | No | No | No | Sí |
| **Área** | No | No | No | Sí |
| **Pago** | En el salón | En la clínica | Contra entrega | En el restaurante |

*Obligatorio solo si hay múltiples profesionales

---

## 🔧 Configuración en tu App de Gestión

### Para Salones

```javascript
const salonConfig = {
  business_type: "salon",
  calendar_id: "salon@example.com",
  services: [...],
  professionals: [
    // Opcional: puede tener profesionales o no
    // Si tiene profesionales, pregunta pero permite "cualquiera"
  ]
};
```

### Para Clínicas

```javascript
const clinicConfig = {
  business_type: "clinic",
  calendar_id: "clinica@example.com",
  professionals: [
    // OBLIGATORIO si hay múltiples doctores
    // Cada doctor DEBE tener calendar_id propio
  ]
};
```

### Para Tiendas

```javascript
const storeConfig = {
  business_type: "store",
  calendar_id: "rutas@example.com",  // Calendario de entregas
  catalog: {
    categories: [
      {
        name: "Categoría",
        products: [...]
      }
    ]
  },
  delivery_hours: {...},
  delivery_duration: 60
};
```

### Para Restaurantes

```javascript
const restaurantConfig = {
  business_type: "restaurant",
  calendar_id: "restaurante@example.com",
  areas: ["Terraza", "Salón"],
  occasions: ["Cumpleaños", "Aniversario"]
};
```

---

## ✅ Checklist por Tipo de Negocio

### Salón ✅
- [ ] `business_type: "salon"`
- [ ] `services` configurados con precios y duraciones
- [ ] `professionals` opcionales (si hay)
- [ ] `calendar_id` general del salón
- [ ] Bot pregunta por profesional pero permite "cualquiera"

### Clínica ✅
- [ ] `business_type: "clinic"`
- [ ] `professionals` con `calendar_id` propio cada uno
- [ ] Bot **obliga** a especificar profesional si hay múltiples
- [ ] Validación automática rechaza agendamiento sin profesional

### Tienda ✅
- [ ] `business_type: "store"`
- [ ] `catalog` con categorías y productos
- [ ] `calendar_id` para rutas/entregas
- [ ] `delivery_hours` y `delivery_duration` configurados
- [ ] Bot usa `ver_servicios` para mostrar catálogo
- [ ] Bot menciona "pago contra entrega" al agendar

### Restaurante ✅
- [ ] `business_type: "restaurant"`
- [ ] `areas` configuradas
- [ ] `occasions` opcionales
- [ ] Bot pregunta por número de personas y área

---

## 🆘 Troubleshooting

### El bot permite agendar sin profesional en una clínica con múltiples doctores

**Solución:** Verifica que `business_type: "clinic"` y que el array `professionals` tenga más de 1 elemento. El bot validará automáticamente.

### El bot no muestra el catálogo en una tienda

**Solución:** Verifica que `catalog.categories` esté configurado y que el bot use `ver_servicios` cuando preguntan por productos.

### El bot no menciona "pago contra entrega" en tiendas

**Solución:** Verifica que `business_type: "store"` esté correctamente configurado. El bot lo mencionará automáticamente.

---

**¿Preguntas?** Revisa los READMEs específicos:
- `README_SALON_PROFESSIONALS.md` - Para salones
- `README_BACKEND_ARCHITECTURE.md` - Arquitectura general
