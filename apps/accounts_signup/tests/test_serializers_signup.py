import pytest
from apps.accounts_signup.serializers import (
    RequestOtpSerializer, ConfirmOtpSerializer, ResendOtpSerializer, StatusRequestSerializer
)

def test_request_otp_serializer_valid():
    s = RequestOtpSerializer(data={"email": "User@EX.com", "password": "12345678"})
    assert s.is_valid(), s.errors
    assert s.validated_data["email"] == "User@EX.com"  # DRF EmailField no fuerza lower, solo valida

def test_request_otp_serializer_password_min_length():
    s = RequestOtpSerializer(data={"email": "a@b.com", "password": "short"})
    assert not s.is_valid()
    assert "password" in s.errors

def test_confirm_otp_serializer_valid():
    s = ConfirmOtpSerializer(data={"email": "a@b.com", "otp_code": "123456"})
    assert s.is_valid(), s.errors

@pytest.mark.parametrize("payload", [
    {"email": "", "otp_code": "123456"},
    {"email": "a@b.com", "otp_code": ""},
])
def test_confirm_otp_serializer_invalid(payload):
    s = ConfirmOtpSerializer(data=payload)
    assert not s.is_valid()

def test_resend_otp_serializer_valid():
    s = ResendOtpSerializer(data={"email": "a@b.com"})
    assert s.is_valid()

def test_status_request_serializer_valid():
    s = StatusRequestSerializer(data={"email": "a@b.com"})
    assert s.is_valid()
