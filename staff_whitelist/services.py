from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

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


# ------- NUEVOS HELPERS PARA SINCRONIZAR DATOS DE USUARIO -------

def _user_model_has_field(field_name: str) -> bool:
    """Devuelve True si el modelo User tiene físicamente ese campo."""
    try:
        User._meta.get_field(field_name)
        return True
    except Exception:
        return False

def _sync_users_from_whitelist(entry: StaffWhitelist, *, first_name: Optional[str], last_name: Optional[str], role: Optional[str]) -> int:
    """
    Sincroniza datos del/los User con el email del entry (case-insensitive):
    - first_name / last_name (todos los usuarios con ese email)
    - is_staff según role (solo no-superusers)
    - role (si el modelo User tiene ese campo)
    No toca el email del User.
    Retorna cuántos registros de User fueron afectados (suma de updates).
    """
    total_updated = 0
    qs_all = User.objects.filter(email__iexact=entry.email)

    # Nombres
    if first_name is not None:
        total_updated += qs_all.update(first_name=first_name)
    if last_name is not None:
        total_updated += qs_all.update(last_name=last_name)

    # Rol -> is_staff (+ user.role si existe)
    if role is not None:
        is_admin = (role == StaffWhitelist.Role.ADMIN)
        qs_non_super = qs_all.filter(is_superuser=False)
        total_updated += qs_non_super.update(is_staff=is_admin)

        if _user_model_has_field("role"):
            total_updated += qs_all.update(role=role)

    return total_updated


# ---------------------- SERVICE ----------------------

class StaffWhitelistService:
    @staticmethod
    @transaction.atomic
    def create_entry(
        *,
        first_name: str,
        last_name: str,
        email: str,
        role: str | None = None,
        created_by: User | None = None,  # type: ignore
    ) -> StaffWhitelist:
        email_norm = email.strip().lower()
        if StaffWhitelist.objects.filter(email__iexact=email_norm).exists():
            raise ValidationError({"email": "Ya existe una entrada de whitelist con este email."})

        role_val = (role or "").strip().lower() or StaffWhitelist.Role.USER
        valid_roles = [c for c, _ in StaffWhitelist.Role.choices]
        if role_val not in valid_roles:
            raise ValidationError({"role": f"Valor inválido. Usa uno de: {valid_roles}"})

        entry = StaffWhitelist.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email_norm,
            role=role_val,
            created_by=created_by,
        )
        return entry

    @staticmethod
    @transaction.atomic
    def update_entry(
        *,
        entry: StaffWhitelist,
        first_name: str | None = None,
        last_name: str | None = None,
        role: str | None = None,
        email: str | None = None,
    ) -> StaffWhitelist:
        """
        Reglas:
        - Si se intenta CAMBIAR el email y existe un User ACTIVO con el email ACTUAL,
          rechaza (400). Tampoco permite duplicar email en otra whitelist.
        - Tras persistir cambios, sincroniza User(s) con ese email: nombres y rol (is_staff / role).
        """
        updated_fields = []

        # --- Email ---
        if email is not None:
            new_email = email.strip().lower()
            current_email = (entry.email or "").strip().lower()
            if new_email != current_email:
                if User.objects.filter(email__iexact=current_email, is_active=True).exists():
                    raise ValidationError({
                        "email": "No se puede cambiar el email porque hay un usuario activo asociado a la entrada."
                    })
                if StaffWhitelist.objects.filter(email__iexact=new_email).exclude(pk=entry.pk).exists():
                    raise ValidationError({"email": "Ya existe otra entrada de whitelist con ese email."})

                entry.email = new_email
                updated_fields.append("email")

        # --- Nombres ---
        role_val_to_sync: Optional[str] = None  
        if first_name is not None:
            entry.first_name = first_name
            updated_fields.append("first_name")

        if last_name is not None:
            entry.last_name = last_name
            updated_fields.append("last_name")

        # --- Rol ---
        if role is not None:
            role_val = (role or "").strip().lower() or StaffWhitelist.Role.USER
            valid_roles = [c for c, _ in StaffWhitelist.Role.choices]
            if role_val not in valid_roles:
                raise ValidationError({"role": f"Valor inválido. Usa uno de: {valid_roles}"})
            entry.role = role_val
            role_val_to_sync = role_val
            updated_fields.append("role")

        # --- Persistencia entry ---
        entry.updated_at = timezone.now()
        updated_fields.append("updated_at")
        entry.save(update_fields=updated_fields)

        # --- Sincronía con User(s) (todo menos email) ---
        _sync_users_from_whitelist(
            entry,
            first_name=first_name,
            last_name=last_name,
            role=role_val_to_sync,
        )

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
