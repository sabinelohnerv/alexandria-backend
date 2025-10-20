import pytest
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model
from apps.staff_whitelist.models import StaffWhitelist
from apps.staff_whitelist.services import StaffWhitelistService

User = get_user_model()

@pytest.mark.django_db
def test_create_enforces_uniqueness_and_normalizes_email(admin_user):
    entry = StaffWhitelistService.create_entry(
        first_name="Grace", last_name="Hopper", email="  GRACE@Ex.com  ",
        role="admin", created_by=admin_user
    )
    assert entry.email == "grace@ex.com"
    with pytest.raises(ValidationError):
        StaffWhitelistService.create_entry(
            first_name="Dup", last_name="Dup", email="grace@EX.com"
        )

@pytest.mark.django_db
def test_update_syncs_user_names_and_role(entry_factory):
    entry = entry_factory(email="sync2@ex.com", role=StaffWhitelist.Role.USER)
    u = User.objects.create_user(username="u", email="sync2@ex.com", password="p", is_staff=False)
    StaffWhitelistService.update_entry(
        entry=entry, first_name="Linus", last_name="Torvalds", role="admin"
    )
    u.refresh_from_db()
    assert u.first_name == "Linus" and u.last_name == "Torvalds" and u.is_staff is True

@pytest.mark.django_db
def test_update_email_rejects_if_active_user_with_current_email(entry_factory):
    entry = entry_factory(email="mail@ex.com")
    User.objects.create_user(username="uu", email="mail@ex.com", password="p", is_active=True)
    with pytest.raises(ValidationError):
        StaffWhitelistService.update_entry(entry=entry, email="other@ex.com")

@pytest.mark.django_db
def test_update_email_duplicate_whitelist_rejected(entry_factory):
    e1 = entry_factory(email="one@ex.com")
    e2 = entry_factory(email="two@ex.com")
    with pytest.raises(ValidationError):
        StaffWhitelistService.update_entry(entry=e2, email="one@ex.com")

@pytest.mark.django_db
def test_deactivate_and_reactivate_toggle_users(entry_factory):
    entry = entry_factory(email="tog@ex.com", is_active=True)
    u = User.objects.create_user(username="u", email="tog@ex.com", password="p", is_active=True)
    StaffWhitelistService.deactivate_entry(entry=entry)
    entry.refresh_from_db(); u.refresh_from_db()
    assert entry.is_active is False and u.is_active is False
    StaffWhitelistService.reactivate_entry(entry=entry)
    entry.refresh_from_db(); u.refresh_from_db()
    assert entry.is_active is True and u.is_active is True

@pytest.mark.django_db
def test_superusers_not_disabled_by_default(entry_factory, superuser, settings):
    entry = entry_factory(email=superuser.email, is_active=True)
    StaffWhitelistService.deactivate_entry(entry=entry)
    superuser.refresh_from_db()
    assert superuser.is_active is True

@pytest.mark.django_db
def test_can_disable_superusers_if_setting_true(entry_factory, superuser, settings):
    settings.WHITELIST_DISABLE_SUPERUSERS = True
    entry = entry_factory(email=superuser.email, is_active=True)
    StaffWhitelistService.deactivate_entry(entry=entry)
    superuser.refresh_from_db()
    assert superuser.is_active is False
    # Respeta setting al desactivar. :contentReference[oaicite:24]{index=24}
