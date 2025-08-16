from typing import Optional
from django.db import transaction
from .models import StaffWhitelist

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
        entry.is_active = False
        entry.save(update_fields=["is_active", "updated_at"])
        return entry

    @staticmethod
    @transaction.atomic
    def reactivate_entry(*, entry: StaffWhitelist) -> StaffWhitelist:
        entry.is_active = True
        entry.save(update_fields=["is_active", "updated_at"])
        return entry
