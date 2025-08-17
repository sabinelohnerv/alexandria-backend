from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import StaffWhitelist


User = get_user_model()

def _revoke_user_refresh_tokens_if_possible(user):
    """
    Blacklistea todos los refresh tokens del usuario si está disponible
    rest_framework_simplejwt.token_blacklist. Falla en silencio si no está.
    """
    if not getattr(settings, "WHITELIST_REVOKE_REFRESH_ON_DEACTIVATE", True):
        return
    try:
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
    except Exception:
        return  
    try:
        for tok in OutstandingToken.objects.filter(user=user):
            try:
                BlacklistedToken.objects.get_or_create(token=tok)
            except Exception:
                pass
    except Exception:
        pass


def _set_users_active_by_email(email: str, *, active: bool) -> int:
    """
    Ajusta is_active de todos los usuarios cuyo email coincida (case-insensitive).
    Por defecto, no toca superusuarios salvo que WHITELIST_DISABLE_SUPERUSERS=True.
    Retorna cantidad de filas actualizadas.
    """
    qs = User.objects.filter(email__iexact=email)
    if not getattr(settings, "WHITELIST_DISABLE_SUPERUSERS", False):
        qs = qs.filter(is_superuser=False)

    users = list(qs) 
    if not users:
        return 0

    updated = qs.update(is_active=active)

    if not active:
        for u in users:
            _revoke_user_refresh_tokens_if_possible(u)

    return updated

class StaffWhitelistService:
    @staticmethod
    @transaction.atomic
    def create_entry(*, first_name: str, last_name: str, email: str, created_by, role: Optional[str] = None) -> StaffWhitelist:
        email = email.strip().lower()
        role = (role or StaffWhitelist.Role.USER).strip().lower()
        if role not in [c for c, _ in StaffWhitelist.Role.choices]:
            role = StaffWhitelist.Role.USER
        entry = StaffWhitelist.objects.create(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=email,
            role=role,
            created_by=created_by,
        )
        return entry

    @staticmethod
    @transaction.atomic
    def update_entry(*, entry: StaffWhitelist, first_name: Optional[str] = None,
                     last_name: Optional[str] = None, email: Optional[str] = None,
                     role: Optional[str] = None) -> StaffWhitelist:
        if first_name is not None:
            entry.first_name = first_name.strip()
        if last_name is not None:
            entry.last_name = last_name.strip()
        if email is not None:
            entry.email = email.strip().lower()
        if role is not None:
            role = role.strip().lower()
            if role in [c for c, _ in StaffWhitelist.Role.choices]:
                entry.role = role
        entry.save(update_fields=["first_name", "last_name", "email", "role", "updated_at"])
        return entry

    @staticmethod
    @transaction.atomic
    def deactivate_entry(*, entry: StaffWhitelist) -> StaffWhitelist:
        """
        Soft delete: marca el whitelist como inactivo y desactiva usuarios con ese email.
        Opcionalmente revoca refresh tokens (SimpleJWT token_blacklist).
        """
        if not entry.is_active:
            return entry
        entry.is_active = False
        entry.updated_at = timezone.now()
        entry.save(update_fields=["is_active", "updated_at"])

        _set_users_active_by_email(entry.email, active=False)
        return entry

    @staticmethod
    @transaction.atomic
    def reactivate_entry(*, entry: StaffWhitelist) -> StaffWhitelist:
        """
        Reactiva el whitelist y re-activa usuarios con ese email (si existen).
        """
        if entry.is_active:
            return entry
        entry.is_active = True
        entry.updated_at = timezone.now()
        entry.save(update_fields=["is_active", "updated_at"])

        _set_users_active_by_email(entry.email, active=True)
        return entry
