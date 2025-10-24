"""
Tests para el módulo accounts_password
"""
import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework import status
from apps.accounts_password.models import PasswordResetTicket
from apps.accounts_password.services import (
    request_password_reset,
    resend_password_reset,
    confirm_password_reset
)

User = get_user_model()


@pytest.mark.django_db
class TestPasswordResetTicketModel:
    """Tests para el modelo PasswordResetTicket"""

    def test_create_password_reset_ticket(self, regular_user):
        """Prueba creación de ticket de reset de contraseña"""
        expires = timezone.now() + timedelta(minutes=15)
        ticket = PasswordResetTicket.objects.create(
            user=regular_user,
            email=regular_user.email,
            otp_code="123456",
            expires_at=expires
        )
        assert ticket.user == regular_user
        assert ticket.email == regular_user.email
        assert ticket.otp_code == "123456"
        assert ticket.attempts == 0
        assert ticket.is_used is False

    def test_password_reset_ticket_str(self, regular_user):
        """Prueba representación en string"""
        expires = timezone.now() + timedelta(minutes=15)
        ticket = PasswordResetTicket.objects.create(
            user=regular_user,
            email=regular_user.email,
            otp_code="123456",
            expires_at=expires
        )
        assert regular_user.email in str(ticket)
        assert "used=False" in str(ticket)


@pytest.mark.django_db
class TestPasswordResetService:
    """Tests para el servicio de reset de contraseña"""

    def test_request_password_reset_success(self, regular_user):
        """Prueba solicitud exitosa de reset de contraseña"""
        request_password_reset(email=regular_user.email)
        
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        assert len(ticket.otp_code) == 6
        assert ticket.is_used is False
        assert ticket.attempts == 0
        assert len(mail.outbox) == 1
        assert regular_user.email in mail.outbox[0].to

    def test_request_password_reset_normalizes_email(self, regular_user):
        """Prueba que el email se normaliza a minúsculas"""
        request_password_reset(email=regular_user.email.upper())
        
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        assert ticket.email == regular_user.email.lower()

    def test_request_password_reset_nonexistent_user(self):
        """Prueba que no falla con usuario inexistente (no revela existencia)"""
        request_password_reset(email="nonexistent@example.com")
        assert len(mail.outbox) == 0

    def test_request_password_reset_inactive_user(self, user_factory):
        """Prueba que no envía email a usuario inactivo"""
        inactive_user = user_factory(email="inactive@example.com", is_active=False)
        request_password_reset(email=inactive_user.email)
        assert len(mail.outbox) == 0

    def test_request_password_reset_cooldown(self, regular_user):
        """Prueba que respeta el cooldown entre solicitudes"""
        request_password_reset(email=regular_user.email)
        
        with pytest.raises(ValueError) as exc_info:
            request_password_reset(email=regular_user.email)
        assert "esperar" in str(exc_info.value)

    def test_request_password_reset_updates_existing_ticket(self, regular_user):
        """Prueba que actualiza ticket existente después del cooldown"""
        request_password_reset(email=regular_user.email)
        first_otp = PasswordResetTicket.objects.get(user=regular_user).otp_code
        
        # Simular que pasó el cooldown
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        ticket.otp_sent_at = timezone.now() - timedelta(seconds=61)
        ticket.save()
        
        request_password_reset(email=regular_user.email)
        second_otp = PasswordResetTicket.objects.get(user=regular_user).otp_code
        
        assert PasswordResetTicket.objects.filter(user=regular_user, is_used=False).count() == 1
        assert first_otp != second_otp

    def test_resend_password_reset_success(self, regular_user):
        """Prueba reenvío exitoso de OTP"""
        request_password_reset(email=regular_user.email)
        first_otp = PasswordResetTicket.objects.get(user=regular_user).otp_code
        
        # Simular que pasó el cooldown
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        ticket.otp_sent_at = timezone.now() - timedelta(seconds=61)
        ticket.save()
        
        resend_password_reset(email=regular_user.email)
        
        ticket.refresh_from_db()
        assert ticket.otp_code != first_otp
        assert ticket.resend_count == 1
        assert len(mail.outbox) == 2

    def test_resend_password_reset_cooldown(self, regular_user):
        """Prueba que respeta el cooldown de reenvío"""
        request_password_reset(email=regular_user.email)
        
        with pytest.raises(ValueError) as exc_info:
            resend_password_reset(email=regular_user.email)
        assert "esperar" in str(exc_info.value)

    def test_resend_password_reset_no_ticket(self, regular_user):
        """Prueba que crea nuevo ticket si no existe"""
        resend_password_reset(email=regular_user.email)
        
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        assert ticket is not None
        assert len(mail.outbox) == 1

    def test_confirm_password_reset_success(self, regular_user):
        """Prueba confirmación exitosa de reset de contraseña"""
        old_password = regular_user.password
        request_password_reset(email=regular_user.email)
        
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        confirm_password_reset(
            email=regular_user.email,
            otp_code=ticket.otp_code,
            new_password="newpassword123"
        )
        
        regular_user.refresh_from_db()
        assert regular_user.password != old_password
        assert regular_user.check_password("newpassword123")
        
        ticket.refresh_from_db()
        assert ticket.is_used is True

    def test_confirm_password_reset_invalid_code(self, regular_user):
        """Prueba que falla con código OTP inválido"""
        request_password_reset(email=regular_user.email)
        
        with pytest.raises(ValueError) as exc_info:
            confirm_password_reset(
                email=regular_user.email,
                otp_code="000000",
                new_password="newpassword123"
            )
        assert "inválido" in str(exc_info.value)

    def test_confirm_password_reset_expired(self, regular_user):
        """Prueba que falla con código expirado"""
        request_password_reset(email=regular_user.email)
        
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        ticket.expires_at = timezone.now() - timedelta(minutes=1)
        ticket.save()
        
        with pytest.raises(ValueError) as exc_info:
            confirm_password_reset(
                email=regular_user.email,
                otp_code=ticket.otp_code,
                new_password="newpassword123"
            )
        assert "expirado" in str(exc_info.value)

    def test_confirm_password_reset_max_attempts(self, regular_user):
        """Prueba que falla después de máximo de intentos"""
        request_password_reset(email=regular_user.email)
        
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        ticket.attempts = 5
        ticket.save()
        
        with pytest.raises(ValueError) as exc_info:
            confirm_password_reset(
                email=regular_user.email,
                otp_code=ticket.otp_code,
                new_password="newpassword123"
            )
        assert "máximo de intentos" in str(exc_info.value)

    def test_confirm_password_reset_nonexistent_user(self):
        """Prueba que falla con usuario inexistente"""
        with pytest.raises(ValueError) as exc_info:
            confirm_password_reset(
                email="nonexistent@example.com",
                otp_code="123456",
                new_password="newpassword123"
            )
        assert "inválido" in str(exc_info.value)

    def test_confirm_password_reset_no_ticket(self, regular_user):
        """Prueba que falla si no hay ticket"""
        with pytest.raises(ValueError) as exc_info:
            confirm_password_reset(
                email=regular_user.email,
                otp_code="123456",
                new_password="newpassword123"
            )
        assert "inválido" in str(exc_info.value)


@pytest.mark.django_db
class TestPasswordResetAPI:
    """Tests para los endpoints de la API de reset de contraseña"""

    def test_request_reset_endpoint(self, api_client, regular_user):
        """Prueba endpoint de solicitud de reset"""
        data = {"email": regular_user.email}
        response = api_client.post("/api/auth/password/request-reset/", data)
        assert response.status_code == status.HTTP_200_OK or response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_request_reset_nonexistent_user(self, api_client):
        """Prueba que no revela si el usuario existe"""
        data = {"email": "nonexistent@example.com"}
        response = api_client.post("/api/auth/password/request-reset/", data)
        assert response.status_code == status.HTTP_200_OK or response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_resend_reset_endpoint(self, api_client, regular_user):
        """Prueba endpoint de reenvío de OTP"""
        request_password_reset(email=regular_user.email)
        
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        ticket.otp_sent_at = timezone.now() - timedelta(seconds=61)
        ticket.save()
        
        data = {"email": regular_user.email}
        response = api_client.post("/api/auth/password/resend-reset/", data)
        assert response.status_code == status.HTTP_200_OK or response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_confirm_reset_endpoint(self, api_client, regular_user):
        """Prueba endpoint de confirmación de reset"""
        request_password_reset(email=regular_user.email)
        
        ticket = PasswordResetTicket.objects.get(user=regular_user)
        data = {
            "email": regular_user.email,
            "otp_code": ticket.otp_code,
            "new_password": "newpassword123"
        }
        response = api_client.post("/api/auth/password/confirm/", data)
        assert response.status_code == status.HTTP_200_OK

    def test_confirm_reset_invalid_code(self, api_client, regular_user):
        """Prueba confirmación con código inválido"""
        request_password_reset(email=regular_user.email)
        
        data = {
            "email": regular_user.email,
            "otp_code": "000000",
            "new_password": "newpassword123"
        }
        response = api_client.post("/api/auth/password/confirm/", data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
