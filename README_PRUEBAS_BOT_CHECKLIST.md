# Checklist definitivo de pruebas – Bot WhatsApp

Este documento es una **lista de verificación exhaustiva** para probar el bot en todos los tipos de negocio y en escenarios que un usuario real puede vivir: desde lo más simple (saludo, consulta) hasta lo complejo (agendar, modificar, cancelar, confirmar asistencia).  
**Objetivo:** asegurar que todo funcione y no queden imprevistos.

---

## Cómo usar este checklist

1. **Pre-requisitos:** verifica que el entorno esté listo (sección 1).
2. **Pruebas globales:** ejecuta la sección 2 para cualquier cliente (saludo, memoria, correo, errores).
3. **Por tipo de negocio:** según el `business_type` del cliente que estés probando, usa **solo** la sección correspondiente (salon, clinic, store, restaurant, general).
4. Marca cada ítem cuando lo hayas probado y el bot se comporte como se indica.

**Tipos:** `salon` (servicios + citas, profesionales opcionales) · `clinic` (citas médicas, profesional obligatorio si hay varios) · `store` (catálogo; con/sin entregas) · `restaurant` (reservaciones) · `general` (citas básicas sin servicios ni profesionales).

---

## 1. Pre-requisitos (antes de probar)

- [ ] Servidor de la API corriendo (`uvicorn` o `python -m app.main`).
- [ ] Redis corriendo y caché limpia si quieres conversaciones nuevas (`python scripts/clear_redis.py`).
- [ ] Base de datos accesible; cliente de prueba existe y tiene `tools_config` correcto según tipo.
- [ ] WhatsApp conectado (webhook verificado, número de prueba o real).
- [ ] Cliente en DB con `business_name`, `whatsapp_phone_number_id` (o el ID que uses para identificar instancia), y `tools_config` con al menos: `business_type`, `business_hours`, `working_days`; según tipo: `services`, `catalog`, `professionals`, `calendar_id`, `areas`, etc.

---

## 2. Pruebas globales (todos los tipos)

Estas pruebas aplican a **cualquier** cliente. El bot debe comportarse igual en lo básico.

### 2.1 Saludo y primer contacto

- [ ] **Primer mensaje:** Usuario envía "Hola".  
  → Bot saluda, se presenta como asistente del negocio, pregunta en qué puede ayudar. No lista herramientas ni capacidades técnicas.
- [ ] **Segundo mensaje:** Usuario escribe "¿Qué pueden hacer?" o "¿En qué me pueden ayudar?".  
  → Bot responde en lenguaje natural (horarios, citas/reservas/catálogo según tipo), sin enumerar funciones técnicas.

### 2.2 Memoria de conversación

- [ ] Usuario da su nombre en un mensaje; más adelante pregunta algo que requiera nombre (ej. agendar).  
  → Bot no pide el nombre de nuevo si ya lo tiene en contexto.
- [ ] Usuario da su correo en un mensaje; más adelante pide modificar o cancelar.  
  → Bot puede pedir correo para confirmar/envío de confirmación, pero no ignora el historial.

### 2.3 Correo electrónico (prioridad alta)

- [ ] Al **agendar**, el bot pide correo (después del nombre o como segundo dato) y confirma: "Te enviaremos la confirmación a [correo]. ¿Confirmas?" antes de ejecutar.
- [ ] Al **modificar o cancelar**, el bot pide correo **primero** (para enviar confirmación) antes de buscar la cita/reserva.
- [ ] Tras crear/modificar/cancelar, el bot confirma explícitamente que enviará o envió la confirmación a [correo].

### 2.4 Confirmación de asistencia (email de recordatorio)

- [ ] Usuario recibe mensaje de confirmación con "Responde **SÍ** para confirmar / **NO** para cancelar / **CAMBIAR** para reagendar".
- [ ] Usuario responde "Sí", "confirmo", "ok", "sí confirmo", etc.  
  → Bot usa **confirmar_cita** sin preguntar "¿de qué cita hablas?"; reconoce el contexto del historial.
- [ ] Usuario responde "No" o "cancelar".  
  → Bot pide correo y procede a **cancelar_cita** (o guía a cancelación).
- [ ] Usuario responde "Cambiar" o "reagendar".  
  → Bot pide correo y procede a **modificar_cita** (o guía a reagendar).

### 2.5 Errores y resiliencia

- [ ] Mensaje muy corto o ambiguo ("x", "?").  
  → Bot pide aclaración de forma amable, no responde con error técnico.
- [ ] Si ocurre un error interno (ej. calendario caído), el bot responde algo como "Lo siento, ocurrió un error. Por favor intenta de nuevo" y no expone stack ni detalles técnicos.

### 2.6 Escalar a humano

- [ ] Usuario escribe que quiere hablar con una persona, o está muy molesto, o menciona emergencia (en contexto médico).  
  → Bot usa **escalar_a_humano** (o indica que un humano tomará el caso) y no intenta resolver solo algo crítico.

---

## 3. Checklist por tipo de negocio

Usa **solo la subsección** del tipo que estés probando (`business_type` en `tools_config`).

---

### 3.1 Tipo `salon` (negocio con servicios y citas)

Aplica a: detailing, taller, spa, centro de servicios. Puede tener 0, 1 o varios profesionales; si hay varios, el profesional es **opcional** (calendario general o con profesional específico).

#### Información y servicios

- [ ] Usuario: "¿Qué servicios tienen?" / "¿Qué tienen disponible?" / "Precios".  
  → Bot usa **ver_servicios** y muestra lista de servicios con precio y duración.
- [ ] Usuario pregunta por un servicio concreto (ej. "¿Cuánto cuesta el lavado completo?").  
  → Bot responde con precio/duración (puede usar ver_servicios con contexto).

#### Profesionales (si están configurados)

- [ ] Si hay **varios** profesionales: usuario "Quiero agendar".  
  → En el flujo el bot pregunta si quiere un profesional específico o con quien esté disponible.
- [ ] Usuario: "¿Miguel está disponible?" / "¿Con Miguel?".  
  → Bot usa **ver_profesionales** y/o **buscar_disponibilidad** con profesional y muestra horarios; ofrece agendar con ese profesional.
- [ ] Usuario dice "con quien esté disponible" o no elige profesional.  
  → Bot agenda en calendario general (sin profesional_id) y la cita se crea correctamente.
- [ ] Usuario elige un profesional por nombre.  
  → Bot usa **buscar_disponibilidad** con ese profesional y **crear_cita** con profesional_id; la cita queda asociada al profesional/calendario correcto.

#### Agendar cita

- [ ] Flujo completo: servicio → nombre → correo → (si aplica) profesional → fecha → hora.  
  → Bot pide **correo** y confirma "Te enviaremos la confirmación a [correo]. ¿Confirmas?" antes de crear.
- [ ] Usuario da fecha en lenguaje natural ("mañana", "el lunes").  
  → Bot interpreta y usa la fecha correcta (YYYY-MM-DD) en herramientas.
- [ ] Usuario da hora en lenguaje natural ("11 de la mañana", "3 pm").  
  → Bot convierte a 24h y usa buscar_disponibilidad / crear_cita correctamente.
- [ ] Tras crear, el bot responde tipo "✅ Cita confirmada. Te enviamos la confirmación a [correo]".

#### Ver / modificar / cancelar

- [ ] Usuario: "¿Tengo citas?" / "Mis citas" / "¿Tengo algo agendado?".  
  → Bot usa **ver_mis_citas** y muestra "Tus citas programadas" con fecha, hora, servicio (y profesional si aplica).
- [ ] Usuario quiere **modificar** una cita: da correo, luego indica fecha/hora nueva.  
  → Bot usa **modificar_cita** y confirma la modificación y el envío de confirmación al correo.
- [ ] Usuario quiere **cancelar**: da correo, identifica la cita.  
  → Bot usa **cancelar_cita** y confirma cancelación y confirmación por correo.

#### Casos que no deben romper

- [ ] Hora fuera de horario de atención.  
  → Bot indica que esa hora no está disponible y ofrece horarios dentro del rango.
- [ ] Día no laborable (ej. domingo si working_days es L–S).  
  → Bot indica los días de atención y pide otro día.
- [ ] Slot ya ocupado (hora no disponible en calendario).  
  → Bot indica que no está disponible y muestra otras opciones de horario.

---

### 3.2 Tipo `clinic` (clínica / consultorio)

Profesionales (doctores) pueden ser 1 o varios. Si hay **varios**, el profesional es **obligatorio**: no se puede agendar sin elegir doctor.

#### Información y profesionales

- [ ] Usuario: "¿Qué doctores hay?" / "¿Quién atiende?" / "Especialistas".  
  → Bot usa **ver_profesionales** y muestra lista con especialidad, horarios, ID.
- [ ] Usuario: "¿El Dr. García está disponible?".  
  → Bot usa **buscar_disponibilidad** con profesional_id y muestra horarios; ofrece agendar con ese doctor.

#### Agendar cita (clínica)

- [ ] Si hay **un solo** profesional: flujo nombre → correo → tipo de consulta → fecha → hora.  
  → No es obligatorio preguntar "¿con qué doctor?"; la cita se asocia al único profesional.
- [ ] Si hay **varios** profesionales y el usuario no dice con quién:  
  → Bot **no** agenda; pide elegir profesional (usa ver_profesionales si hace falta) y muestra mensaje tipo "Para agendar tu cita médica, necesito saber con qué profesional te gustaría agendar. Los profesionales disponibles son: ...".
- [ ] Flujo completo con doctor elegido: nombre → correo → tipo de consulta → profesional → fecha → hora.  
  → Bot confirma correo y crea cita; respuesta tipo "🏥 Cita médica confirmada" con doctor, fecha, hora.
- [ ] Usuario da "mañana" / "el martes" y hora en natural.  
  → Bot convierte correctamente y usa las herramientas con fecha/hora válidas.

#### Ver / modificar / cancelar

- [ ] "¿Tengo citas?" / "Mis citas".  
  → Bot usa **ver_mis_citas**; título/tono coherente con cita médica.
- [ ] Modificar cita: correo primero, luego fecha/hora nueva.  
  → **modificar_cita** exitoso; mensaje tipo "🏥 Cita modificada" (tono médico).
- [ ] Cancelar cita: correo primero.  
  → **cancelar_cita** y confirmación por correo.

#### Reglas críticas

- [ ] Bot **nunca** da consejos médicos, diagnósticos ni recetas.
- [ ] Si el usuario menciona emergencia o síntomas graves, el bot escala a humano o recomienda acudir a emergencias.

---

### 3.3 Tipo `store` (tienda / catálogo)

Puede ser **solo catálogo y visita al local** (sin `calendar_id`) o **catálogo + entregas a domicilio** (con `calendar_id`). Si hay entregas, se usa `delivery_hours` y `delivery_duration` para slots.

#### Catálogo e información (todos los stores)

- [ ] Usuario: "¿Qué tienen?" / "¿Qué productos tienen?" / "¿Qué tienen disponible?".  
  → Bot usa **ver_servicios** y muestra **catálogo** (categorías y productos con precios). No debe decir "no hay servicios o productos disponibles" si `catalog` está configurado (y no solo `services: []`).
- [ ] Usuario: "¿Tienen colchones?" / "Precios de almohadas".  
  → Bot usa ver_servicios (con categoría si aplica) y muestra los productos relevantes.
- [ ] Si está configurado `free_delivery_minimum`, el mensaje de catálogo puede incluir envío gratis a partir de X.

#### Visita al local (sin agendar)

- [ ] Usuario: "Quiero ir a ver" / "¿Puedo pasar?" / "Horarios".  
  → Bot da horarios y dice algo como "Puedes pasar cuando quieras" / "Te esperamos". **No** obliga a agendar una cita solo para visitar.

#### Store **sin** entregas (sin `calendar_id`)

- [ ] Usuario: "¿Hacen envíos?" / "¿Entregan?".  
  → Bot indica que **no** tienen entregas a domicilio configuradas y que pueden pasar al local según horarios. **No** ofrece agendar entrega.
- [ ] Usuario pide "agendar entrega" o "quiero que me lleven X".  
  → Bot aclara que no hay entregas y ofrece ir al local o contacto humano si aplica.

#### Store **con** entregas (con `calendar_id`)

- [ ] Al mostrar catálogo o al preguntar por productos, el bot puede mencionar que tienen entrega a domicilio (pago contra entrega).
- [ ] Usuario: "¿Hacen envíos?" / "¿Entregan?".  
  → Bot confirma que sí y ofrece agendar la entrega (nombre, correo, producto, dirección, fecha/hora).
- [ ] Usuario: "Quiero comprar X y que me lo lleven".  
  → Bot recopila: nombre, correo, producto(s), **dirección**, fecha y hora de entrega; confirma "Te enviaremos la confirmación a [correo]. Pago contra entrega." y usa **crear_cita** con **direccion**.
- [ ] **buscar_disponibilidad** para entrega usa horario de **entregas** (`delivery_hours`), no solo business_hours.
- [ ] Tras agendar entrega, respuesta tipo "✅ Entrega agendada" con fecha, hora, producto, dirección.

#### Ver / modificar / cancelar (store con entregas)

- [ ] "¿Tengo entregas?" / "Mis pedidos" / "Mis citas".  
  → Bot usa **ver_mis_citas**; mensaje tipo "Tus entregas programadas".
- [ ] Modificar o cancelar entrega: correo primero; bot usa **modificar_cita** / **cancelar_cita** y confirma envío de confirmación al correo.

---

### 3.4 Tipo `restaurant` (restaurante)

Reservaciones: invitados, área, ocasión. Sin profesionales.

#### Información

- [ ] Usuario: "¿Cómo hago una reserva?" / "Quiero reservar".  
  → Bot inicia flujo: nombre, correo, cantidad de invitados, fecha, hora, área preferida, ocasión (opcional).
- [ ] Si hay **menu_url**: usuario pregunta por menú.  
  → Bot responde con la URL del menú.

#### Reservación

- [ ] Flujo completo: nombre → correo → invitados → fecha → hora → área → ocasión (opcional).  
  → Bot pide correo y confirma "Te enviaremos la confirmación a [correo]. ¿Confirmas?" antes de crear.
- [ ] Fechas/horas en lenguaje natural ("mañana 8 pm", "el sábado a las 2").  
  → Bot interpreta y usa **buscar_disponibilidad** / **crear_cita** correctamente.
- [ ] Tras crear: mensaje tipo "🍽️ Reservación confirmada. Te enviamos la confirmación a [correo]" con personas, área, ocasión si aplica.

#### Ver / modificar / cancelar

- [ ] "¿Tengo reservas?" / "Mis reservaciones".  
  → Bot usa **ver_mis_citas**; mensaje tipo "Tus reservaciones".
- [ ] Modificar: correo primero; luego nueva fecha/hora/área.  
  → **modificar_cita**; mensaje tipo "🍽️ Reservación modificada".
- [ ] Cancelar: correo primero.  
  → **cancelar_cita** y confirmación por correo.

#### Reglas

- [ ] Grupos grandes (ej. 8+ personas): bot puede indicar que para grupos grandes un humano los contactará, o escalar.

---

### 3.5 Tipo `general` (citas básicas)

No hay listado de servicios ni profesionales. Solo: nombre, correo, fecha, hora.

#### Comportamiento esperado

- [ ] Usuario: "¿Qué servicios tienen?" / "¿Qué tienen?".  
  → Bot no muestra lista de servicios (no hay); ofrece agendar una cita básica o dar horarios.
- [ ] Bot **no** pregunta por "servicio" ni "profesional"; solo nombre, correo, fecha, hora.
- [ ] Flujo: nombre → correo → fecha → hora.  
  → **buscar_disponibilidad** para la fecha; **crear_cita** con fecha, hora, servicio genérico (ej. "Cita"); confirmación de correo antes de crear.
- [ ] Respuesta tras crear: tipo "✅ Cita confirmada. Te enviamos la confirmación a [correo]".

#### Ver / modificar / cancelar / confirmar

- [ ] "Mis citas" → **ver_mis_citas**; "Tus citas programadas".
- [ ] Modificar y cancelar: correo primero; **modificar_cita** y **cancelar_cita** funcionan.
- [ ] Respuesta "Sí" / "confirmo" al mensaje de confirmación → **confirmar_cita** sin pedir aclaraciones.

---

## 4. Casos edge y validaciones (todos los tipos)

- [ ] **Fecha pasada:** usuario pide "ayer" o una fecha ya pasada.  
  → Bot no agenda; indica que no puede agendar en fechas pasadas o pide una fecha válida.
- [ ] **Hora ya pasada** (ej. son las 15:00 y pide 10:00 hoy).  
  → Bot indica que esa hora ya pasó y pide otro horario.
- [ ] **Día no laborable:** según `working_days`, si el usuario pide un día que no trabaja el negocio, el bot indica los días de atención y pide otro día.
- [ ] **Hora fuera de horario:** si pide fuera de `business_hours` (o `delivery_hours` en store), el bot indica el rango de horario y ofrece alternativas.
- [ ] **Slot no disponible:** la hora elegida ya está ocupada en el calendario.  
  → Bot indica que no está disponible y muestra otras opciones (o pide otra hora/fecha).
- [ ] **Modificar/cancelar sin correo:** si el usuario intenta modificar o cancelar sin dar correo, el bot pide el correo primero (para enviar confirmación).
- [ ] **Profesional inexistente (clinic/salon):** si el usuario dice un nombre que no coincide con ningún profesional, el bot lista los disponibles y pide elegir uno válido.

---

## 5. Resumen rápido por tipo

| Tipo       | Ver algo          | Agendar                          | Ver citas        | Modificar/Cancelar | Confirmar asistencia |
|-----------|-------------------|-----------------------------------|------------------|--------------------|------------------------|
| **salon** | ver_servicios     | Cita con/sin profesional          | ver_mis_citas    | Sí (correo primero)| Sí                     |
| **clinic**| ver_profesionales | Cita; **profesional obligatorio** si hay varios | ver_mis_citas | Sí (correo primero)| Sí                     |
| **store** | ver_servicios (catálogo) | Solo si hay delivery: entrega con dirección | ver_mis_citas (entregas) | Sí (correo primero)| Sí                     |
| **restaurant** | menu_url si hay | Reservación (personas, área, ocasión) | ver_mis_citas (reservaciones) | Sí (correo primero)| Sí                     |
| **general** | No listado       | Cita básica (nombre, correo, fecha, hora) | ver_mis_citas | Sí (correo primero)| Sí                     |

---

## 6. Después de las pruebas

- Si algo falla: revisa `tools_config` del cliente (campos requeridos por tipo en `README_CONFIG_ADMIN.md` y `README_CONFIG_EJEMPLOS_TIPOS.md`).
- Revisa logs (`logs/app.log` o `./view_logs.sh`) para errores o warnings (ej. ver_servicios sin catalog, cliente no encontrado).
- Para conversaciones nuevas entre pruebas, ejecuta `python scripts/clear_redis.py` (y opcionalmente reinicia Redis si lo necesitas).

Este checklist cubre lo básico y lo complejo por tipo de empresa para que puedas asegurarte de que todo funcione y evitar imprevistos en producción.
