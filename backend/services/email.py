import ssl
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import get_settings

settings = get_settings()


class EmailService:
    @staticmethod
    async def send_email(to: str, subject: str, html_body: str, text_body: str = None):
        message = MIMEMultipart("alternative")
        message["From"] = settings.email_from
        message["To"] = to
        message["Subject"] = subject

        if text_body:
            message.attach(MIMEText(text_body, "plain"))
        message.attach(MIMEText(html_body, "html"))

        # Create SSL context that doesn't verify hostname (for internal SMTP servers)
        tls_context = None
        if settings.smtp_start_tls:
            tls_context = ssl.create_default_context()
            if settings.smtp_skip_verify:
                tls_context.check_hostname = False
                tls_context.verify_mode = ssl.CERT_NONE

        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            start_tls=settings.smtp_start_tls,
            tls_context=tls_context,
        )

    @staticmethod
    async def send_magic_link(to: str, token: str, name: str = None):
        link = f"{settings.app_url}/auth/verify?token={token}"
        greeting = f"Hi {name}," if name else "Hi,"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .button {{
                    display: inline-block;
                    padding: 12px 24px;
                    background-color: #2563eb;
                    color: white !important;
                    text-decoration: none;
                    border-radius: 6px;
                    margin: 20px 0;
                }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Sign in to AACSB Accreditation</h2>
                <p>{greeting}</p>
                <p>Click the button below to sign in to your account. This link will expire in 15 minutes.</p>
                <a href="{link}" class="button">Sign In</a>
                <p>Or copy and paste this URL into your browser:</p>
                <p style="word-break: break-all; color: #666;">{link}</p>
                <div class="footer">
                    <p>If you didn't request this email, you can safely ignore it.</p>
                    <p>NMBU - Norwegian University of Life Sciences</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        {greeting}

        Click the link below to sign in to AACSB Accreditation:
        {link}

        This link will expire in 15 minutes.

        If you didn't request this email, you can safely ignore it.
        """

        await EmailService.send_email(
            to=to,
            subject="Sign in to AACSB Accreditation",
            html_body=html_body,
            text_body=text_body,
        )
