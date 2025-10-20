import pytest
from apps.accounts_password.serializers import (
    RequestResetSerializer, ResendResetSerializer,
    ConfirmResetSerializer, ResetStatusRequestSerializer,
)

@pytest.mark.parametrize("payload,ok", [
    ({"email": "a@b.com"}, True),
    ({"email": "bad"}, False),
])
def test_request_and_resend_serializers(payload, ok):
    assert RequestResetSerializer(data=payload).is_valid() is ok
    assert ResendResetSerializer(data=payload).is_valid() is ok  # EmailField (:contentReference[oaicite:7]{index=7})

@pytest.mark.parametrize("payload,ok", [
    ({"email":"a@b.com","otp_code":"123456","new_password":"12345678"}, True),
    ({"email":"a@b.com","otp_code":"1234567","new_password":"12345678"}, False),  # max_length=6
    ({"email":"a@b.com","otp_code":"123456","new_password":"short"}, False),      # min_length=8
])
def test_confirm_reset_serializer(payload, ok):
    s = ConfirmResetSerializer(data=payload)  # (:contentReference[oaicite:8]{index=8})
    assert s.is_valid() is ok, s.errors

def test_status_request_serializer():
    assert ResetStatusRequestSerializer(data={"email":"a@b.com"}).is_valid()
