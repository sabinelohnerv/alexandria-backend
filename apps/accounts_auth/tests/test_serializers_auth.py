import pytest
from django.contrib.auth import get_user_model
from rest_framework import serializers
from apps.accounts_auth.serializers import EmailTokenObtainPairSerializer

User = get_user_model()


@pytest.mark.django_db
def test_validate_requires_email():
    ser = EmailTokenObtainPairSerializer(data={"password": "x"})
    with pytest.raises(serializers.ValidationError) as ex:
        ser.is_valid(raise_exception=True)
    assert "username" in ex.value.detail  # requiere email (:contentReference[oaicite:4]{index=4})


@pytest.mark.django_db
@pytest.mark.parametrize("is_staff,is_superuser,expected_role", [
    (False, False, "user"),
    (True, False, "admin"),
    (False, True, "admin"),
])
def test_get_token_includes_custom_claims(is_staff, is_superuser, expected_role):
    u = User.objects.create_user(
        username="x", email="x@ex.com", password="p",
        first_name="Ada", last_name="Lovelace",
        is_staff=is_staff, is_superuser=is_superuser
    )
    token = EmailTokenObtainPairSerializer.get_token(u)  
    assert token["role"] == expected_role
    assert token["email"] == "x@ex.com"
    assert token["name"] in ("Ada Lovelace", "x")  
