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
        appointment_details: dict,
        client_settings=None
    ) -> bool:
       
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
                details=appointment_details,
                client_settings=client_settings
            )
            
            # Crear mensaje
            sender_display = business_name
            if client_settings and getattr(client_settings, 'sender_name', None):
                sender_display = client_settings.sender_name
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{sender_display} <{self.from_email}>"
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
        client_settings=None
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
            
            # Preparar estilos personalizados
            primary_color = getattr(client_settings, 'primary_color', None) or "#4facfe"
            secondary_color = getattr(client_settings, 'secondary_color', None) or "#00f2fe"
            logo_html = f'<img src="{client_settings.logo_url}" alt="Logo" style="max-height: 50px; margin-bottom: 10px;">' if client_settings and client_settings.logo_url else ''
            footer_text = getattr(client_settings, 'footer_text', None) or business_name

            subject = f"Recordatorio de cita - {business_name}"
            if hours_before >= 48:
                subject = f"Confirmación de cita - {business_name}"
            
            # Chequear override de subject
            templates = getattr(client_settings, 'templates', {}) or {}
            custom_subject = templates.get('reminder', {}).get('subject')
            if custom_subject:
                subject = custom_subject.format(business_name=business_name, date=fecha_formateada, hours=hours_before)

            html = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, {primary_color} 0%, {secondary_color} 100%); padding: 20px; border-radius: 8px 8px 0 0; color: white; text-align: center;">
                        {logo_html}
                        <h2 style="margin-top: 0; margin-bottom: 5px;">Recordatorio de cita</h2>
                        <p style="margin:0; opacity: 0.9;">{business_name}</p>
                    </div>
                    <div style="background: #f9f9f9; padding: 20px; border: 1px solid #eee; border-top: none; border-radius: 0 0 8px 8px;">
                        <p>Hola <strong>{customer_name}</strong>,</p>
                        <p>Te recordamos que tienes una cita programada:</p>
                        <p><strong>Fecha y hora:</strong> {fecha_formateada}</p>
                        <p><strong>Servicio:</strong> {appointment_details.get('servicio', 'Cita')}</p>
                        {f'<p><strong>Profesional:</strong> {appointment_details.get("profesional", "")}</p>' if appointment_details.get('profesional') else ''}
                        <p>Si necesitas cancelar o modificar, contáctanos por WhatsApp.</p>
                        <p>¡Te esperamos!</p>
                    </div>
                    <p style="color: #888; font-size: 12px; text-align: center; margin-top: 20px;">{footer_text}</p>
                </div>
            </body>
            </html>
            """
            
            sender_display = business_name
            if client_settings and getattr(client_settings, 'sender_name', None):
                sender_display = client_settings.sender_name
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{sender_display} <{self.from_email}>"
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
        details: dict,
        client_settings=None
    ) -> tuple[str, str]:
        """Genera el contenido del email según el tipo de negocio."""
        
        # Detectar si es cancelación o modificación
        is_cancelled = details.get("cancelado", False)
        is_modified = details.get("modificada", False)
        
        # Preparar estilos personalizados
        primary_color = getattr(client_settings, 'primary_color', None) or "#4A90D9"
        secondary_color = getattr(client_settings, 'secondary_color', None) or "#357ABD"
        footer_text = getattr(client_settings, 'footer_text', None) or business_name
        
        # Logo HTML — prominente en el header
        logo_url = getattr(client_settings, 'logo_url', None) if client_settings else None
        logo_html = f'<img src="{logo_url}" alt="{business_name}" style="max-height:70px; max-width:200px; margin-bottom:12px; display:block;">' if logo_url else ''
        
        # Override de templates
        templates = getattr(client_settings, 'templates', {}) or {}
        
        # ==========================================
        # FUNCIÓN HELPER: Genera una fila de detalle
        # ==========================================
        def _detail_row(emoji, label, value):
            if not value:
                return ""
            return f'''
            <tr>
                <td style="padding:10px 16px; border-bottom:1px solid #f0f0f0;">
                    <span style="font-size:16px;">{emoji}</span>
                    <span style="color:#888; font-size:13px; margin-left:4px;">{label}</span><br>
                    <span style="color:#333; font-size:15px; font-weight:600; margin-left:24px;">{value}</span>
                </td>
            </tr>'''

        # ==========================================
        # FUNCIÓN HELPER: Genera el HTML completo
        # ==========================================
        def _build_email(title_emoji, title_text, subject, detail_rows_html, extra_content="", notice_html=""):
            return subject, f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{subject}</title>
</head>
<body style="margin:0; padding:0; background-color:#f4f4f7; font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif; -webkit-font-smoothing:antialiased;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f4f4f7;">
        <tr>
            <td align="center" style="padding:24px 16px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px; background:#ffffff; border-radius:12px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                    
                    <!-- HEADER -->
                    <tr>
                        <td style="background:linear-gradient(135deg, {primary_color} 0%, {secondary_color} 100%); padding:32px 24px; text-align:center;">
                            {logo_html}
                            <h1 style="margin:0; color:#ffffff; font-size:22px; font-weight:700; letter-spacing:-0.3px;">
                                {title_emoji} {title_text}
                            </h1>
                            <p style="margin:6px 0 0 0; color:rgba(255,255,255,0.85); font-size:14px;">{business_name}</p>
                        </td>
                    </tr>
                    
                    <!-- BODY -->
                    <tr>
                        <td style="padding:28px 24px 12px 24px;">
                            {notice_html}
                            <p style="margin:0 0 16px 0; color:#333; font-size:15px; line-height:1.6;">
                                Estimado/a <strong>{customer_name}</strong>,
                            </p>
                            {extra_content}
                        </td>
                    </tr>
                    
                    <!-- DETALLES -->
                    <tr>
                        <td style="padding:0 24px 24px 24px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#fafbfc; border-radius:8px; border:1px solid #eef0f2;">
                                {detail_rows_html}
                            </table>
                        </td>
                    </tr>
                    
                    <!-- NOTAS/CTA -->
                    <tr>
                        <td style="padding:0 24px 28px 24px; text-align:center;">
                            <p style="margin:0; color:#888; font-size:13px; line-height:1.5;">
                                Si necesitas cancelar o modificar, contáctanos por WhatsApp.
                            </p>
                        </td>
                    </tr>
                    
                    <!-- FOOTER -->
                    <tr>
                        <td style="border-top:1px solid #eef0f2; padding:16px 24px; text-align:center;">
                            <p style="margin:0; color:#aaa; font-size:12px;">{footer_text}</p>
                        </td>
                    </tr>
                    
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

        # ==========================================
        # CANCELACIÓN
        # ==========================================
        if is_cancelled:
            custom_subject = templates.get('cancellation', {}).get('subject')
            subject = custom_subject.format(business_name=business_name, date=fecha_formateada) if custom_subject else f"❌ Cita Cancelada - {business_name}"
            
            rows = _detail_row("📅", "Fecha programada", fecha_formateada)
            extra = '<p style="margin:0 0 16px 0; color:#333; font-size:15px; line-height:1.6;">Tu cita ha sido <strong>cancelada</strong> exitosamente.</p>'
            extra += '<p style="margin:0 0 8px 0; color:#333; font-size:15px; line-height:1.6;">Si deseas reagendar, contáctanos nuevamente. <strong>¡Esperamos poder atenderte pronto!</strong></p>'
            
            return _build_email("❌", "Cita Cancelada", subject, rows, extra)

        # ==========================================
        # MODIFICACIÓN
        # ==========================================
        if is_modified:
            custom_subject = templates.get('modification', {}).get('subject')
            subject = custom_subject.format(business_name=business_name, date=fecha_formateada) if custom_subject else f"🔄 Cita Modificada - {business_name}"
            
            rows = _detail_row("📅", "Nueva fecha", fecha_formateada)
            rows += _detail_row("💼", "Servicio", details.get('servicio'))
            rows += _detail_row("👨‍⚕️", "Profesional", details.get('profesional'))
            rows += _detail_row("👥", "Personas", details.get('num_personas'))
            rows += _detail_row("🪑", "Área", details.get('area'))
            
            notice = '''<div style="background:#fff8e1; border-left:4px solid #ffc107; padding:12px 16px; border-radius:0 6px 6px 0; margin-bottom:16px;">
                <strong style="color:#856404;">⚠️ Tu cita ha sido modificada</strong>
                <p style="margin:4px 0 0 0; color:#856404; font-size:13px;">Verifica los nuevos detalles a continuación.</p>
            </div>'''
            extra = '<p style="margin:0 0 8px 0; color:#333; font-size:15px; line-height:1.6;">Hemos actualizado los detalles de tu cita:</p>'
            
            return _build_email("🔄", "Cita Modificada", subject, rows, extra, notice)

        # ==========================================
        # CONFIRMACIONES POR TIPO DE NEGOCIO
        # ==========================================
        custom_subject = templates.get('confirmation', {}).get('subject')
        
        if business_type == 'restaurant':
            default_subject = f"✅ Reservación Confirmada - {business_name}"
            subject = custom_subject.format(business_name=business_name, date=fecha_formateada) if custom_subject else default_subject
            
            rows = _detail_row("📅", "Fecha y hora", fecha_formateada)
            rows += _detail_row("👥", "Personas", details.get('num_personas'))
            rows += _detail_row("🪑", "Área", details.get('area'))
            rows += _detail_row("🎉", "Ocasión", details.get('ocasion'))
            
            extra = '<p style="margin:0 0 8px 0; color:#333; font-size:15px; line-height:1.6;">¡Gracias por tu reservación! Aquí están los detalles:</p>'
            extra += '''<div style="margin-top:16px; padding:12px; background:#f0fdf4; border-radius:6px; text-align:center;">
                <p style="margin:0; color:#166534; font-size:14px;">📍 Por favor llega <strong>10 minutos antes</strong> de tu reservación</p>
                <p style="margin:4px 0 0 0; color:#166534; font-size:13px;">La reservación se mantendrá por 15 minutos después de la hora programada</p>
            </div>'''
            
            return _build_email("🍽️", "Reservación Confirmada", subject, rows, extra)
            
        elif business_type == 'clinic':
            default_subject = f"✅ Cita Médica Confirmada - {business_name}"
            subject = custom_subject.format(business_name=business_name, date=fecha_formateada) if custom_subject else default_subject
            
            rows = _detail_row("📅", "Fecha y hora", fecha_formateada)
            rows += _detail_row("👨‍⚕️", "Profesional", details.get('profesional'))
            rows += _detail_row("📋", "Tipo de consulta", details.get('servicio'))
            rows += _detail_row("💰", "Precio", details.get('precio'))
            
            extra = '<p style="margin:0 0 8px 0; color:#333; font-size:15px; line-height:1.6;">Su cita médica ha sido confirmada:</p>'
            extra += '''<div style="margin-top:16px; padding:12px; background:#eff6ff; border-radius:6px;">
                <p style="margin:0 0 4px 0; color:#1e40af; font-size:14px; font-weight:600;">📋 Recomendaciones:</p>
                <ul style="margin:0; padding-left:20px; color:#1e40af; font-size:13px; line-height:1.8;">
                    <li>Llegue 15 minutos antes de su cita</li>
                    <li>Traiga su documento de identidad</li>
                    <li>Si tiene estudios previos, tráigalos consigo</li>
                </ul>
            </div>'''
            
            return _build_email("🏥", "Cita Confirmada", subject, rows, extra)
            
        elif business_type == 'salon':
            default_subject = f"✅ Cita Confirmada - {business_name}"
            subject = custom_subject.format(business_name=business_name, date=fecha_formateada) if custom_subject else default_subject
            
            rows = _detail_row("📅", "Fecha y hora", fecha_formateada)
            rows += _detail_row("💅", "Servicio", details.get('servicio'))
            rows += _detail_row("👤", "Profesional", details.get('profesional'))
            rows += _detail_row("💰", "Precio", details.get('precio'))
            
            extra = '<p style="margin:0 0 8px 0; color:#333; font-size:15px; line-height:1.6;">¡Tu cita ha sido confirmada! ✨ Aquí están los detalles:</p>'
            extra += '''<div style="margin-top:16px; padding:12px; background:#fdf2f8; border-radius:6px; text-align:center;">
                <p style="margin:0; color:#9d174d; font-size:14px;">Llega <strong>5-10 minutos antes</strong> de tu cita 💖</p>
            </div>'''
            
            return _build_email("💇‍♀️", "Cita Confirmada", subject, rows, extra)
            
        else:  # store u otros
            default_subject = f"✅ Confirmación - {business_name}"
            subject = custom_subject.format(business_name=business_name, date=fecha_formateada) if custom_subject else default_subject
            
            rows = _detail_row("📅", "Fecha", fecha_formateada)
            rows += _detail_row("📦", "Producto", details.get('servicio'))
            rows += _detail_row("💰", "Precio", details.get('precio'))
            rows += _detail_row("📍", "Dirección de entrega", details.get('direccion'))
            rows += _detail_row("📋", "Detalles", details.get('detalles'))
            
            extra = '<p style="margin:0 0 8px 0; color:#333; font-size:15px; line-height:1.6;">Su entrega ha sido programada:</p>'
            extra += '''<div style="margin-top:16px; padding:12px; background:#f0fdf4; border-radius:6px; text-align:center;">
                <p style="margin:0; color:#166534; font-size:14px;">📞 Nos pondremos en contacto antes de la entrega</p>
            </div>'''
            
            return _build_email("📦", "Entrega Programada", subject, rows, extra)

# Instancia global
email_service = EmailService()

