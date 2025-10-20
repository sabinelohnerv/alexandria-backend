import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password

from apps.accounts_password import services
from apps.accounts_password.models import PasswordResetTicket

User = get_user_model()


@pytest.fixture
def user_active(db):
    return User.objects.create_user(username="u", email="ok@ex.com", password="OldPass123", first_name="Ada")


@pytest.fixture(autouse=True)
def _no_real_email(monkeypatch):
    # Evita enviar correos reales en tests (:contentReference[oaicite:9]{index=9})
    monkeypatch.setattr(services, "_send_reset_email", lambda **kwargs: None)


# ---------- request_password_reset ----------
@pytest.mark.django_db
def test_request_creates_ticket_and_sends_email(user_active):
    services.request_password_reset(email="ok@ex.com")  # crea ticket y envía OTP (:contentReference[oaicite:10]{index=10})
    t = PasswordResetTicket.objects.get(user=user_active)
    assert len(t.otp_code) == services.OTP_LENGTH
    assert t.expires_at > timezone.now()

@pytest.mark.django_db
def test_request_unknown_user_is_noop():
    services.request_password_reset(email="no@ex.com")  # no revela existencia (:contentReference[oaicite:11]{index=11})
    assert PasswordResetTicket.objects.count() == 0


# ---------- resend_password_reset ----------
@pytest.mark.django_db
def test_resend_enforces_cooldown_then_updates_code(user_active):
    services.request_password_reset(email="ok@ex.com")
    t = PasswordResetTicket.objects.latest("created_at")

    # cooldown activo
    with pytest.raises(ValueError):
        services.resend_password_reset(email="ok@ex.com")  # cooldown (:contentReference[oaicite:12]{index=12})

    # forzamos a pasar cooldown y reenvía con nuevo código
    t.otp_sent_at = timezone.now() - timedelta(seconds=services.RESEND_COOLDOWN_SECONDS + 1)
    old = t.otp_code
    t.save(update_fields=["otp_sent_at"])
    services.resend_password_reset(email="ok@ex.com")
    t.refresh_from_db()
    assert t.otp_code != old and t.resend_count >= 1


# ---------- confirm_password_reset ----------
@pytest.mark.django_db
def test_confirm_success_changes_password_and_marks_ticket_used(user_active):
    services.request_password_reset(email="ok@ex.com")
    t = PasswordResetTicket.objects.latest("created_at")
    services.confirm_password_reset(email="ok@ex.com", otp_code=t.otp_code, new_password="NewPass123")  # (:contentReference[oaicite:13]{index=13})

    user_active.refresh_from_db()
    assert check_password("NewPass123", user_active.password)
    t.refresh_from_db()
    assert t.is_used is True


