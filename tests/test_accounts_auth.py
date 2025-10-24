"""
Tests para el módulo accounts_auth
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts_auth.serializers import get_role

User = get_user_model()


@pytest.mark.django_db
class TestGetRoleFunction:
    """Tests para la función get_role"""

    def test_get_role_admin_user(self, admin_user):
        """Prueba que admin_user retorna rol 'admin'"""
        assert get_role(admin_user) == "admin"

    def test_get_role_regular_user(self, regular_user):
        """Prueba que usuario regular retorna rol 'user'"""
        assert get_role(regular_user) == "user"

    def test_get_role_staff_user(self, user_factory):
        """Prueba que usuario staff retorna rol 'admin'"""
        staff_user = user_factory(email="staff@example.com", is_staff=True)
        assert get_role(staff_user) == "admin"


@pytest.mark.django_db
class TestJWTLoginAPI:
    """Tests para el endpoint de login JWT"""

    def test_login_success(self, api_client, regular_user):
        """Prueba login exitoso"""
        data = {
            "username": "user@example.com",
            "password": "testpass123"
        }
        response = api_client.post("/api/auth/jwt/login/", data)
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data
        assert response.data["user"]["email"] == "user@example.com"

    def test_login_with_username_field(self, api_client, regular_user):
        """Prueba login usando campo username en lugar de email"""
        data = {
            "username": "user@example.com",
            "password": "testpass123"
        }
        response = api_client.post("/api/auth/jwt/login/", data)
        assert response.status_code == status.HTTP_200_OK

    def test_login_invalid_credentials(self, api_client, regular_user):
        """Prueba login con credenciales inválidas"""
        data = {
            "username": "user@example.com",
            "password": "wrongpassword"
        }
        response = api_client.post("/api/auth/jwt/login/", data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self, api_client):
        """Prueba login con usuario inexistente"""
        data = {
            "username": "nonexistent@example.com",
            "password": "testpass123"
        }
        response = api_client.post("/api/auth/jwt/login/", data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_missing_email(self, api_client):
        """Prueba login sin email"""
        data = {
            "password": "testpass123"
        }
        response = api_client.post("/api/auth/jwt/login/", data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_missing_password(self, api_client, regular_user):
        """Prueba login sin contraseña"""
        data = {
            "username": "user@example.com"
        }
        response = api_client.post("/api/auth/jwt/login/", data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_returns_user_info(self, api_client, regular_user):
        """Prueba que login retorna información del usuario"""
        data = {
            "username": "user@example.com",
            "password": "testpass123"
        }
        response = api_client.post("/api/auth/jwt/login/", data)
        assert response.status_code == status.HTTP_200_OK
        user_data = response.data["user"]
        assert user_data["id"] == regular_user.id
        assert user_data["email"] == regular_user.email
        assert user_data["first_name"] == regular_user.first_name
        assert user_data["last_name"] == regular_user.last_name
        assert "role" in user_data

    def test_login_admin_user_has_admin_role(self, api_client, admin_user):
        """Prueba que admin tiene rol 'admin'"""
        data = {
            "username": "admin@example.com",
            "password": "testpass123"
        }
        response = api_client.post("/api/auth/jwt/login/", data)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["user"]["role"] == "admin"

@pytest.mark.django_db
class TestJWTRefreshAPI:
    """Tests para el endpoint de refresh de JWT"""

    def test_refresh_token_success(self, api_client, regular_user):
        """Prueba refresh exitoso de token"""
        refresh = RefreshToken.for_user(regular_user)
        data = {"refresh": str(refresh)}
        response = api_client.post("/api/auth/jwt/refresh/", data)
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_refresh_token_invalid(self, api_client):
        """Prueba refresh con token inválido"""
        data = {"refresh": "invalid_token"}
        response = api_client.post("/api/auth/jwt/refresh/", data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_token_missing(self, api_client):
        """Prueba refresh sin token"""
        response = api_client.post("/api/auth/jwt/refresh/", {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestMeEndpoint:
    """Tests para el endpoint /me"""

    def test_me_authenticated(self, authenticated_client, regular_user):
        """Prueba obtener información del usuario autenticado"""
        response = authenticated_client.get("/api/auth/me/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == regular_user.id
        assert response.data["email"] == regular_user.email
        assert response.data["first_name"] == regular_user.first_name
        assert response.data["last_name"] == regular_user.last_name
        assert "role" in response.data

    def test_me_unauthenticated(self, api_client):
        """Prueba que /me requiere autenticación"""
        response = api_client.get("/api/auth/me/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_me_admin_user(self, admin_client, admin_user):
        """Prueba /me con usuario admin"""
        response = admin_client.get("/api/auth/me/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["role"] == "admin"
        assert response.data["is_staff"] is True
