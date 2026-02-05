# 📋 Changelog - Mejoras al Bot de WhatsApp

## Versión 2.1.0 - Febrero 2026

### 🏥 Mejoras para Clínicas/Consultorios

#### 1. Información Detallada de Profesionales
Ahora cada profesional muestra en el bot:
- **Precio de consulta** individual (ej: RD$1,500)
- **Días de trabajo** específicos (ej: Lun, Mar, Vie)
- **Horario individual** (ej: 07:00 - 18:00)
- **Duración de cita** (ej: 60 min)

**Configuración en Panel Admin:**
```json
{
  "professionals": [
    {
      "id": "prof-1",
      "name": "Dra. García",
      "specialty": "Odontología",
      "consultation_price": 1500,
      "working_days": [1, 2, 5],
      "business_hours": {"start": "07:00", "end": "18:00"},
      "slot_duration": 60
    }
  ]
}
```

#### 2. Requisito de Seguro Médico
Nueva opción `requires_insurance` que cuando está activa:
- El bot pregunta automáticamente si el paciente tiene seguro
- Pregunta qué tipo de seguro (ARS, privado, etc.)

**Configuración:**
```json
{
  "requires_insurance": true
}
```

#### 3. System Prompt con Prioridad Máxima
El prompt personalizado del negocio ahora tiene **prioridad absoluta**:
- Aparece al final del sistema de instrucciones
- Si hay conflicto, las instrucciones del dueño ganan
- Útil para excepciones (ej: "La Dra. X no acepta seguro")

---

### 💅 Mejoras para Salones/Servicios

#### Catálogo Priorizado
- Los productos del catálogo ahora tienen prioridad sobre servicios genéricos
- Servicios placeholder (precio $0, nombre "Servicio") son ignorados automáticamente

---

### 🔧 Campos de Configuración Soportados

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `requires_insurance` | boolean | Activa pregunta de seguro médico |
| `professionals[].consultation_price` | number | Precio de consulta por doctor |
| `professionals[].working_days` | array | Días de trabajo [1-7] |
| `professionals[].business_hours` | object | Horario individual |
| `professionals[].slot_duration` | number | Duración de cita en minutos |

---

### 📱 Para el Panel de Administración

#### Formulario de Profesionales
Añadir campos para:
- [ ] Precio de consulta (`consultation_price`)
- [ ] Días de trabajo (`working_days`) - selector múltiple
- [ ] Horario individual (`business_hours.start`, `business_hours.end`)
- [ ] Duración de slot (`slot_duration`)

#### Configuración General
Añadir toggle para:
- [ ] Requiere seguro médico (`requires_insurance`)

#### System Prompt
El textarea de "Personalidad del Bot" ahora tiene prioridad máxima sobre todas las reglas automáticas.
