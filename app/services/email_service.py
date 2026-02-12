"""
Servicio de Email para enviar confirmaciones de citas/reservaciones.
Usa SMTP o servicios como SendGrid/Resend.
"""
import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Servicio para enviar emails de confirmación."""
    
    def __init__(self, smtp_host=None, smtp_port=None, smtp_user=None, smtp_password=None, from_email=None):
        """
        Inicializa el servicio de email.
        
        Args:
            smtp_host: Host SMTP (opcional, usa settings si no se proporciona)
            smtp_port: Puerto SMTP (opcional)
            smtp_user: Usuario SMTP (opcional)
            smtp_password: Contraseña SMTP (opcional)
            from_email: Email remitente (opcional)
        """
        try:
            # Intentar usar settings si están disponibles
            from app.core.config import settings as app_settings
            self.smtp_host = smtp_host or getattr(app_settings, 'SMTP_HOST', 'smtp.gmail.com')
            self.smtp_port = smtp_port or getattr(app_settings, 'SMTP_PORT', 587)
            self.smtp_user = smtp_user or getattr(app_settings, 'SMTP_USER', None)
            self.smtp_password = smtp_password or getattr(app_settings, 'SMTP_PASSWORD', None)
            self.from_email = from_email or getattr(app_settings, 'EMAIL_FROM', self.smtp_user)
        except Exception:
            # Si settings no está disponible, usar parámetros o variables de entorno
            import os
            self.smtp_host = smtp_host or os.getenv('SMTP_HOST', 'smtp.gmail.com')
            self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
            self.smtp_user = smtp_user or os.getenv('SMTP_USER')
            self.smtp_password = smtp_password or os.getenv('SMTP_PASSWORD')
            self.from_email = from_email or os.getenv('EMAIL_FROM', self.smtp_user)
        
        self.enabled = bool(self.smtp_user and self.smtp_password)
        
        if not self.enabled:
            logger.warning("Email service disabled - SMTP credentials not configured")
    
    def _send_smtp(self, msg: MIMEMultipart):
        """Envía un email de forma síncrona (solo para uso con asyncio.to_thread)."""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
    
    async def send_confirmation_email(
        self,
        to_email: str,
        business_name: str,
        business_type: str,
        customer_name: str,
        appointment_date: datetime,
        appointment_details: dict
    ) -> bool:
        """
        Envía email de confirmación de cita/reservación.
        
        Args:
            to_email: Email del cliente
            business_name: Nombre del negocio
            business_type: Tipo (salon, clinic, store, restaurant)
            customer_name: Nombre del cliente
            appointment_date: Fecha y hora de la cita
            appointment_details: Detalles adicionales
        
        Returns:
            True si se envió correctamente
        """
        if not self.enabled:
            logger.info("Email disabled - skipping confirmation")
            return False
        
        try:
            # Formatear fecha en español
            dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                     'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            
            dia_semana = dias[appointment_date.weekday()]
            dia = appointment_date.day
            mes = meses[appointment_date.month - 1]
            año = appointment_date.year
            hora = appointment_date.strftime("%I:%M %p")
            
            fecha_formateada = f"{dia_semana} {dia} de {mes} de {año} a las {hora}"
            
            # Generar contenido según tipo de negocio
            subject, html_content = self._generate_email_content(
                business_type=business_type,
                business_name=business_name,
                customer_name=customer_name,
                fecha_formateada=fecha_formateada,
                details=appointment_details
            )
            
            # Crear mensaje
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{business_name} <{self.from_email}>"
            msg['To'] = to_email
            
            # Agregar contenido HTML
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            # Enviar (en thread para no bloquear el event loop)
            await asyncio.to_thread(self._send_smtp, msg)
            
            logger.debug(f"Email de confirmación enviado a {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Error enviando email: {e}", exc_info=True)
            return False
    
    async def send_reminder_email(
        self,
        to_email: str,
        business_name: str,
        business_type: str,
        customer_name: str,
        appointment_date: datetime,
        appointment_details: dict,
        hours_before: int = 24,
    ) -> bool:
        """
        Envía email de recordatorio de cita (ej. 24h o 48h antes).
        
        Args:
            to_email: Email del cliente
            business_name: Nombre del negocio
            business_type: salon, clinic, restaurant, store
            customer_name: Nombre del cliente
            appointment_date: Fecha y hora de la cita
            appointment_details: servicio, profesional, etc.
            hours_before: Anticipación del recordatorio (24 o 48)
        
        Returns:
            True si se envió correctamente
        """
        if not self.enabled:
            logger.info("Email disabled - skipping reminder")
            return False
        
        try:
            dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                     'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            dia_semana = dias[appointment_date.weekday()]
            dia = appointment_date.day
            mes = meses[appointment_date.month - 1]
            año = appointment_date.year
            hora = appointment_date.strftime("%I:%M %p")
            fecha_formateada = f"{dia_semana} {dia} de {mes} de {año} a las {hora}"
            
            subject = f"Recordatorio de cita - {business_name}"
            if hours_before >= 48:
                subject = f"Confirmación de cita - {business_name}"
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: #f0f4f8; padding: 20px; border-radius: 8px;">
                        <h2 style="margin-top: 0;">Recordatorio de cita</h2>
                        <p>Hola <strong>{customer_name}</strong>,</p>
                        <p>Te recordamos que tienes una cita programada en <strong>{business_name}</strong>:</p>
                        <p><strong>Fecha y hora:</strong> {fecha_formateada}</p>
                        <p><strong>Servicio:</strong> {appointment_details.get('servicio', 'Cita')}</p>
                        {f'<p><strong>Profesional:</strong> {appointment_details.get("profesional", "")}</p>' if appointment_details.get('profesional') else ''}
                        <p>Si necesitas cancelar o modificar, contáctanos por WhatsApp.</p>
                        <p>¡Te esperamos!</p>
                    </div>
                    <p style="color: #888; font-size: 12px;">{business_name}</p>
                </div>
            </body>
            </html>
            """
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{business_name} <{self.from_email}>"
            msg['To'] = to_email
            msg.attach(MIMEText(html, 'html', 'utf-8'))
            
            await asyncio.to_thread(self._send_smtp, msg)
            
            logger.debug(f"Email de recordatorio enviado a {to_email}")
            return True
        except Exception as e:
            logger.error(f"Error enviando email de recordatorio: {e}", exc_info=True)
            return False
    
    def _generate_email_content(
        self,
        business_type: str,
        business_name: str,
        customer_name: str,
        fecha_formateada: str,
        details: dict
    ) -> tuple[str, str]:
        """Genera el contenido del email según el tipo de negocio."""
        
        # Detectar si es cancelación o modificación
        is_cancelled = details.get("cancelado", False)
        is_modified = details.get("modificada", False)
        
        if is_cancelled:
            # Template de cancelación
            subject = f"❌ Cancelación de Cita - {business_name}"
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .footer {{ text-align: center; padding: 20px; color: #888; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin:0;">❌ Cita Cancelada</h1>
                        <p style="margin:10px 0 0 0; opacity:0.9;">{business_name}</p>
                    </div>
                    <div class="content">
                        <p>Estimado/a <strong>{customer_name}</strong>,</p>
                        <p>Confirmamos que tu cita programada para el <strong>{fecha_formateada}</strong> ha sido cancelada.</p>
                        <p>Si deseas reagendar, por favor contáctanos nuevamente.</p>
                        <p style="text-align: center; margin-top: 30px;">
                            <strong>¡Esperamos poder atenderte pronto!</strong>
                        </p>
                    </div>
                    <div class="footer">
                        <p>{business_name}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            return subject, html
        
        if is_modified:
            # Template de modificación (similar al de confirmación pero con nota de modificación)
            if business_type == 'restaurant':
                subject = f"🔄 Reservación Modificada - {business_name}"
                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                        .details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                        .detail-row {{ display: flex; padding: 10px 0; border-bottom: 1px solid #eee; }}
                        .label {{ font-weight: bold; width: 150px; color: #666; }}
                        .value {{ color: #333; }}
                        .footer {{ text-align: center; padding: 20px; color: #888; font-size: 12px; }}
                        .notice {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">
                            <h1 style="margin:0;">🔄 Reservación Modificada</h1>
                            <p style="margin:10px 0 0 0; opacity:0.9;">{business_name}</p>
                        </div>
                        <div class="content">
                            <div class="notice">
                                <strong>⚠️ Tu reservación ha sido modificada</strong>
                            </div>
                            <p>Estimado/a <strong>{customer_name}</strong>,</p>
                            <p>Hemos actualizado los detalles de tu reservación:</p>
                            
                            <div class="details">
                                <div class="detail-row">
                                    <span class="label">📅 Nueva fecha y hora:</span>
                                    <span class="value">{fecha_formateada}</span>
                                </div>
                                <div class="detail-row">
                                    <span class="label">👥 Personas:</span>
                                    <span class="value">{details.get('num_personas', 'No especificado')}</span>
                                </div>
                                <div class="detail-row">
                                    <span class="label">🪑 Área:</span>
                                    <span class="value">{details.get('area', 'Por asignar')}</span>
                                </div>
                            </div>
                            
                            <p><strong>📍 Notas importantes:</strong></p>
                            <ul>
                                <li>Por favor llega 10 minutos antes de tu nueva hora</li>
                                <li>La reservación se mantendrá por 15 minutos después de la hora programada</li>
                            </ul>
                            
                            <p style="text-align: center; margin-top: 30px;">
                                <strong>¡Será un placer atenderle!</strong> 🥂
                            </p>
                        </div>
                        <div class="footer">
                            <p>{business_name}</p>
                        </div>
                    </div>
                </body>
                </html>
                """
                return subject, html
        
        # Continuar con templates normales de confirmación
        if business_type == 'restaurant':
            subject = f"✅ Confirmación de Reservación - {business_name}"
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                    .detail-row {{ display: flex; padding: 10px 0; border-bottom: 1px solid #eee; }}
                    .label {{ font-weight: bold; width: 150px; color: #666; }}
                    .value {{ color: #333; }}
                    .footer {{ text-align: center; padding: 20px; color: #888; font-size: 12px; }}
                    .emoji {{ font-size: 24px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin:0;">🍽️ Reservación Confirmada</h1>
                        <p style="margin:10px 0 0 0; opacity:0.9;">{business_name}</p>
                    </div>
                    <div class="content">
                        <p>Estimado/a <strong>{customer_name}</strong>,</p>
                        <p>¡Gracias por su reservación! Nos complace confirmar los siguientes detalles:</p>
                        
                        <div class="details">
                            <div class="detail-row">
                                <span class="label">📅 Fecha y hora:</span>
                                <span class="value">{fecha_formateada}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">👥 Personas:</span>
                                <span class="value">{details.get('num_personas', 'No especificado')}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">🪑 Área:</span>
                                <span class="value">{details.get('area', 'Por asignar')}</span>
                            </div>
                            {f'<div class="detail-row"><span class="label">🎉 Ocasión:</span><span class="value">{details.get("ocasion")}</span></div>' if details.get('ocasion') else ''}
                        </div>
                        
                        <p><strong>📍 Notas importantes:</strong></p>
                        <ul>
                            <li>Por favor llegue 10 minutos antes de su reservación</li>
                            <li>La reservación se mantendrá por 15 minutos después de la hora programada</li>
                            <li>Para cancelar o modificar, contáctenos con al menos 2 horas de anticipación</li>
                        </ul>
                        
                        <p style="text-align: center; margin-top: 30px;">
                            <strong>¡Será un placer atenderle!</strong> 🥂
                        </p>
                    </div>
                    <div class="footer">
                        <p>{business_name}</p>
                        <p>Este es un correo automático, por favor no responda a este mensaje.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
        elif business_type == 'clinic':
            subject = f"✅ Confirmación de Cita Médica - {business_name}"
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                    .detail-row {{ padding: 10px 0; border-bottom: 1px solid #eee; }}
                    .label {{ font-weight: bold; color: #666; }}
                    .footer {{ text-align: center; padding: 20px; color: #888; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin:0;">🏥 Cita Confirmada</h1>
                        <p style="margin:10px 0 0 0; opacity:0.9;">{business_name}</p>
                    </div>
                    <div class="content">
                        <p>Estimado/a <strong>{customer_name}</strong>,</p>
                        <p>Su cita médica ha sido confirmada con los siguientes detalles:</p>
                        
                        <div class="details">
                            <div class="detail-row">
                                <span class="label">📅 Fecha y hora:</span><br>
                                <span>{fecha_formateada}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">👨‍⚕️ Profesional:</span><br>
                                <span>{details.get('profesional', 'Por asignar')}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">📋 Tipo de consulta:</span><br>
                                <span>{details.get('servicio', 'Consulta general')}</span>
                            </div>
                        </div>
                        
                        <p><strong>📋 Recomendaciones:</strong></p>
                        <ul>
                            <li>Llegue 15 minutos antes de su cita</li>
                            <li>Traiga su documento de identidad</li>
                            <li>Si tiene estudios previos, tráigalos consigo</li>
                            <li>Para cancelar, avise con al menos 24 horas de anticipación</li>
                        </ul>
                    </div>
                    <div class="footer">
                        <p>{business_name}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
        elif business_type == 'salon':
            subject = f"✅ Confirmación de Cita - {business_name}"
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                    .detail-row {{ padding: 10px 0; border-bottom: 1px solid #eee; }}
                    .label {{ font-weight: bold; color: #666; }}
                    .footer {{ text-align: center; padding: 20px; color: #888; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin:0;">💇‍♀️ Cita Confirmada</h1>
                        <p style="margin:10px 0 0 0; opacity:0.9;">{business_name}</p>
                    </div>
                    <div class="content">
                        <p>¡Hola <strong>{customer_name}</strong>! ✨</p>
                        <p>Tu cita ha sido confirmada. Aquí están los detalles:</p>
                        
                        <div class="details">
                            <div class="detail-row">
                                <span class="label">📅 Fecha y hora:</span><br>
                                <span>{fecha_formateada}</span>
                            </div>
                            <div class="detail-row">
                                <span class="label">💅 Servicio:</span><br>
                                <span>{details.get('servicio', 'No especificado')}</span>
                            </div>
                            {f'<div class="detail-row"><span class="label">💰 Precio:</span><br><span>{details.get("precio")}</span></div>' if details.get('precio') else ''}
                        </div>
                        
                        <p><strong>📝 Recuerda:</strong></p>
                        <ul>
                            <li>Llega 5-10 minutos antes de tu cita</li>
                            <li>Si necesitas cancelar, avísanos con anticipación</li>
                        </ul>
                        
                        <p style="text-align: center; margin-top: 30px;">
                            <strong>¡Te esperamos!</strong> 💖
                        </p>
                    </div>
                    <div class="footer">
                        <p>{business_name}</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
        else:  # store u otros
            subject = f"✅ Confirmación - {business_name}"
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                    .footer {{ text-align: center; padding: 20px; color: #888; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin:0;">📦 Entrega Programada</h1>
                        <p style="margin:10px 0 0 0; opacity:0.9;">{business_name}</p>
                    </div>
                    <div class="content">
                        <p>Estimado/a <strong>{customer_name}</strong>,</p>
                        <p>Su entrega ha sido programada:</p>
                        
                        <div class="details">
                            <p><strong>📅 Fecha:</strong> {fecha_formateada}</p>
                            <p><strong>📦 Producto:</strong> {details.get('servicio', 'No especificado')}</p>
                            {f'<p><strong>📍 Dirección:</strong> {details.get("direccion")}</p>' if details.get('direccion') else ''}
                        </div>
                        
                        <p>Nos pondremos en contacto antes de la entrega.</p>
                    </div>
                    <div class="footer">
                        <p>{business_name}</p>
                    </div>
                </div>
            </body>
            </html>
            """
        
        return subject, html


# Instancia global
email_service = EmailService()
