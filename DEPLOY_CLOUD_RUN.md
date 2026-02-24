# 🚀 Guía de Despliegue en Google Cloud Run

Este proyecto está 100% listo para producción. Se ha diseñado con una arquitectura **Serverless / Stateless** y está dockerizado usando una imagen liviana de Python (`python:3.12-slim`) ejecutándose con Gunicorn y Uvicorn Workers.

Sigue estos pasos para desplegar tu aplicación en **Google Cloud Run**.

## 1. Requisitos Previos

1. Instalar [Google Cloud CLI (`gcloud`)](https://cloud.google.com/sdk/docs/install?hl=es-419).
2. Estar autenticado en tu cuenta de Google Cloud:
   ```bash
   gcloud auth login
   gcloud config set project TU_PROYECTO_ID
   ```
3. Activar las APIs necesarias en tu proyecto de Google Cloud:
   ```bash
   gcloud services enable run.googleapis.com
   gcloud services enable artifactregistry.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   ```

## 2. Construir la Imagen en Cloud Build

Google Cloud Build subirá tu código, leerá el `Dockerfile` y construirá la imagen en la nube automáticamente, guardándola en Artifact Registry.

```bash
gcloud builds submit --tag gcr.io/TU_PROYECTO_ID/whatsapp-bot
```
*(Cambia `TU_PROYECTO_ID` por el ID real de tu proyecto en Google Cloud)*

## 3. Desplegar en Cloud Run

Una vez construida la imagen, ejecuta este comando para lanzar tu contenedor a producción.

> **⚠️ Importante**: Cloud Run inyecta automáticamente la variable `PORT` (usualmente 8080). El `Dockerfile` ya está configurado para escuchar en ese puerto.

```bash
gcloud run deploy whatsapp-bot \
  --image gcr.io/TU_PROYECTO_ID/whatsapp-bot \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --set-env-vars="ENV_MODE=prod,LOG_LEVEL=INFO,DATA_BASE_CONNECTION_STRING=tu_url_neon,REDIS_URL=rediss://default:TU_PASSWORD_AQUI@tu_host.upstash.io:6379,REDIS_CONNECT_TIMEOUT_SECONDS=3.0,REDIS_SOCKET_TIMEOUT_SECONDS=3.0,REDIS_REQUIRED=true,WHATSAPP_VERIFY_TOKEN=n8n,GEMINI_API_KEY=tu_gemini_key,GEMINI_MODEL=gemini-2.5-flash,GOOGLE_CREDENTIALS_PATH=credentials/google_calendar_service.json,RESEND_API_KEY=tu_resend_api_key,EMAIL_FROM=notificaciones@bot.dlcsoft.dev,SESSION_EXPIRE_SECONDS=14400,MAX_CONTEXT_MESSAGES=20"
```

### Configuración Segura de Variables (Recomendado)
En lugar de pasar las variables de entorno (`--set-env-vars`), es **altamente recomendable** usar **Google Secret Manager** para tus credenciales (Base de datos, Gemini, Resend):

```bash
gcloud run deploy whatsapp-bot \
  --image gcr.io/TU_PROYECTO_ID/whatsapp-bot \
  ...
  --set-secrets="DATA_BASE_CONNECTION_STRING=neon_db_url:latest,GEMINI_API_KEY=gemini_key:latest"
```

## 4. Post-Despliegue

1. **Obtener URL pública**: Al terminar de desplegar, la terminal te dará una URL (ej: `https://whatsapp-bot-123.a.run.app`).
2. **Configurar WhatsApp Webhook**: 
   Vete al panel de Meta Developers y configura tu Webhook con esa URL y el token `n8n`.
   *(Nota: Asegúrate de añadir la ruta correcta, probablemente `https://whatsapp-bot-123.a.run.app/webhook`)*
3. **Validar Base de Datos**: Como tu base está en Neon y tu Redis externamente, asegúrate de que Cloud Run tenga permisos de salida a internet (los tiene por default) y que no haya restricciones de IP en tu base de datos.
4. **Ver Logs**: Puedes ver los logs del bot en tiempo real dirigiéndote a **Cloud Logging**. El bot ya tiene configurado el `CloudRunJsonFormatter`, por lo que tus logs estarán perfectamente parseados y filtrables por niveles (`INFO`, `ERROR`, `WARNING`).

## ¡Listo! 🎉
Tu bot ahora auto-escalará dependiendo del tráfico de mensajes de WhatsApp que recibas. Cloud Run lo apagará (`scale to zero`) si no hay tráfico para ahorrar dinero.
