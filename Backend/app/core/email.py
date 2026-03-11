import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

def enviar_correo_botin(destinatario: str, nivel: int, codigo_cupon: str, descripcion_premio: str):
    remitente = "hola@tridyland.com"
    password = settings.EMAIL_PASSWORD
    servidor_smtp = "mail.spacemail.com" #
    puerto = 465                         #
    
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = f"¡Tu botín de Nivel {nivel} en Tridyland! 🎁"
    
    html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; text-align: center; color: #333; background-color: #f9f9f9; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: #ffffff; padding: 30px; border-radius: 15px; border: 2px solid #4a148c;">
                <h2 style="color: #ffaa00;">¡Felicidades Héroe! ⚔️</h2>
                <p>Has derrotado al Jefe de Nivel {nivel} y reclamaste con éxito tu recompensa:</p>
                <h3 style="color: #4a148c; font-size: 22px;">{descripcion_premio}</h3>
                <p>Ingresa este código secreto en tu carrito de compras antes de pagar:</p>
                <div style="background: #222; color: #ffaa00; padding: 15px; font-size: 24px; font-weight: bold; border-radius: 8px; display: inline-block; letter-spacing: 2px; margin: 15px 0;">
                    {codigo_cupon}
                </div>
                <p style="font-size: 12px; color: #888;">*Este código es de un solo uso y está ligado a tu cuenta.</p>
                <br>
                <p style="font-weight: bold;">¡Gracias por ser parte de Tridyland!</p>
            </div>
        </body>
    </html>
    """
    msg.attach(MIMEText(html, 'html'))
    
    try:
        # AQUI ESTA LA MAGIA: Usamos SMTP_SSL en lugar del SMTP normal
        server = smtplib.SMTP_SSL(servidor_smtp, puerto) 
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        print(f"📧 Correo enviado con madres a {destinatario}")
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")

def enviar_correo_experiencia(destinatario: str, xp_ganada: int, xp_total: int, nivel_actual: int):
    remitente = "hola@tridyland.com"
    password = settings.EMAIL_PASSWORD
    servidor_smtp = "mail.spacemail.com"
    puerto = 465
    
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = f"¡+{xp_ganada} XP ganados en Tridyland! ⚔️"
    
    html = f"""
    <html>
        <body style="font-family: Arial, sans-serif; text-align: center; color: #333; background-color: #1a1a2e; padding: 20px;">
            <div style="max-width: 500px; margin: auto; background: #16213e; padding: 30px; border-radius: 15px; border: 2px solid #ffaa00;">
                <h2 style="color: #ffeb3b;">¡Botín de Compra Asegurado! 🛍️</h2>
                <p style="color: #ccc;">Gracias por tu pedido. Los Dioses de la Impresión 3D te han otorgado:</p>
                <h1 style="color: #00e676; font-size: 40px; margin: 10px 0;">+{xp_ganada} XP</h1>
                
                <div style="background: #0f3460; padding: 15px; border-radius: 8px; margin-top: 20px;">
                    <p style="color: #fff; margin: 0; font-size: 14px;">🌟 Experiencia Total: <strong>{xp_total} XP</strong></p>
                    <p style="color: #ffaa00; margin: 5px 0 0 0; font-size: 18px; font-weight: bold;">🛡️ Eres Nivel {nivel_actual}</p>
                </div>
                
                <p style="color: #aaa; font-size: 12px; margin-top: 20px;">Entra a la tienda para ver qué tan cerca estás de tu próximo Jefe y recompensa.</p>
            </div>
        </body>
    </html>
    """
    msg.attach(MIMEText(html, 'html'))
    
    try:
        server = smtplib.SMTP_SSL(servidor_smtp, puerto)
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        print(f"📧 Correo de XP enviado a {destinatario}")
    except Exception as e:
        print(f"❌ Error enviando correo de XP: {e}")

def enviar_correo_bienvenida_magica(destinatario: str, nombre: str, token: str, xp: int):
    remitente = "hola@tridyland.com"
    password = settings.EMAIL_PASSWORD
    servidor_smtp = "mail.spacemail.com"
    puerto = 465
    
    msg = MIMEMultipart()
    msg['From'] = remitente
    msg['To'] = destinatario
    msg['Subject'] = f"¡Bienvenido a Tridyland! ⚔️"
    
    magic_link = f"https://www.tridyland.com/account/register?email={destinatario}"
    
    html = f"""
    <div style="font-family: Arial; text-align: center; background: #1a1a2e; color: white; padding: 30px; border-radius: 15px;">
        <h1 style="color: #00ffcc;">¡BIENVENIDO A TRIDYLAND, {nombre.upper()}! 🚀</h1>
        <p>Tu aventura comienza hoy. Con tu compra en la Expo has desbloqueado:</p>
        <h2 style="color: #ffaa00;">+{xp} PUNTOS DE EXPERIENCIA</h2>
        <hr style="border: 1px solid #444;">
        <p>No necesitas contraseña. Usa este portal dimensional para entrar a tu perfil y ver tus premios:</p>
        <a href="{magic_link}" style="background: #ff00ff; color: white; padding: 15px 25px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; margin: 20px 0;">
            ENTRAR A MI PERFIL
        </a>
        <p style="font-size: 10px; color: #888;">Este link es personal y secreto. No lo compartas con otros goblins.</p>
    </div>
    """
    msg.attach(MIMEText(html, 'html'))
    
    try:
        server = smtplib.SMTP_SSL(servidor_smtp, puerto)
        server.login(remitente, password)
        server.sendmail(remitente, destinatario, msg.as_string())
        server.quit()
        print(f"📧 Correo de bienvenida enviado a {destinatario}")
    except Exception as e:
        print(f"❌ Error enviando correo de bienvenida: {e}")