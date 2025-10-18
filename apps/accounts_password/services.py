import random
from datetime import timedelta
from typing import Dict
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db import transaction
from django.utils import timezone

from .models import PasswordResetTicket

User = get_user_model()

OTP_LENGTH = 6
OTP_TTL_MINUTES = 15
MAX_OTP_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60  

def _generate_otp(length: int = OTP_LENGTH) -> str:
    return f"{random.randint(0, 10**length - 1):0{length}d}"

def _send_reset_email(*, email: str, first_name: str, otp: str):
    subject = f"{getattr(settings, 'BRAND_NAME', 'Tu cuenta')}: recupera tu contraseña"
    ctx = {
        "subject": subject,
        "first_name": first_name or email.split("@")[0],
        "otp": otp,
        "ttl_minutes": OTP_TTL_MINUTES,
        "brand_name": getattr(settings, "BRAND_NAME", "Tu Marca"),
        "brand_color": getattr(settings, "BRAND_PRIMARY_COLOR", "#0d6efd"),
        "brand_logo_url": getattr(settings, "BRAND_LOGO_URL", ""),
        "frontend_url": getattr(settings, "FRONTEND_URL", ""),
        "default_from_email": getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", None),
    }
    html = render_to_string("emails/password_reset_email.html", ctx)
    txt = render_to_string("emails/password_reset_email.txt", ctx)
    msg = EmailMultiAlternatives(
        subject=subject, body=txt,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        to=[email],
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)

@transaction.atomic
def request_password_reset(*, email: str) -> None:
    """Genera OTP y envía correo. No revela si el usuario existe (respuesta genérica)."""
    email = email.strip().lower()
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if not user:
        return

    now = timezone.now()
    otp = _generate_otp()
    expires = now + timedelta(minutes=OTP_TTL_MINUTES)

    ticket = PasswordResetTicket.objects.filter(user=user, is_used=False).order_by("-created_at").first()
    if ticket:
        delta = (now - ticket.otp_sent_at).total_seconds()
        if delta < RESEND_COOLDOWN_SECONDS:
            remaining = int(RESEND_COOLDOWN_SECONDS - delta)
            raise ValueError(f"Debes esperar {remaining} segundos antes de volver a solicitar el código.")
        ticket.otp_code = otp
        ticket.otp_sent_at = now
        ticket.expires_at = expires
        ticket.resend_count += 1
        ticket.attempts = ticket.attempts  
        ticket.save(update_fields=["otp_code","otp_sent_at","expires_at","resend_count","updated_at"])
    else:
        ticket = PasswordResetTicket.objects.create(
            user=user,
            email=email,
            otp_code=otp,
            otp_sent_at=now,
            expires_at=expires,
        )

    _send_reset_email(email=email, first_name=user.first_name, otp=otp)

@transaction.atomic
def resend_password_reset(*, email: str) -> None:
    """Reenvía OTP con cooldown; no revela existencia del usuario."""
    email = email.strip().lower()
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if not user:
        return

    try:
        ticket = PasswordResetTicket.objects.select_for_update().filter(user=user, is_used=False).latest("created_at")
    except PasswordResetTicket.DoesNotExist:
        return request_password_reset(email=email)

    now = timezone.now()
    delta = (now - ticket.otp_sent_at).total_seconds()
    if delta < RESEND_COOLDOWN_SECONDS:
        remaining = int(RESEND_COOLDOWN_SECONDS - delta)
        raise ValueError(f"Debes esperar {remaining} segundos antes de reenviar el código.")

    ticket.otp_code = _generate_otp()
    ticket.otp_sent_at = now
    ticket.expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)
    ticket.resend_count += 1
    ticket.save(update_fields=["otp_code","otp_sent_at","expires_at","resend_count","updated_at"])

    _send_reset_email(email=email, first_name=user.first_name, otp=ticket.otp_code)

@transaction.atomic
def confirm_password_reset(*, email: str, otp_code: str, new_password: str) -> None:
    """Valida OTP y cambia la contraseña."""
    email = email.strip().lower()
    otp_code = otp_code.strip()
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if not user:
        raise ValueError("Código inválido o expirado.")

    try:
        ticket = PasswordResetTicket.objects.select_for_update().filter(user=user, is_used=False).latest("created_at")
    except PasswordResetTicket.DoesNotExist:
        raise ValueError("Código inválido o expirado.")

    now = timezone.now()
    if now > ticket.expires_at:
        raise ValueError("El código ha expirado. Solicita uno nuevo.")
    if ticket.attempts >= MAX_OTP_ATTEMPTS:
        raise ValueError("Se superó el número máximo de intentos. Solicita un nuevo código.")

    if otp_code != ticket.otp_code:
        ticket.attempts += 1
        ticket.save(update_fields=["attempts","updated_at"])
        raise ValueError("Código inválido.")

    user.password = make_password(new_password)
    user.save(update_fields=["password"])

    ticket.is_used = True
    ticket.save(update_fields=["is_used","updated_at"])
