# 💇 Guía: Manejo de Profesionales en Salones de Belleza

Esta guía explica cómo el bot maneja las citas en salones de belleza cuando hay profesionales disponibles, permitiendo tanto citas con profesional específico como citas generales.

---

## 🎯 Objetivo

Permitir que los clientes puedan:
1. **Agendar sin profesional específico** → Cualquier profesional disponible puede atender
2. **Agendar con profesional específico** → Verificar disponibilidad y agendar solo con ese profesional
3. **Consultar disponibilidad de profesionales** → Saber quién está disponible y cuándo

---

## 📋 Estructura del JSON `tools_config` para Salones

### Ejemplo Completo

```json
{
  "business_type": "salon",
  "calendar_id": "salon@example.com",
  "timezone": "America/Santo_Domingo",
  "currency": "$",
  "business_hours": {
    "start": "08:00",
    "end": "18:00"
  },
  "working_days": [1, 2, 3, 4, 5],
  "slot_duration": 30,
  "services": [
    {
      "name": "Corte de pelo",
      "price": 500,
      "duration_minutes": 60
    },
    {
      "name": "Tinte",
      "price": 1500,
      "duration_minutes": 120
    }
  ],
  "professionals": [
    {
      "id": "prof_1769641947174",
      "name": "Miguel",
      "specialty": "Peluquero",
      "calendar_id": "miguel@example.com",
      "slot_duration": 60,
      "business_hours": {
        "start": "08:00",
        "end": "17:00"
      }
    },
    {
      "id": "prof_1769641961246",
      "name": "Matias",
      "specialty": "Peluquero"
    }
  ]
}
```

### Campos Importantes

#### `professionals` (Array)

Cada profesional puede tener:

- **`id`** (requerido): Identificador único del profesional
- **`name`** (requerido): Nombre del profesional
- **`specialty`** (opcional): Especialidad (ej: "Peluquero", "Colorista")
- **`calendar_id`** (opcional): Calendario específico del profesional
  - Si **NO** tiene `calendar_id`: Se usa el `calendar_id` general del salón
  - Si **SÍ** tiene `calendar_id`: Se usa ese calendario específico para verificar disponibilidad
- **`slot_duration`** (opcional): Duración de slots para este profesional (sobrescribe el general)
- **`business_hours`** (opcional): Horario específico del profesional (sobrescribe el general)

---

## 🔄 Flujo de Agendamiento

### Caso 1: Cliente NO quiere profesional específico

```
1. Cliente: "Quiero agendar un corte de pelo"
2. Bot: "¿Te gustaría agendar con algún profesional en específico o con quien esté disponible?"
3. Cliente: "Con quien esté disponible" o "No importa" o "Cualquiera"
4. Bot: Usa crear_cita SIN profesional_id
   → Se agenda en el calendario general del salón (calendar_id principal)
   → Cualquier profesional disponible puede atender
```

**JSON enviado a `crear_cita`:**
```json
{
  "fecha": "2026-01-30",
  "hora": "14:00",
  "servicio": "Corte de pelo",
  "email": "cliente@example.com"
  // NO incluye profesional_id
}
```

### Caso 2: Cliente SÍ quiere profesional específico

```
1. Cliente: "Quiero agendar un corte de pelo"
2. Bot: "¿Te gustaría agendar con algún profesional en específico o con quien esté disponible?"
3. Cliente: "Con Miguel" o "Miguel está disponible?"
4. Bot: Verifica disponibilidad con buscar_disponibilidad(profesional_id="Miguel")
5. Bot: Muestra horarios disponibles de Miguel
6. Cliente: "A las 14:00"
7. Bot: Usa crear_cita CON profesional_id="Miguel"
   → Se agenda en el calendario específico de Miguel (si tiene) o general con nota
   → Solo Miguel puede atender esta cita
```

**JSON enviado a `crear_cita`:**
```json
{
  "fecha": "2026-01-30",
  "hora": "14:00",
  "servicio": "Corte de pelo",
  "profesional_id": "Miguel",
  "email": "cliente@example.com"
}
```

### Caso 3: Cliente pregunta disponibilidad antes de agendar

```
1. Cliente: "¿Miguel está disponible?"
2. Bot: Usa ver_profesionales para mostrar info de Miguel
3. Bot: "Sí, Miguel está disponible. Su horario es de 8:00 a 17:00. ¿Te gustaría agendar una cita con él?"
4. Cliente: "Sí"
5. Bot: Usa buscar_disponibilidad(profesional_id="Miguel", fecha="2026-01-30")
6. Bot: Muestra horarios disponibles
7. Cliente: Selecciona horario
8. Bot: Usa crear_cita con profesional_id="Miguel"
```

---

## 🛠️ Implementación Técnica

### 1. Verificar Disponibilidad de Profesional

El bot usa `buscar_disponibilidad` con `profesional_id`:

```python
# En app/agents/tools/definitions.py

async def _buscar_disponibilidad(self, args: dict) -> str:
    profesional_id = args.get("profesional_id")
    
    if profesional_id and self.config.get("professionals"):
        # Buscar profesional
        prof = next((p for p in self.config["professionals"] 
                    if profesional_id.lower() in p.get("name", "").lower()), None)
        
        if prof:
            # Usar calendario del profesional si tiene, sino el general
            calendar_id = prof.get("calendar_id") or self.calendar_id
            # Obtener slots disponibles
            slots = await calendar_service.get_available_slots(...)
```

### 2. Crear Cita con o sin Profesional

```python
# En app/agents/tools/definitions.py

async def _crear_cita(self, args: dict) -> str:
    profesional_id = args.get("profesional_id")  # Puede ser None
    
    # Si hay profesional_id, buscar y configurar
    if profesional_id and self.config.get("professionals"):
        prof = # ... buscar profesional ...
        if prof:
            # Si tiene calendario propio, usarlo
            if prof.get("calendar_id"):
                calendar_id = prof.get("calendar_id")
            # Marcar en descripción
            descripcion_extra = f"\nProfesional: {prof['name']}"
    
    # Si NO hay profesional_id, usar calendario general
    # calendar_id ya está configurado como self.calendar_id
```

### 3. Verificación de Disponibilidad Antes de Crear

El bot **SIEMPRE** verifica disponibilidad antes de crear la cita:

```python
# Verificar disponibilidad del slot específico
slots_disponibles = await calendar_service.get_available_slots(
    calendar_id=calendar_id,  # Del profesional o general
    date=fecha_date,
    duration_minutes=duration,
    config=config_for_calendar
)

# Verificar si el horario solicitado está disponible
hora_solicitada = fecha.strftime('%H:%M')
slot_disponible = any(slot['start'] == hora_solicitada for slot in slots_disponibles)

if not slot_disponible:
    return f"❌ Lo siento, el horario {hora_solicitada} no está disponible..."
```

---

## 📝 Reglas del Bot para Salones

### Siempre Preguntar por Profesional

El bot **SIEMPRE** pregunta:
> "¿Te gustaría agendar con algún profesional en específico o con quien esté disponible?"

**Razón:** Permite al cliente elegir, pero no es obligatorio especificar profesional.

### Manejo de Respuestas

| Respuesta del Cliente | Acción del Bot |
|----------------------|----------------|
| "Con Miguel" / "Miguel" | Busca profesional "Miguel", verifica disponibilidad, agenda con él |
| "Con quien esté disponible" / "No importa" / "Cualquiera" | Agenda sin `profesional_id`, usa calendario general |
| "¿Miguel está disponible?" | Muestra info de Miguel, pregunta si quiere agendar con él |
| "¿Y Matías?" | Muestra info de Matías, ofrece elegir entre ambos |

### Verificación de Disponibilidad

- **Con profesional específico:** Verifica disponibilidad en su calendario (o general si no tiene)
- **Sin profesional específico:** Verifica disponibilidad en calendario general
- **Antes de confirmar:** Siempre verifica que el slot esté disponible

---

## 🎨 Ejemplos de Conversación

### Ejemplo 1: Sin Profesional Específico

```
Cliente: Quiero agendar un corte de pelo
Bot: ¿Te gustaría agendar con algún profesional en específico o con quien esté disponible?
Cliente: Con quien esté disponible
Bot: Perfecto. ¿Para qué fecha te gustaría?
Cliente: Mañana a las 2pm
Bot: [Verifica disponibilidad en calendario general]
Bot: ✅ Cita confirmada para mañana a las 14:00...
```

### Ejemplo 2: Con Profesional Específico

```
Cliente: Quiero agendar un corte de pelo
Bot: ¿Te gustaría agendar con algún profesional en específico o con quien esté disponible?
Cliente: Con Miguel
Bot: [Verifica disponibilidad de Miguel]
Bot: Miguel tiene disponibles estos horarios para mañana:
     • 09:00 - 10:00
     • 14:00 - 15:00
     • 16:00 - 17:00
Cliente: A las 2pm
Bot: ✅ Cita confirmada con Miguel para mañana a las 14:00...
```

### Ejemplo 3: Consulta de Disponibilidad

```
Cliente: ¿Miguel está disponible?
Bot: Sí, Miguel está disponible. Su horario es de 8:00 a 17:00.
     ¿Te gustaría agendar una cita con él?
Cliente: Sí
Bot: ¿Para qué fecha?
Cliente: Mañana
Bot: [Busca disponibilidad de Miguel para mañana]
Bot: Miguel tiene disponibles estos horarios para mañana...
```

---

## ⚙️ Configuración en tu App de Gestión

### Al Crear/Actualizar Cliente (Salón)

```javascript
// En tu app de gestión (Next.js)

const salonConfig = {
  business_type: "salon",
  calendar_id: "salon@example.com",  // Calendario general del salón
  timezone: "America/Santo_Domingo",
  currency: "$",
  business_hours: {
    start: "08:00",
    end: "18:00"
  },
  working_days: [1, 2, 3, 4, 5],
  slot_duration: 30,
  services: [
    {
      name: "Corte de pelo",
      price: 500,
      duration_minutes: 60
    }
  ],
  professionals: [
    {
      id: "prof_1769641947174",
      name: "Miguel",
      specialty: "Peluquero",
      // Opcional: calendar_id específico (si el profesional tiene su propio calendario)
      // calendar_id: "miguel@example.com",
      // Opcional: horario específico
      // business_hours: { start: "08:00", end: "17:00" }
    },
    {
      id: "prof_1769641961246",
      name: "Matias",
      specialty: "Peluquero"
      // Sin calendar_id → usa el calendario general del salón
    }
  ]
};

// Guardar en tools_config del cliente
await updateClient(clientId, {
  tools_config: salonConfig
});
```

### Opciones de Configuración

#### Opción A: Profesionales con Calendarios Propios

```json
{
  "professionals": [
    {
      "id": "prof_1",
      "name": "Miguel",
      "calendar_id": "miguel@example.com"  // ← Calendario específico
    }
  ]
}
```

**Ventaja:** Disponibilidad independiente por profesional  
**Uso:** Cada profesional gestiona su propio calendario

#### Opción B: Profesionales Compartiendo Calendario General

```json
{
  "professionals": [
    {
      "id": "prof_1",
      "name": "Miguel"
      // Sin calendar_id → usa calendar_id del salón
    }
  ]
}
```

**Ventaja:** Más simple, un solo calendario  
**Uso:** Todos los profesionales comparten el mismo calendario

---

## 🔍 Verificación de Disponibilidad

### Con `calendar_id` Específico del Profesional

```
Profesional: Miguel
calendar_id profesional: miguel@example.com
→ Verifica disponibilidad en miguel@example.com
```

### Sin `calendar_id` Específico

```
Profesional: Matias
Sin calendar_id
→ Verifica disponibilidad en calendar_id general del salón
→ Pero marca en la descripción: "Profesional: Matias"
```

---

## ✅ Checklist de Implementación

- [ ] Configurar `business_type: "salon"` en `tools_config`
- [ ] Agregar array `professionals` con al menos `id` y `name`
- [ ] Configurar `calendar_id` general del salón
- [ ] (Opcional) Configurar `calendar_id` específico para cada profesional
- [ ] Configurar `services` con duraciones
- [ ] Probar agendamiento sin profesional específico
- [ ] Probar agendamiento con profesional específico
- [ ] Probar consulta de disponibilidad de profesionales
- [ ] Verificar que el bot siempre pregunta por profesional específico

---

## 🆘 Troubleshooting

### El bot no pregunta por profesional específico

**Solución:** Verifica que `business_type: "salon"` y que exista el array `professionals` en `tools_config`.

### No encuentra al profesional cuando se especifica

**Solución:** Verifica que el `name` en `professionals` coincida exactamente (case-insensitive) con lo que dice el cliente.

### No verifica disponibilidad del profesional específico

**Solución:** Verifica que el profesional tenga `calendar_id` o que el `calendar_id` general esté configurado.

### Agenda en calendario incorrecto

**Solución:** 
- Si el profesional tiene `calendar_id`, se usa ese
- Si NO tiene `calendar_id`, se usa el `calendar_id` general del salón
- Verifica que ambos calendarios estén correctamente configurados

---

**¿Preguntas?** Revisa el código en `app/agents/tools/definitions.py` y `app/services/gemini.py` para entender mejor la implementación.
