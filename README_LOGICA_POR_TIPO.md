# Lógica del agente por tipo de negocio

Cada agente **actúa distinto según `business_type`** no solo por el texto del `system_prompt` (personalidad), sino por **lógica real en código**: validaciones, cálculo de slots, mensajes de respuesta y plantillas de email. Este README resume **qué cambia en la lógica** por tipo.

---

## 1. Resumen: ¿qué cambia por tipo?

| Aspecto | Dónde | salon | store | clinic | restaurant | general |
|--------|--------|------|-------|--------|------------|---------|
| **Validación al crear cita** | definitions.py | Profesional opcional | — | **Profesional obligatorio** si hay varios | — | — |
| **Cálculo de slots** | definitions.py | `slot_duration`, servicio, profesional | **`delivery_hours`**, **`delivery_duration`** | Por profesional/servicio | Horario normal | Horario normal |
| **Mensaje al crear cita** | definitions.py | "Cita confirmada" | **"Entrega agendada"** + dirección | **"Cita médica confirmada"** + doctor | **"Reservación confirmada"** + personas/área/ocasión | "Cita confirmada" |
| **Texto "Ver mis citas"** | definitions.py | "Tus citas programadas" | **"Tus entregas programadas"** | "Tus citas programadas" | **"Tus reservaciones"** | "Tus citas programadas" |
| **Mensaje al modificar** | definitions.py | Genérico | Genérico | **"Cita modificada"** (tono médico) | **"Reservación modificada"** (tono restaurante) | Genérico |
| **Email de confirmación** | email_service.py | Plantilla "Cita" | — | Plantilla **"Cita médica"** | Plantilla **"Reservación"** | Plantilla "Cita" |
| **Instrucciones de flujo** | gemini.py | Servicio + profesional opcional | No obligar cita para visitar; entregas solo si compra | Profesional **obligatorio** si hay varios | Invitados, área, ocasión; tono restaurante | Citas básicas |

Las **mismas herramientas** (ver_servicios, crear_cita, buscar_disponibilidad, etc.) existen para todos; lo que cambia es el **comportamiento interno** según `business_type` y `tools_config`.

---

## 2. Lógica en código (definitions.py)

### 2.1 `ver_servicios`

- Si `tools_config` tiene **`services`** (salon, clinic): lista servicios con precio y duración.
- Si tiene **`catalog`** (store): lista categorías y productos; si existe `free_delivery_minimum`, lo añade al final.
- Si tiene **`menu_url`** (restaurant): responde con la URL del menú.

El **mismo nombre de herramienta** devuelve contenido distinto según la configuración del cliente.

---

### 2.2 `buscar_disponibilidad`

- **salon / clinic / general:**  
  - Usa `slot_duration`, calendario del profesional si hay `profesional_id`, y duración del **servicio** si viene `servicio` y hay `services`.
- **store:**  
  - Usa **`delivery_duration`** (default 60 min) y **`delivery_hours`** (si no hay, usa `business_hours`).  
  - Solo aplica cuando hay `calendar_id` (entregas a domicilio).

Así, en store los slots son para **entregas** (horario y duración de entrega), no para “visita al local”.

---

### 2.3 `crear_cita`

**Validaciones:**

- **clinic:** Si hay **varios** profesionales en `tools_config` y no se envía `profesional_id`, el backend **no crea la cita** y devuelve un mensaje pidiendo elegir profesional. En salon no es obligatorio.

**Datos que se usan según tipo:**

- **store:**  
  - Duración del slot = `delivery_duration`.  
  - Si viene `direccion`, se guarda en datos del cliente y se muestra en la confirmación (entrega a domicilio).

**Mensaje de éxito (respuesta al usuario):**

- **store:** `"✅ Entrega agendada"` + fecha, hora, servicio, dirección.
- **restaurant:** `"🍽️ Reservación confirmada"` + fecha, hora, número de personas, área, ocasión.
- **clinic:** `"🏥 Cita médica confirmada"` + fecha, hora, servicio, nombre del profesional.
- **salon / general:** `"✅ Cita confirmada"` + fecha, hora, servicio.

La lógica de “qué es una cita” (cita vs entrega vs reservación vs cita médica) está en código, no solo en el prompt.

---

### 2.4 `ver_mis_citas`

- **store:** Título **"Tus entregas programadas"**.
- **restaurant:** Título **"Tus reservaciones"**.
- Resto: **"Tus citas programadas"**.

---

### 2.5 `modificar_cita`

Tras modificar correctamente, el mensaje al usuario depende del tipo:

- **restaurant:** `"🍽️ Reservación modificada"` + tono restaurante.
- **clinic:** `"🏥 Cita modificada"` + profesional si aplica.
- **salon / store / general:** `"✅ Cita modificada"` genérico.

---

## 3. Lógica en instrucciones (gemini.py – system prompt)

El system prompt se **arma por `business_type`**: se añaden bloques distintos de instrucciones. Eso define el **flujo** que debe seguir el LLM (qué preguntar, en qué orden, qué no hacer). No es solo “personalidad”, es lógica de flujo.

- **salon:**  
  - Flujo: servicio → nombre → correo → (si hay varios profesionales) “¿con quién o quien esté disponible?” → fecha → hora.  
  - Profesional **opcional**; se puede agendar sin `profesional_id` (calendario general).

- **clinic:**  
  - Flujo: nombre → correo → tipo de consulta → **profesional (obligatorio si hay varios)** → fecha → hora.  
  - Se indica explícitamente que **no** puede agendar sin elegir profesional cuando hay múltiples.

- **store:**  
  - Instrucciones: no obligar a agendar cita para “ir a ver” o solo informarse; horarios + “puedes pasar cuando quieras”.  
  - Agendar solo para **entregas a domicilio** (compra + entrega).

- **restaurant:**  
  - Flujo: nombre → correo → cantidad de invitados → fecha → hora → área preferida → ocasión (opcional).  
  - Sin profesionales; tono reservación/restaurante.

- **general:**  
  - Citas básicas: nombre, correo, fecha, hora. Sin servicios ni profesionales.

Si cambias el `business_type` en `tools_config`, cambia el bloque de instrucciones que se inyecta y, por tanto, el flujo que sigue el agente.

---

## 4. Emails (email_service.py)

Las plantillas de correo también dependen de `business_type`:

- **restaurant:** Asunto y cuerpo de **reservación** (ej. “Confirmación de Reservación”, “Reservación Modificada”).
- **clinic:** Asunto y cuerpo de **cita médica** (ej. “Confirmación de Cita Médica”).
- **salon (y resto):** Asunto y cuerpo de **cita** genérica (ej. “Confirmación de Cita”).

Misma acción (confirmar/modificar), distinto texto según tipo.

---

## 5. Conclusión

- **Sí:** cada agente está configurado según el tipo de negocio.
- **No** es solo el `system_prompt` (personalidad): la **lógica** cambia en:
  - **Backend (definitions.py):** validaciones (clinic obliga profesional), cálculo de slots (store = delivery_*), mensajes de éxito y listados por tipo.
  - **Prompt (gemini.py):** flujos y reglas por tipo (qué preguntar, qué es obligatorio, qué no hacer).
  - **Emails (email_service.py):** plantillas por tipo.

Por eso cada tipo “actúa diferente”: mismo conjunto de herramientas, distinto comportamiento interno y distinto flujo de conversación según `business_type` y `tools_config`.
