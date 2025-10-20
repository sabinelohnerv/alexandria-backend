import pytest
from rest_framework import serializers
from apps.staff_whitelist.models import StaffWhitelist
from apps.staff_whitelist.serializers import StaffWhitelistSerializer

@pytest.mark.django_db
def test_validate_email_lowercases(entry_factory):
    s = StaffWhitelistSerializer(data={
        "first_name": "A", "last_name": "B", "email": "MiXeD@Example.Com", "role": "user"
    })
    assert s.is_valid(), s.errors
    assert s.validated_data["email"] == "mixed@example.com"


@pytest.mark.django_db
def test_validate_role_invalid_raises():
    s = StaffWhitelistSerializer(data={
        "first_name": "A", "last_name": "B", "email": "a@b.com", "role": "boss"
    })
    with pytest.raises(serializers.ValidationError):
        s.is_valid(raise_exception=True)

@pytest.mark.django_db
def test_validate_prevent_email_change_if_active_user_with_current_email(django_user_model, entry_factory):
    entry = entry_factory(email="hold@ex.com")
    django_user_model.objects.create_user(username="u", email="hold@ex.com", password="p", is_active=True)
    s = StaffWhitelistSerializer(instance=entry, data={"email": "new@ex.com"}, partial=True)
    assert not s.is_valid()
    assert "email" in s.errors
