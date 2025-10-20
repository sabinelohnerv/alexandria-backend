import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.staff_whitelist.models import StaffWhitelist  # ajusta el import al path real

User = get_user_model()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin", email="admin@example.com",
        password="pass", is_staff=True, is_superuser=False
    )

@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        username="root", email="root@example.com", password="pass"
    )

@pytest.fixture
def normal_user(db):
    return User.objects.create_user(
        username="user", email="user@example.com", password="pass"
    )

@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client

@pytest.fixture
def user_client(api_client, normal_user):
    api_client.force_authenticate(user=normal_user)
    return api_client

@pytest.fixture
def entry_factory(db, admin_user):
    def make(**kwargs):
        defaults = {
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "role": StaffWhitelist.Role.USER,
            "created_by": admin_user,
            "is_active": True,
        }
        defaults.update(kwargs)
        return StaffWhitelist.objects.create(**defaults)
    return make
