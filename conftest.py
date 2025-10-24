"""
Configuración global de pytest para Alexandria Backend
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.staff_whitelist.models import StaffWhitelist

User = get_user_model()


@pytest.fixture
def api_client():
    """Cliente API de DRF para pruebas"""
    return APIClient()


@pytest.fixture
def user_factory(db):
    """Factory para crear usuarios de prueba"""
    def create_user(
        email="test@example.com",
        password="testpass123",
        first_name="Test",
        last_name="User",
        is_staff=False,
        is_superuser=False,
        **extra_fields
    ):
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=is_staff,
            is_superuser=is_superuser,
            **extra_fields
        )
        return user
    return create_user


@pytest.fixture
def admin_user(user_factory):
    """Usuario administrador"""
    return user_factory(
        email="admin@example.com",
        is_staff=True,
        is_superuser=True,
        first_name="Admin",
        last_name="User"
    )


@pytest.fixture
def regular_user(user_factory):
    """Usuario regular"""
    return user_factory(
        email="user@example.com",
        first_name="Regular",
        last_name="User"
    )


@pytest.fixture
def authenticated_client(api_client, regular_user):
    """Cliente autenticado con usuario regular"""
    api_client.force_authenticate(user=regular_user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """Cliente autenticado con usuario administrador"""
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def whitelist_factory(db, admin_user):
    """Factory para crear entradas de whitelist"""
    def create_whitelist(
        email="whitelist@example.com",
        first_name="Whitelist",
        last_name="User",
        role=StaffWhitelist.Role.USER,
        is_active=True,
        **extra_fields
    ):
        return StaffWhitelist.objects.create(
            email=email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=is_active,
            created_by=admin_user,
            **extra_fields
        )
    return create_whitelist
