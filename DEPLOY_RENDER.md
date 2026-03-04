# 🚀 Guía de Despliegue en Render (Plan Gratis)

Render es la forma más fácil de desplegar tu bot directamente desde tu repositorio de GitHub usando el `Dockerfile` que ya tenemos preparado. 

> ⚠️ **Limitaciones del Plan Gratis:**
> - El bot entrará en reposo (se dormirá) tras 15 minutos sin recibir mensajes.
> - Al dormirse, el próximo cliente que escriba tendrá que esperar ~40 segundos para que el servidor despierte y envíe la respuesta.
> - Mientras esté dormido, los correos automáticos de confirmación/recordatorio no se enviarán a su hora.

## 1. Preparar el Repositorio

Abre tu terminal en la carpeta del proyecto y asegúrate de subir los últimos cambios a GitHub:

```bash
git add .
git commit -m "Listo para Render"
git push origin main
```

## 2. Crear la Aplicación en Render

1. Ve a [render.com](https://render.com/) e inicia sesión con tu cuenta de GitHub.
2. Da clic en el botón **"New +"** y selecciona **"Web Service"**.
3. Elige la opción **"Build and deploy from a Git repository"** y haz clic en Next.
4. Conecta tu repositorio (ej. `guelo0987/BOTWA`) y presiona "Connect".

## 3. Configurar el Web Service

Llena el formulario con estos datos exactos:

- **Name:** `whatsapp-bot-dlcsoft` (o el nombre que quieras)
- **Region:** `US East (Ohio)` (o la más cercana a ti)
- **Branch:** `main`
- **Root Directory:** Déjalo en blanco.
- **Runtime:** Selecciona **`Docker`** (Render leerá tu `Dockerfile` automáticamente).
- **Instance Type:** Selecciona el plan **`Free`**.

## 4. Agregar las Variables de Entorno (Environment Variables)

Este es el paso fundamental. Sube (haz scroll up) en la página de Render hasta la sección **Environment Variables** y haz clic en "Add Environment Variable" para cada uno de los siguientes valores. Puedes copiarlos directamente de tu archivo `.env` local:

| Key | Value |
| :--- | :--- |
| `ENV_MODE` | `prod` |
| `LOG_LEVEL` | `INFO` |
| `DATA_BASE_CONNECTION_STRING` | *(Tu URL de Neon Postgres)* |
| `REDIS_URL` | *(Tu URL de Upstash)* |
| `REDIS_CONNECT_TIMEOUT_SECONDS` | `3.0` |
| `REDIS_SOCKET_TIMEOUT_SECONDS`| `3.0` |
| `REDIS_REQUIRED` | `true` |
| `WHATSAPP_VERIFY_TOKEN` | `n8n` |
| `GEMINI_API_KEY` | *(Tu llave de Gemini)* |
| `GEMINI_MODEL` | `gemini-2.5-flash` |
| `GOOGLE_CREDENTIALS_PATH` | `credentials/google_calendar_service.json` |
| `RESEND_API_KEY` | *(Tu API Key de Resend)* |
| `EMAIL_FROM` | `notificaciones@bot.dlcsoft.dev` |
| `SESSION_EXPIRE_SECONDS` | `14400` |
| `MAX_CONTEXT_MESSAGES` | `20` |

> **Nota sobre Google Calendar:** Asegúrate de que tu archivo `credentials/google_calendar_service.json` esté subido a GitHub (quítalo del `.gitignore` temporalmente si no está subido). ¡Si el bot no encuentra ese archivo al arrancar, fallará y el deploy se cancelará!

## 5. ¡Desplegar! 🚀

1. Al final de la página, presiona el botón **Create Web Service**.
2. Render comenzará a construir tu contenedor (descargará Python, instalará las dependencias y lanzará Gunicorn). Este proceso toma entre 2 y 5 minutos.
3. Observa los logs en la pantalla negra de Render. Si todo salió bien, verás tus mensajes habituales: `🤖 Bot WhatsApp listo!`.

## 6. Siguientes Pasos (Configurar el Webhook)

Arriba a la izquierda en Render verás un link público de tu aplicación, algo como `https://whatsapp-bot-xxx.onrender.com`.

Copia esa URL, ve al panel de desarrollo de Meta (WhatsApp) y configura tu Webhook apuntando a:
**`https://whatsapp-bot-xxx.onrender.com/webhook`**

Agrega el token `n8n` para verificar, guarda, ¡y tu bot estará vivo en la nube! ☁️
