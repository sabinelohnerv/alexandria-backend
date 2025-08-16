import random
from datetime import timedelta
from typing import Tuple
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from typing import Dict

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from staff_whitelist.models import StaffWhitelist
from .models import PendingRegistration

User = get_user_model()

OTP_LENGTH = 6
OTP_TTL_MINUTES = 10
MAX_OTP_ATTEMPTS = 5

RESEND_COOLDOWN_SECONDS = 60

def _generate_otp(length: int = OTP_LENGTH) -> str:
    return f"{random.randint(0, 10**length - 1):0{length}d}"

def _resolve_role_from_whitelist(email: str) -> Tuple[bool, str]:
    """
    Retorna (permitido, role). Debe estar activo en whitelist.
    """
    entry = StaffWhitelist.objects.filter(email=email.strip().lower(), is_active=True).first()
    if not entry:
        return False, "user"
    return True, entry.role

def _send_otp_email(email: str, otp: str, first_name: str):
    subject = f"{getattr(settings, 'BRAND_NAME', 'Tu cuenta')}: tu código de verificación"
    context = {
        "subject": subject,
        "first_name": first_name,
        "otp": otp,
        "ttl_minutes": OTP_TTL_MINUTES,
        "brand_name": getattr(settings, "BRAND_NAME", "Tu Marca"),
        "brand_color": getattr(settings, "BRAND_PRIMARY_COLOR", "#0d6efd"),
        "brand_logo_url": getattr(settings, "BRAND_LOGO_URL", ""),
        "frontend_url": getattr(settings, "FRONTEND_URL", ""),
        "default_from_email": getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", None),
    }

    html_body = render_to_string("emails/otp_email.html", context)
    text_body = render_to_string("emails/otp_email.txt", context)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        to=[email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=False)

@transaction.atomic
def request_registration_otp(*, first_name: str, last_name: str, email: str, password: str) -> None:
    email = email.strip().lower()

    allowed, role = _resolve_role_from_whitelist(email)
    if not allowed:
        raise PermissionError("El correo no está autorizado.")

    otp = _generate_otp()
    now = timezone.now()
    expires = now + timedelta(minutes=OTP_TTL_MINUTES)
    password_hash = make_password(password)

    pending, _created = PendingRegistration.objects.update_or_create(
        email=email,
        defaults={
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
            "password_hash": password_hash,
            "otp_code": otp,
            "otp_sent_at": now,
            "expires_at": expires,
            "attempts": 0,
            "intended_role": role,
            "is_verified": False,
        },
    )

    _send_otp_email(email=email, otp=otp, first_name=first_name)

@transaction.atomic
def confirm_registration_with_otp(*, email: str, otp_code: str) -> User:
    email = email.strip().lower()
    otp_code = otp_code.strip()

    try:
        pending = PendingRegistration.objects.select_for_update().get(email=email)
    except PendingRegistration.DoesNotExist:
        raise ValueError("No hay una solicitud de registro vigente para este correo.")

    if timezone.now() > pending.expires_at:
        raise ValueError("El código ha expirado. Solicítalo nuevamente.")

    if pending.attempts >= MAX_OTP_ATTEMPTS:
        raise ValueError("Se superó el número máximo de intentos. Solicita un nuevo código.")

    if otp_code != pending.otp_code:
        pending.attempts += 1
        pending.save(update_fields=["attempts", "updated_at"])
        raise ValueError("Código inválido.")

    allowed, role = _resolve_role_from_whitelist(email)
    if not allowed:
        raise PermissionError("El correo dejó de estar autorizado (whitelist).")

    user = User.objects.create(
        username=email,  
        email=email,
        first_name=pending.first_name,
        last_name=pending.last_name,
        password=pending.password_hash,
        is_staff=True if role == "admin" else False,
        is_superuser=False,  
        is_active=True, 
    )

    pending.is_verified = True
    pending.delete()

    return user

@transaction.atomic
def resend_registration_otp(*, email: str) -> None:
    email = email.strip().lower()

    allowed, _role = _resolve_role_from_whitelist(email)
    if not allowed:
        raise PermissionError("El correo no está autorizado (whitelist).")

    try:
        pending = PendingRegistration.objects.select_for_update().get(email=email)
    except PendingRegistration.DoesNotExist:
        raise ValueError("No hay una solicitud de registro vigente para este correo. Usa request-otp.")

    if pending.is_verified:
        raise ValueError("Esta solicitud ya fue verificada. Inicia sesión.")

    now = timezone.now()
    delta = (now - pending.otp_sent_at).total_seconds()
    if delta < RESEND_COOLDOWN_SECONDS:
        remaining = int(RESEND_COOLDOWN_SECONDS - delta)
        raise ValueError(f"Debes esperar {remaining} segundos antes de reenviar el código.")

    new_otp = _generate_otp()
    pending.otp_code = new_otp
    pending.otp_sent_at = now
    pending.expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)
    pending.resend_count += 1
    pending.save(update_fields=["otp_code", "otp_sent_at", "expires_at", "resend_count", "updated_at"])

    _send_otp_email(email=email, otp=new_otp, first_name=pending.first_name)


def get_registration_status(*, email: str) -> Dict:
    email = email.strip().lower()
    allowed, role = _resolve_role_from_whitelist(email)

    now = timezone.now()
    data = {
        "email": email,
        "allowed": allowed,
        "role": role,
        "has_pending": False,
        "status": "none",
        "expires_in_seconds": 0,
        "attempts_left": MAX_OTP_ATTEMPTS,
        "resend_available": False,
        "resend_in_seconds": 0,
        "confirm_available": False,
        "resend_count": 0,
    }

    try:
        pending = PendingRegistration.objects.get(email=email)
    except PendingRegistration.DoesNotExist:
        return data

    data["has_pending"] = True
    data["resend_count"] = pending.resend_count

    if pending.is_verified:
        data["status"] = "verified"
        data["confirm_available"] = False
        data["resend_available"] = False
        return data

    expired = now > pending.expires_at
    data["status"] = "expired" if expired else "pending"

    if not expired:
        ttl_sec = int((pending.expires_at - now).total_seconds())
        data["expires_in_seconds"] = max(0, ttl_sec)
        attempts_left = max(0, MAX_OTP_ATTEMPTS - pending.attempts)
        data["attempts_left"] = attempts_left
        data["confirm_available"] = attempts_left > 0 and allowed

    delta = int((now - pending.otp_sent_at).total_seconds())
    remain = max(0, RESEND_COOLDOWN_SECONDS - delta)
    data["resend_in_seconds"] = remain
    data["resend_available"] = (remain == 0) and (not pending.is_verified) and allowed

    return data