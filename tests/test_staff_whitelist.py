"""
Tests para el módulo staff_whitelist
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from apps.staff_whitelist.models import StaffWhitelist
from apps.staff_whitelist.services import StaffWhitelistService
from rest_framework.exceptions import ValidationError

User = get_user_model()


@pytest.mark.django_db
class TestStaffWhitelistModel:
    """Tests para el modelo StaffWhitelist"""

    def test_create_whitelist_entry(self, admin_user):
        """Prueba creación de entrada en whitelist"""
        entry = StaffWhitelist.objects.create(
            email="test@example.com",
            first_name="Test",
            last_name="User",
            role=StaffWhitelist.Role.USER,
            created_by=admin_user
        )
        assert entry.email == "test@example.com"
        assert entry.first_name == "Test"
        assert entry.last_name == "User"
        assert entry.role == StaffWhitelist.Role.USER
        assert entry.is_active is True
        assert entry.created_by == admin_user

    def test_whitelist_str_representation(self, admin_user):
        """Prueba representación en string del modelo"""
        entry = StaffWhitelist.objects.create(
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            role=StaffWhitelist.Role.ADMIN,
            created_by=admin_user
        )
        expected = "John Doe <test@example.com> [admin]"
        assert str(entry) == expected

    def test_is_admin_property(self, admin_user):
        """Prueba propiedad is_admin"""
        admin_entry = StaffWhitelist.objects.create(
            email="admin@example.com",
            first_name="Admin",
            last_name="User",
            role=StaffWhitelist.Role.ADMIN,
            created_by=admin_user
        )
        user_entry = StaffWhitelist.objects.create(
            email="user@example.com",
            first_name="Regular",
            last_name="User",
            role=StaffWhitelist.Role.USER,
            created_by=admin_user
        )
        assert admin_entry.is_admin is True
        assert user_entry.is_admin is False

    def test_unique_email_constraint(self, admin_user):
        """Prueba que el email debe ser único"""
        StaffWhitelist.objects.create(
            email="test@example.com",
            first_name="First",
            last_name="User",
            role=StaffWhitelist.Role.USER,
            created_by=admin_user
        )
        with pytest.raises(Exception):
            StaffWhitelist.objects.create(
                email="test@example.com",
                first_name="Second",
                last_name="User",
                role=StaffWhitelist.Role.USER,
                created_by=admin_user
            )


@pytest.mark.django_db
class TestStaffWhitelistService:
    """Tests para StaffWhitelistService"""

    def test_create_entry_success(self, admin_user):
        """Prueba creación exitosa de entrada"""
        entry = StaffWhitelistService.create_entry(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            role=StaffWhitelist.Role.USER,
            created_by=admin_user
        )
        assert entry.email == "test@example.com"
        assert entry.first_name == "Test"
        assert entry.last_name == "User"
        assert entry.role == StaffWhitelist.Role.USER

    def test_create_entry_normalizes_email(self, admin_user):
        """Prueba que el email se normaliza a minúsculas"""
        entry = StaffWhitelistService.create_entry(
            first_name="Test",
            last_name="User",
            email="TEST@EXAMPLE.COM",
            role=StaffWhitelist.Role.USER,
            created_by=admin_user
        )
        assert entry.email == "test@example.com"

    def test_create_entry_duplicate_email_fails(self, admin_user):
        """Prueba que no se puede crear entrada con email duplicado"""
        StaffWhitelistService.create_entry(
            first_name="First",
            last_name="User",
            email="test@example.com",
            role=StaffWhitelist.Role.USER,
            created_by=admin_user
        )
        with pytest.raises(ValidationError) as exc_info:
            StaffWhitelistService.create_entry(
                first_name="Second",
                last_name="User",
                email="test@example.com",
                role=StaffWhitelist.Role.USER,
                created_by=admin_user
            )
        assert "email" in exc_info.value.detail

    def test_create_entry_invalid_role_fails(self, admin_user):
        """Prueba que falla con rol inválido"""
        with pytest.raises(ValidationError) as exc_info:
            StaffWhitelistService.create_entry(
                first_name="Test",
                last_name="User",
                email="test@example.com",
                role="invalid_role",
                created_by=admin_user
            )
        assert "role" in exc_info.value.detail

    def test_update_entry_first_name(self, whitelist_factory):
        """Prueba actualización de nombre"""
        entry = whitelist_factory(email="test@example.com", first_name="Old")
        updated = StaffWhitelistService.update_entry(
            entry=entry,
            first_name="New"
        )
        assert updated.first_name == "New"

    def test_update_entry_role(self, whitelist_factory):
        """Prueba actualización de rol"""
        entry = whitelist_factory(email="test@example.com", role=StaffWhitelist.Role.USER)
        updated = StaffWhitelistService.update_entry(
            entry=entry,
            role=StaffWhitelist.Role.ADMIN
        )
        assert updated.role == StaffWhitelist.Role.ADMIN

    def test_deactivate_entry(self, whitelist_factory):
        """Prueba desactivación de entrada"""
        entry = whitelist_factory(email="test@example.com", is_active=True)
        deactivated = StaffWhitelistService.deactivate_entry(entry=entry)
        assert deactivated.is_active is False

    def test_deactivate_entry_idempotent(self, whitelist_factory):
        """Prueba que desactivar entrada ya inactiva no causa error"""
        entry = whitelist_factory(email="test@example.com", is_active=False)
        deactivated = StaffWhitelistService.deactivate_entry(entry=entry)
        assert deactivated.is_active is False

    def test_reactivate_entry(self, whitelist_factory):
        """Prueba reactivación de entrada"""
        entry = whitelist_factory(email="test@example.com", is_active=False)
        reactivated = StaffWhitelistService.reactivate_entry(entry=entry)
        assert reactivated.is_active is True

    def test_reactivate_entry_idempotent(self, whitelist_factory):
        """Prueba que reactivar entrada ya activa no causa error"""
        entry = whitelist_factory(email="test@example.com", is_active=True)
        reactivated = StaffWhitelistService.reactivate_entry(entry=entry)
        assert reactivated.is_active is True


@pytest.mark.django_db
class TestStaffWhitelistAPI:
    """Tests para los endpoints de la API de whitelist"""

    def test_list_whitelist_requires_admin(self, api_client):
        """Prueba que listar whitelist requiere ser admin"""
        response = api_client.get("/api/whitelist/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_whitelist_as_admin(self, admin_client, whitelist_factory):
        """Prueba listar whitelist como admin"""
        whitelist_factory(email="test1@example.com")
        whitelist_factory(email="test2@example.com")
        response = admin_client.get("/api/whitelist/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 2

    def test_list_whitelist_filters_inactive_by_default(self, admin_client, whitelist_factory):
        """Prueba que por defecto solo muestra entradas activas"""
        whitelist_factory(email="active@example.com", is_active=True)
        whitelist_factory(email="inactive@example.com", is_active=False)
        response = admin_client.get("/api/whitelist/")
        assert response.status_code == status.HTTP_200_OK
        emails = [item["email"] for item in response.data["results"]]
        assert "active@example.com" in emails
        assert "inactive@example.com" not in emails

    def test_create_whitelist_entry(self, admin_client):
        """Prueba crear entrada en whitelist"""
        data = {
            "email": "newuser@example.com",
            "first_name": "New",
            "last_name": "User",
            "role": "user"
        }
        response = admin_client.post("/api/whitelist/", data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "newuser@example.com"

    def test_create_whitelist_duplicate_email_fails(self, admin_client, whitelist_factory):
        """Prueba que no se puede crear entrada con email duplicado"""
        whitelist_factory(email="existing@example.com")
        data = {
            "email": "existing@example.com",
            "first_name": "New",
            "last_name": "User",
            "role": "user"
        }
        response = admin_client.post("/api/whitelist/", data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_whitelist_entry(self, admin_client, whitelist_factory):
        """Prueba actualizar entrada en whitelist"""
        entry = whitelist_factory(email="test@example.com", first_name="Old")
        data = {"first_name": "Updated"}
        response = admin_client.patch(f"/api/whitelist/{entry.id}/", data)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["first_name"] == "Updated"

    def test_deactivate_whitelist_entry(self, admin_client, whitelist_factory):
        """Prueba desactivar entrada en whitelist"""
        entry = whitelist_factory(email="test@example.com", is_active=True)
        response = admin_client.post(f"/api/whitelist/{entry.id}/deactivate/")
        assert response.status_code == status.HTTP_200_OK
        entry.refresh_from_db()
        assert entry.is_active is False

    def test_reactivate_whitelist_entry(self, admin_client, whitelist_factory):
        """Prueba reactivar entrada en whitelist"""
        entry = whitelist_factory(email="test@example.com", is_active=False)
        response = admin_client.post(f"/api/whitelist/{entry.id}/reactivate/")
        assert response.status_code == status.HTTP_200_OK
        entry.refresh_from_db()
        assert entry.is_active is True

    def test_search_whitelist(self, admin_client, whitelist_factory):
        """Prueba búsqueda en whitelist"""
        whitelist_factory(email="john@example.com", first_name="John", last_name="Doe")
        whitelist_factory(email="jane@example.com", first_name="Jane", last_name="Smith")
        response = admin_client.get("/api/whitelist/?search=John")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 1
        assert response.data["results"][0]["first_name"] == "John"
