# 📱 Guía de Integración: Panel Admin con Bot WhatsApp

Esta guía explica cómo integrar tu panel admin (Next.js) con el bot de WhatsApp para permitir intervención humana directa desde el mismo número.

## ⚠️ PROBLEMA COMÚN: Mensaje en Redis pero NO en WhatsApp

Si tu mensaje aparece en Redis pero NO llega a WhatsApp, el problema es que **no se está enviando realmente a la API de WhatsApp**. Revisa la sección [Troubleshooting](#-troubleshooting) al final de este documento.

---

## 🎯 Objetivo

Permitir que los administradores respondan directamente a los clientes desde el panel admin usando el **mismo número de WhatsApp del bot**, pausando automáticamente la IA mientras el humano está respondiendo.

---

## 🔄 Flujo de Intervención Humana

```
1. Cliente escribe mensaje → Bot recibe en webhook
2. Bot verifica Redis: ¿Hay intervención humana activa?
   ├─ NO → Bot responde con IA normalmente
   └─ SÍ → Bot guarda mensaje pero NO responde (IA pausada)
3. Admin ve mensaje en panel → Responde desde panel
4. Panel envía mensaje por WhatsApp API → Guarda en Redis como "human"
5. Cliente responde → Bot detecta "human_handled" → NO responde
6. Admin termina → Marca conversación como resuelta → IA se reanuda
```

---

## 🔑 Conceptos Clave

### Estados en Redis

El bot usa Redis para gestionar el estado de las conversaciones:

- **`active`**: Conversación normal, IA responde automáticamente
- **`human_handled`**: Admin está respondiendo, IA pausada
- **`escalated`**: Conversación escalada (similar a human_handled)

### Keys en Redis

Para cada conversación, el bot guarda:

```
{client_id}:{phone_number}:messages     → Historial de mensajes
{client_id}:{phone_number}:status       → Estado (active/human_handled/escalated)
{client_id}:{phone_number}:admin        → Nombre del admin que está respondiendo
{client_id}:{phone_number}:sent_messages → IDs de mensajes enviados por el bot
```

---

## 📡 API de WhatsApp (Meta)

Tu panel admin necesita enviar mensajes usando la **API oficial de Meta WhatsApp Business**.

### Endpoint Base

```
POST https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages
```

### Headers Requeridos

```javascript
{
  "Authorization": "Bearer {WHATSAPP_ACCESS_TOKEN}",
  "Content-Type": "application/json"
}
```

### Payload para Enviar Mensaje

```javascript
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "18091234567",  // Número del cliente (sin +, sin espacios)
  "type": "text",
  "text": {
    "body": "Hola, te estoy ayudando personalmente"
  }
}
```

### Ejemplo en Next.js (API Route) - COMPLETO Y FUNCIONAL

```javascript
// app/api/whatsapp/send-message/route.js
import axios from 'axios';
import { markAsHumanHandled, addHumanMessage, saveSentMessageId } from '@/lib/redis-admin';

export async function POST(request) {
  try {
    const { phone_number, message, client_id, admin_name = 'Agente' } = await request.json();
    
    // ⚠️ VALIDACIONES
    if (!phone_number || !message || !client_id) {
      return Response.json(
        { error: 'Faltan parámetros requeridos: phone_number, message, client_id' },
        { status: 400 }
      );
    }
    
    // ⚠️ VERIFICAR VARIABLES DE ENTORNO
    const phoneNumberId = process.env.WHATSAPP_PHONE_NUMBER_ID;
    const accessToken = process.env.WHATSAPP_ACCESS_TOKEN;
    
    if (!phoneNumberId || !accessToken) {
      console.error('❌ Variables de entorno faltantes:', {
        hasPhoneNumberId: !!phoneNumberId,
        hasAccessToken: !!accessToken
      });
      return Response.json(
        { error: 'Configuración de WhatsApp incompleta' },
        { status: 500 }
      );
    }
    
    // ⚠️ FORMATO DE NÚMERO (sin +, sin espacios, solo dígitos)
    const cleanPhone = phone_number.replace(/[+\s-()]/g, '');
    
    const url = `https://graph.facebook.com/v21.0/${phoneNumberId}/messages`;
    
    const payload = {
      messaging_product: 'whatsapp',
      recipient_type: 'individual',
      to: cleanPhone,
      type: 'text',
      text: {
        body: message
      }
    };
    
    console.log('📤 Enviando mensaje a WhatsApp:', {
      url,
      to: cleanPhone,
      messageLength: message.length,
      hasToken: !!accessToken
    });
    
    // ⚠️ ENVIAR A WHATSAPP PRIMERO
    let response;
    try {
      response = await axios.post(url, payload, {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        },
        timeout: 30000 // 30 segundos
      });
      
      console.log('✅ Respuesta de WhatsApp:', {
        status: response.status,
        messageId: response.data.messages?.[0]?.id,
        data: response.data
      });
      
    } catch (whatsappError) {
      // ⚠️ ERROR AL ENVIAR A WHATSAPP - NO ACTUALIZAR REDIS
      console.error('❌ Error enviando a WhatsApp:', {
        status: whatsappError.response?.status,
        statusText: whatsappError.response?.statusText,
        data: whatsappError.response?.data,
        message: whatsappError.message
      });
      
      return Response.json(
        { 
          error: 'Error enviando mensaje a WhatsApp',
          details: whatsappError.response?.data || whatsappError.message
        },
        { status: whatsappError.response?.status || 500 }
      );
    }
    
    // ⚠️ SOLO SI WHATSAPP RESPONDE OK, ACTUALIZAR REDIS
    const messageId = response.data.messages?.[0]?.id;
    
    if (!messageId) {
      console.warn('⚠️ WhatsApp no retornó message_id:', response.data);
    }
    
    // Actualizar Redis
    try {
      await markAsHumanHandled(client_id, cleanPhone, admin_name);
      await addHumanMessage(client_id, cleanPhone, message, admin_name);
      
      if (messageId) {
        await saveSentMessageId(client_id, cleanPhone, messageId);
      }
      
      console.log('✅ Redis actualizado correctamente');
      
    } catch (redisError) {
      // ⚠️ ERROR EN REDIS PERO MENSAJE YA ENVIADO A WHATSAPP
      console.error('⚠️ Error actualizando Redis (mensaje ya enviado):', redisError);
      // No fallar porque el mensaje ya se envió
    }
    
    return Response.json({ 
      success: true, 
      message_id: messageId,
      phone_number: cleanPhone
    });
    
  } catch (error) {
    console.error('❌ Error general:', error);
    return Response.json(
      { error: 'Error interno del servidor', details: error.message },
      { status: 500 }
    );
  }
}
```

---

## 🔴 Actualizar Redis (Clave del Sistema)

Cuando el admin envía un mensaje, **DEBES** actualizar Redis para que el bot sepa que hay intervención humana.

### Opción 1: Usar Redis directamente (Recomendado)

```javascript
// lib/redis-admin.js
import { createClient } from 'redis';

const redis = createClient({
  url: process.env.REDIS_URL || 'redis://localhost:6379'
});

await redis.connect();

export async function markAsHumanHandled(clientId, phoneNumber, adminName) {
  const statusKey = `${clientId}:${phoneNumber}:status`;
  const adminKey = `${clientId}:${phoneNumber}:admin`;
  
  // Marcar como human_handled (expira en 1 hora)
  await redis.setEx(statusKey, 3600, 'human_handled');
  await redis.setEx(adminKey, 3600, adminName);
}

export async function addHumanMessage(clientId, phoneNumber, message, adminName) {
  const messagesKey = `${clientId}:${phoneNumber}:messages`;
  
  // Agregar mensaje al historial
  const messageData = {
    role: 'assistant',
    content: message,
    human: true,
    admin: adminName,
    timestamp: new Date().toISOString()
  };
  
  // Agregar al final de la lista (Redis LIST)
  await redis.rPush(messagesKey, JSON.stringify(messageData));
  
  // Limitar a últimos 50 mensajes
  await redis.lTrim(messagesKey, -50, -1);
  
  // Expirar en 1 hora
  await redis.expire(messagesKey, 3600);
}

export async function saveSentMessageId(clientId, phoneNumber, messageId) {
  const sentKey = `${clientId}:${phoneNumber}:sent_messages`;
  
  // Guardar message_id para detectar mensajes desde Business Suite
  await redis.sAdd(sentKey, messageId);
  await redis.expire(sentKey, 3600);
}

export async function resolveConversation(clientId, phoneNumber, resumeAI = true) {
  const statusKey = `${clientId}:${phoneNumber}:status`;
  const adminKey = `${clientId}:${phoneNumber}:admin`;
  const escalationKey = `${clientId}:${phoneNumber}:escalation_reason`;
  
  if (resumeAI) {
    // Liberar control y reanudar IA
    await redis.del(statusKey);
    await redis.del(adminKey);
    await redis.del(escalationKey);
  } else {
    // Solo marcar como resuelta, mantener IA pausada
    // (No hacer nada, o agregar flag adicional)
  }
}
```

### Uso en API Route

```javascript
// app/api/whatsapp/send-message/route.js
import { markAsHumanHandled, addHumanMessage, saveSentMessageId } from '@/lib/redis-admin';

export async function POST(request) {
  const { phone_number, message, client_id, admin_name = 'Agente' } = await request.json();
  
  // 1. Enviar mensaje por WhatsApp
  const response = await sendWhatsAppMessage(phone_number, message);
  const messageId = response.data.messages?.[0]?.id;
  
  // 2. Marcar conversación como human_handled
  await markAsHumanHandled(client_id, phone_number, admin_name);
  
  // 3. Guardar mensaje en historial
  await addHumanMessage(client_id, phone_number, message, admin_name);
  
  // 4. Guardar message_id (para detectar mensajes desde Business Suite)
  if (messageId) {
    await saveSentMessageId(client_id, phone_number, messageId);
  }
  
  return Response.json({ success: true });
}
```

---

## 📋 Endpoints Recomendados para tu Panel Admin

### 1. Enviar Mensaje como Humano

```javascript
POST /api/admin/conversations/send-message

Body:
{
  "client_id": 1,
  "phone_number": "18091234567",
  "message": "Hola, te estoy ayudando personalmente",
  "admin_name": "Juan Pérez"
}

Response:
{
  "success": true,
  "message_id": "wamid.xxx",
  "status": "human_handled"
}
```

**Comportamiento:**
- Envía mensaje por WhatsApp
- Marca conversación como `human_handled` en Redis
- Guarda mensaje en historial con flag `human: true`
- **El bot detectará esto y pausará la IA automáticamente**

### 2. Escalar Conversación

```javascript
POST /api/admin/conversations/escalate

Body:
{
  "client_id": 1,
  "phone_number": "18091234567",
  "motivo": "Cliente muy molesto, requiere atención especial"
}

Response:
{
  "success": true,
  "status": "escalated"
}
```

**Comportamiento:**
- Marca conversación como `escalated` en Redis
- **El bot pausará la IA automáticamente**

### 3. Resolver Conversación

```javascript
POST /api/admin/conversations/resolve

Body:
{
  "client_id": 1,
  "phone_number": "18091234567",
  "resume_ai": true  // true = reanudar IA, false = solo marcar como resuelta
}

Response:
{
  "success": true,
  "status": "active",
  "ai_resumed": true
}
```

**Comportamiento:**
- Si `resume_ai: true`: Libera control y reanuda la IA
- Si `resume_ai: false`: Solo marca como resuelta pero mantiene IA pausada

### 4. Obtener Estado de Conversación

```javascript
GET /api/admin/conversations/status?client_id=1&phone_number=18091234567

Response:
{
  "phone_number": "18091234567",
  "client_id": 1,
  "status": {
    "status": "human_handled",
    "admin": "Juan Pérez",
    "escalation_reason": null
  },
  "is_human_handled": true
}
```

---

## 🔍 Cómo el Bot Detecta Intervención Humana

El bot verifica Redis en cada mensaje entrante:

```python
# En app/api/routes/webhook.py (del bot Python)

memory = ConversationMemory(client_id, phone_number)
is_human_handled = await memory.is_human_handled()

if is_human_handled:
    # Solo guardar mensaje, NO responder con IA
    await memory.add_message("user", user_message)
    return  # IA pausada
```

**El bot verifica:**
- Si `status` en Redis es `"human_handled"` o `"escalated"`
- Si es así, guarda el mensaje pero **NO genera respuesta automática**

---

## 🎨 Ejemplo Completo: Componente React

```jsx
// components/ConversationChat.jsx
'use client';

import { useState } from 'react';

export default function ConversationChat({ conversation }) {
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  
  const handleSendMessage = async () => {
    if (!message.trim()) return;
    
    setSending(true);
    
    try {
      const response = await fetch('/api/admin/conversations/send-message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: conversation.client_id,
          phone_number: conversation.phone_number,
          message: message,
          admin_name: 'Tu Nombre' // O desde sesión
        })
      });
      
      if (response.ok) {
        setMessage('');
        // Refrescar mensajes
        // ...
      }
    } catch (error) {
      console.error('Error enviando mensaje:', error);
    } finally {
      setSending(false);
    }
  };
  
  return (
    <div className="conversation-chat">
      {/* Lista de mensajes */}
      <div className="messages">
        {conversation.messages.map((msg, idx) => (
          <div key={idx} className={msg.human ? 'message-human' : 'message-bot'}>
            {msg.human && <span className="admin-badge">{msg.admin}</span>}
            <p>{msg.content}</p>
          </div>
        ))}
      </div>
      
      {/* Input para enviar */}
      <div className="message-input">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Escribe tu mensaje..."
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSendMessage();
            }
          }}
        />
        <button onClick={handleSendMessage} disabled={sending || !message.trim()}>
          {sending ? 'Enviando...' : 'Enviar'}
        </button>
      </div>
    </div>
  );
}
```

---

## 🔐 Variables de Entorno Necesarias

```env
# .env.local (Next.js)

# WhatsApp API
WHATSAPP_PHONE_NUMBER_ID=930560030145818
WHATSAPP_ACCESS_TOKEN=tu_token_aqui
WHATSAPP_API_VERSION=v21.0

# Redis
REDIS_URL=redis://localhost:6379
# O si usas Redis Cloud:
# REDIS_URL=rediss://:password@host:port

# Base de datos (para obtener client_id)
DATABASE_URL=postgresql://...
```

---

## ⚠️ Puntos Importantes

### 1. Formato de Número de Teléfono

El número debe estar en formato internacional **sin + y sin espacios**:
- ✅ Correcto: `18091234567`
- ❌ Incorrecto: `+1 809 123 4567` o `809-123-4567`

### 2. Guardar message_id

**Siempre** guarda el `message_id` que retorna la API de WhatsApp. El bot lo usa para detectar mensajes enviados desde Business Suite.

### 3. TTL en Redis

El bot usa TTL de 1 hora (3600 segundos) para las keys. Si una conversación está inactiva por más de 1 hora, el estado se resetea automáticamente.

### 4. Detección Automática

El bot también detecta mensajes enviados desde **Meta Business Suite**. Si envías un mensaje desde Business Suite, el bot lo detectará automáticamente y pausará la IA.

---

## 🧪 Testing y Debugging

### 1. Verificar que el Mensaje se Envía a WhatsApp

**⚠️ PROBLEMA COMÚN:** El mensaje aparece en Redis pero no en WhatsApp.

**Causas posibles:**
1. Error al llamar a la API de WhatsApp (no se está enviando realmente)
2. Credenciales incorrectas
3. Formato de número incorrecto
4. Error silencioso que no se está mostrando

**Solución - Agregar Logs Detallados:**

```javascript
// En tu API route, ANTES de actualizar Redis:

console.log('🔍 DEBUG - Antes de enviar a WhatsApp:', {
  phoneNumberId: process.env.WHATSAPP_PHONE_NUMBER_ID,
  hasAccessToken: !!process.env.WHATSAPP_ACCESS_TOKEN,
  phoneNumber: cleanPhone,
  message: message.substring(0, 50) + '...'
});

const response = await axios.post(url, payload, {
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  }
});

console.log('✅ WhatsApp Response:', {
  status: response.status,
  messageId: response.data.messages?.[0]?.id,
  fullResponse: JSON.stringify(response.data, null, 2)
});

// ⚠️ IMPORTANTE: Verificar que response.status === 200
if (response.status !== 200) {
  throw new Error(`WhatsApp API retornó status ${response.status}`);
}
```

### 2. Probar Envío de Mensaje con curl

```bash
curl -X POST http://localhost:3000/api/admin/conversations/send-message \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": 1,
    "phone_number": "18091234567",
    "message": "Hola, soy un admin",
    "admin_name": "Test Admin"
  }' \
  -v  # -v para ver headers y respuesta completa
```

**Respuesta esperada:**
```json
{
  "success": true,
  "message_id": "wamid.xxx",
  "phone_number": "18091234567"
}
```

**Si hay error:**
```json
{
  "error": "Error enviando mensaje a WhatsApp",
  "details": { ... }
}
```

### 3. Verificar Logs del Servidor

Revisa los logs de tu servidor Next.js para ver:
- ¿Se está llamando a la API de WhatsApp?
- ¿Qué respuesta está retornando?
- ¿Hay algún error?

```bash
# En tu terminal donde corre Next.js
# Deberías ver logs como:
# 📤 Enviando mensaje a WhatsApp: { ... }
# ✅ Respuesta de WhatsApp: { ... }
# ✅ Redis actualizado correctamente
```

### 4. Probar Directamente la API de WhatsApp

Para verificar que tus credenciales funcionan:

```bash
curl -X POST "https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages" \
  -H "Authorization: Bearer {ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": "18091234567",
    "type": "text",
    "text": {
      "body": "Test desde curl"
    }
  }'
```

**Si esto funciona pero tu panel no, el problema está en tu código Next.js.**

### 2. Verificar Estado en Redis

```bash
redis-cli
> GET "1:18091234567:status"
"human_handled"
> GET "1:18091234567:admin"
"Test Admin"
```

### 3. Probar que el Bot No Responde

1. Marca conversación como `human_handled`
2. Envía un mensaje desde WhatsApp al bot
3. El bot **NO debe responder** (solo guarda el mensaje)

---

## 📚 Recursos Adicionales

- [WhatsApp Business API Documentation](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [Redis Node.js Client](https://github.com/redis/node-redis)
- [Bot Python Codebase](../app/core/redis.py) - Ver cómo el bot gestiona Redis

---

## 🆘 Troubleshooting

### ❌ PROBLEMA: El mensaje aparece en Redis pero NO en WhatsApp

**Síntomas:**
- El mensaje se guarda en Redis correctamente
- Aparece en tu panel admin
- Pero NO llega a WhatsApp

**Causas y Soluciones:**

#### 1. Error al llamar a la API de WhatsApp (más común)

**Diagnóstico:**
```javascript
// Agrega esto ANTES de actualizar Redis:

try {
  const response = await axios.post(url, payload, { headers });
  
  // ⚠️ VERIFICAR QUE REALMENTE SE ENVIÓ
  if (response.status !== 200) {
    console.error('❌ WhatsApp retornó error:', response.status, response.data);
    return Response.json({ error: 'Error de WhatsApp' }, { status: 500 });
  }
  
  if (!response.data.messages?.[0]?.id) {
    console.error('❌ WhatsApp no retornó message_id:', response.data);
    return Response.json({ error: 'Error de WhatsApp' }, { status: 500 });
  }
  
  console.log('✅ Mensaje enviado correctamente a WhatsApp');
  
} catch (error) {
  // ⚠️ NO ACTUALIZAR REDIS SI HAY ERROR
  console.error('❌ Error enviando a WhatsApp:', error.response?.data || error.message);
  return Response.json(
    { error: 'Error enviando a WhatsApp', details: error.response?.data },
    { status: error.response?.status || 500 }
  );
}
```

**Solución:** Asegúrate de que el código **NO actualice Redis** si hay error al enviar a WhatsApp.

#### 2. Credenciales incorrectas

**Diagnóstico:**
```javascript
// Verificar variables de entorno
console.log('Credenciales:', {
  phoneNumberId: process.env.WHATSAPP_PHONE_NUMBER_ID,
  hasToken: !!process.env.WHATSAPP_ACCESS_TOKEN,
  tokenLength: process.env.WHATSAPP_ACCESS_TOKEN?.length
});
```

**Solución:** Verifica que las variables de entorno estén correctas en `.env.local`:
```env
WHATSAPP_PHONE_NUMBER_ID=930560030145818
WHATSAPP_ACCESS_TOKEN=tu_token_completo_aqui
```

#### 3. Formato de número incorrecto

**Diagnóstico:**
```javascript
// El número debe ser: "18091234567" (sin +, sin espacios)
const cleanPhone = phone_number.replace(/[+\s-()]/g, '');
console.log('Número limpio:', cleanPhone);
```

**Solución:** Asegúrate de limpiar el número antes de enviarlo.

#### 4. Error silencioso (try-catch que oculta el error)

**Diagnóstico:**
```javascript
// ⚠️ NO hacer esto:
try {
  await axios.post(url, payload);
  await updateRedis(); // Esto se ejecuta aunque WhatsApp falle
} catch (error) {
  // Error silencioso
}
```

**Solución:** Verificar respuesta de WhatsApp ANTES de actualizar Redis:
```javascript
const response = await axios.post(url, payload);
if (response.status === 200 && response.data.messages?.[0]?.id) {
  await updateRedis(); // Solo si WhatsApp respondió OK
}
```

#### 5. Orden incorrecto de operaciones

**❌ INCORRECTO:**
```javascript
await updateRedis(); // Actualizar Redis primero
await sendToWhatsApp(); // Enviar después (si falla, Redis ya está actualizado)
```

**✅ CORRECTO:**
```javascript
const response = await sendToWhatsApp(); // Enviar primero
if (response.status === 200) {
  await updateRedis(); // Solo si WhatsApp OK
}
```

### El bot sigue respondiendo aunque marqué como human_handled

1. Verifica que la key en Redis sea correcta: `{client_id}:{phone_number}:status`
2. Verifica que el valor sea exactamente `"human_handled"` o `"escalated"`
3. Verifica que el TTL no haya expirado

### No puedo enviar mensajes por WhatsApp

1. Verifica que `WHATSAPP_ACCESS_TOKEN` sea válido
2. Verifica que `WHATSAPP_PHONE_NUMBER_ID` sea correcto
3. Verifica que el número de destino esté en formato correcto (sin +, sin espacios)
4. **Verifica los logs del servidor** para ver el error exacto

### Los mensajes no aparecen en el historial

1. Verifica que estés guardando en la key correcta: `{client_id}:{phone_number}:messages`
2. Verifica el formato del mensaje (debe ser JSON stringificado)
3. Verifica que estés usando `rPush` para agregar al final de la lista

---

## ✅ Checklist de Implementación

- [ ] Configurar variables de entorno (WhatsApp API, Redis)
- [ ] Instalar cliente de Redis en Next.js
- [ ] Crear funciones para actualizar Redis (`markAsHumanHandled`, `addHumanMessage`, etc.)
- [ ] Crear API route para enviar mensajes (`/api/admin/conversations/send-message`)
- [ ] Crear API route para escalar (`/api/admin/conversations/escalate`)
- [ ] Crear API route para resolver (`/api/admin/conversations/resolve`)
- [ ] Crear componente React para chat de conversación
- [ ] Probar envío de mensaje y verificar que el bot no responde
- [ ] Probar resolución y verificar que el bot reanuda la IA

---

**¿Preguntas?** Revisa el código del bot en `app/core/redis.py` y `app/api/routes/webhook.py` para entender mejor cómo funciona la detección.
