import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings
from app.retry_utils import exponential_backoff


@exponential_backoff(max_retries=2, base_delay=2.0, exceptions=(smtplib.SMTPException, OSError, ConnectionError))
def send_email(to_email: str, subject: str, html_body: str) -> None:
    """Send an HTML email via SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, to_email, msg.as_string())


def send_verification_email(to_email: str, verify_url: str) -> None:
    """Send the email verification link."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #fff; margin: 0; padding: 40px 20px; }}
            .container {{ max-width: 480px; margin: 0 auto; background: #141414; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 48px 40px; text-align: center; }}
            h1 {{ font-size: 24px; font-weight: 700; margin: 0 0 12px; }}
            p {{ color: #9ca3af; font-size: 15px; line-height: 1.6; margin: 0 0 32px; }}
            a.btn {{ display: inline-block; background: #fff; color: #000; font-weight: 700; font-size: 15px; padding: 14px 36px; border-radius: 12px; text-decoration: none; }}
            .note {{ font-size: 13px; color: #6b7280; margin-top: 24px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Verify your email</h1>
            <p>Click the button below to verify your email address and activate your PicUr account.</p>
            <a class="btn" href="{verify_url}">Verify Email</a>
            <p class="note">This link expires in 1 hour. If you didn't create an account, you can ignore this email.</p>
        </div>
    </body>
    </html>
    """
    send_email(to_email, "Verify your PicUr email", html)


def send_password_reset_email(to_email: str, reset_url: str) -> None:
    """Send the password reset link."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #fff; margin: 0; padding: 40px 20px; }}
            .container {{ max-width: 480px; margin: 0 auto; background: #141414; border: 1px solid rgba(255,255,255,0.08); border-radius: 16px; padding: 48px 40px; text-align: center; }}
            h1 {{ font-size: 24px; font-weight: 700; margin: 0 0 12px; }}
            p {{ color: #9ca3af; font-size: 15px; line-height: 1.6; margin: 0 0 32px; }}
            a.btn {{ display: inline-block; background: #fff; color: #000; font-weight: 700; font-size: 15px; padding: 14px 36px; border-radius: 12px; text-decoration: none; }}
            .note {{ font-size: 13px; color: #6b7280; margin-top: 24px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Reset your password</h1>
            <p>Click the button below to reset your PicUr account password. If you didn't request this, you can safely ignore this email.</p>
            <a class="btn" href="{reset_url}">Reset Password</a>
            <p class="note">This link expires in 1 hour.</p>
        </div>
    </body>
    </html>
    """
    send_email(to_email, "Reset your PicUr password", html)
