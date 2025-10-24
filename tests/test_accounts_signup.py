"""
Tests para el módulo accounts_signup
"""
import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework import status
from apps.accounts_signup.models import PendingRegistration
from apps.accounts_signup.services import (
    request_registration_otp,
    confirm_registration_with_otp,
    resend_registration_otp,
    get_registration_status
)

User = get_user_model()


@pytest.mark.django_db
class TestPendingRegistrationModel:
    """Tests para el modelo PendingRegistration"""

    def test_create_pending_registration(self):
        """Prueba creación de registro pendiente"""
        expires = timezone.now() + timedelta(minutes=10)
        pending = PendingRegistration.objects.create(
            email="test@example.com",
            first_name="Test",
            last_name="User",
            password_hash="hashed_password",
            otp_code="123456",
            expires_at=expires
        )
        assert pending.email == "test@example.com"
        assert pending.otp_code == "123456"
        assert pending.attempts == 0
        assert pending.is_verified is False

    def test_pending_registration_str(self):
        """Prueba representación en string"""
        expires = timezone.now() + timedelta(minutes=10)
        pending = PendingRegistration.objects.create(
            email="test@example.com",
            first_name="Test",
            last_name="User",
            password_hash="hashed_password",
            otp_code="123456",
            expires_at=expires
        )
        assert "test@example.com" in str(pending)


@pytest.mark.django_db
class TestRegistrationOTPService:
    """Tests para el servicio de OTP de registro"""

    def test_request_otp_success(self, whitelist_factory):
        """Prueba solicitud exitosa de OTP"""
        whitelist_factory(email="test@example.com", first_name="Test", last_name="User")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        pending = PendingRegistration.objects.get(email="test@example.com")
        assert pending.first_name == "Test"
        assert pending.last_name == "User"
        assert len(pending.otp_code) == 6
        assert pending.attempts == 0
        assert len(mail.outbox) == 1
        assert "test@example.com" in mail.outbox[0].to

    def test_request_otp_not_in_whitelist(self):
        """Prueba que falla si el email no está en whitelist"""
        with pytest.raises(PermissionError) as exc_info:
            request_registration_otp(email="notallowed@example.com", password="testpass123")
        assert "no está autorizado" in str(exc_info.value)

    def test_request_otp_normalizes_email(self, whitelist_factory):
        """Prueba que el email se normaliza a minúsculas"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="TEST@EXAMPLE.COM", password="testpass123")
        
        pending = PendingRegistration.objects.get(email="test@example.com")
        assert pending.email == "test@example.com"

    def test_request_otp_updates_existing_pending(self, whitelist_factory):
        """Prueba que actualiza registro pendiente existente"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="test@example.com", password="pass1")
        first_otp = PendingRegistration.objects.get(email="test@example.com").otp_code
        
        request_registration_otp(email="test@example.com", password="pass2")
        second_otp = PendingRegistration.objects.get(email="test@example.com").otp_code
        
        assert PendingRegistration.objects.filter(email="test@example.com").count() == 1
        assert first_otp != second_otp

    def test_confirm_otp_success(self, whitelist_factory):
        """Prueba confirmación exitosa de OTP"""
        whitelist_factory(email="test@example.com", first_name="Test", last_name="User")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        pending = PendingRegistration.objects.get(email="test@example.com")
        user = confirm_registration_with_otp(email="test@example.com", otp_code=pending.otp_code)
        
        assert user.email == "test@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.is_active is True
        assert not PendingRegistration.objects.filter(email="test@example.com").exists()

    def test_confirm_otp_invalid_code(self, whitelist_factory):
        """Prueba que falla con código OTP inválido"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        with pytest.raises(ValueError) as exc_info:
            confirm_registration_with_otp(email="test@example.com", otp_code="000000")
        assert "inválido" in str(exc_info.value)

    def test_confirm_otp_expired(self, whitelist_factory):
        """Prueba que falla con código expirado"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        pending = PendingRegistration.objects.get(email="test@example.com")
        pending.expires_at = timezone.now() - timedelta(minutes=1)
        pending.save()
        
        with pytest.raises(ValueError) as exc_info:
            confirm_registration_with_otp(email="test@example.com", otp_code=pending.otp_code)
        assert "expirado" in str(exc_info.value)

    def test_confirm_otp_max_attempts(self, whitelist_factory):
        """Prueba que falla después de máximo de intentos"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        pending = PendingRegistration.objects.get(email="test@example.com")
        pending.attempts = 5
        pending.save()
        
        with pytest.raises(ValueError) as exc_info:
            confirm_registration_with_otp(email="test@example.com", otp_code=pending.otp_code)
        assert "máximo de intentos" in str(exc_info.value)

    def test_confirm_otp_no_pending_registration(self):
        """Prueba que falla si no hay registro pendiente"""
        with pytest.raises(ValueError) as exc_info:
            confirm_registration_with_otp(email="test@example.com", otp_code="123456")
        assert "No hay una solicitud" in str(exc_info.value)

    def test_resend_otp_success(self, whitelist_factory):
        """Prueba reenvío exitoso de OTP"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        pending = PendingRegistration.objects.get(email="test@example.com")
        old_otp = pending.otp_code
        pending.otp_sent_at = timezone.now() - timedelta(seconds=61)
        pending.save()
        
        resend_registration_otp(email="test@example.com")
        
        pending.refresh_from_db()
        assert pending.otp_code != old_otp
        assert pending.resend_count == 1
        assert len(mail.outbox) == 2

    def test_resend_otp_cooldown(self, whitelist_factory):
        """Prueba que respeta el cooldown de reenvío"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        with pytest.raises(ValueError) as exc_info:
            resend_registration_otp(email="test@example.com")
        assert "esperar" in str(exc_info.value)

    def test_resend_otp_not_in_whitelist(self, whitelist_factory):
        """Prueba que falla si el email no está en whitelist"""
        whitelist_factory(email="test@example.com", is_active=True)
        request_registration_otp(email="test@example.com", password="testpass123")
        
        # Desactivar whitelist
        from apps.staff_whitelist.models import StaffWhitelist
        StaffWhitelist.objects.filter(email="test@example.com").update(is_active=False)
        
        pending = PendingRegistration.objects.get(email="test@example.com")
        pending.otp_sent_at = timezone.now() - timedelta(seconds=61)
        pending.save()
        
        with pytest.raises(PermissionError):
            resend_registration_otp(email="test@example.com")

    def test_get_registration_status_no_pending(self, whitelist_factory):
        """Prueba obtener estado sin registro pendiente"""
        whitelist_factory(email="test@example.com")
        status = get_registration_status(email="test@example.com")
        
        assert status["email"] == "test@example.com"
        assert status["allowed"] is True
        assert status["has_pending"] is False
        assert status["status"] == "none"

    def test_get_registration_status_with_pending(self, whitelist_factory):
        """Prueba obtener estado con registro pendiente"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        status = get_registration_status(email="test@example.com")
        
        assert status["has_pending"] is True
        assert status["status"] == "pending"
        assert status["expires_in_seconds"] > 0
        assert status["attempts_left"] == 5

    def test_get_registration_status_not_allowed(self):
        """Prueba obtener estado de email no autorizado"""
        status = get_registration_status(email="notallowed@example.com")
        
        assert status["allowed"] is False
        assert status["has_pending"] is False


@pytest.mark.django_db
class TestRegistrationAPI:
    """Tests para los endpoints de la API de registro"""

    def test_request_otp_endpoint(self, api_client, whitelist_factory):
        """Prueba endpoint de solicitud de OTP"""
        whitelist_factory(email="test@example.com")
        data = {
            "email": "test@example.com",
            "password": "testpass123"
        }
        response = api_client.post("/api/auth/register/request-otp", data)
        assert response.status_code == status.HTTP_200_OK or response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "OTP enviado" in response.data["detail"]

    def test_request_otp_not_in_whitelist(self, api_client):
        """Prueba que falla si no está en whitelist"""
        data = {
            "email": "notallowed@example.com",
            "password": "testpass123"
        }
        response = api_client.post("/api/auth/register/request-otp", data)
        assert response.status_code == status.HTTP_403_FORBIDDEN or response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_confirm_otp_endpoint(self, api_client, whitelist_factory):
        """Prueba endpoint de confirmación de OTP"""
        whitelist_factory(email="test@example.com", first_name="Test", last_name="User")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        pending = PendingRegistration.objects.get(email="test@example.com")
        data = {
            "email": "test@example.com",
            "otp_code": pending.otp_code
        }
        response = api_client.post("/api/auth/register/confirm", data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["user"]["email"] == "test@example.com"

    def test_confirm_otp_invalid_code(self, api_client, whitelist_factory):
        """Prueba confirmación con código inválido"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        data = {
            "email": "test@example.com",
            "otp_code": "000000"
        }
        response = api_client.post("/api/auth/register/confirm", data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_resend_otp_endpoint(self, api_client, whitelist_factory):
        """Prueba endpoint de reenvío de OTP"""
        whitelist_factory(email="test@example.com")
        request_registration_otp(email="test@example.com", password="testpass123")
        
        pending = PendingRegistration.objects.get(email="test@example.com")
        pending.otp_sent_at = timezone.now() - timedelta(seconds=61)
        pending.save()
        
        data = {"email": "test@example.com"}
        response = api_client.post("/api/auth/register/resend-otp", data)
        assert response.status_code == status.HTTP_200_OK or response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_registration_status_endpoint(self, api_client, whitelist_factory):
        """Prueba endpoint de estado de registro"""
        whitelist_factory(email="test@example.com")
        data = {"email": "test@example.com"}
        response = api_client.post("/api/auth/register/status/", data)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == "test@example.com"
        assert response.data["allowed"] is True
