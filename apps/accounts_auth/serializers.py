from typing import Any, Dict
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()

def get_role(user: User) -> str:
    return "admin" if (user.is_staff or user.is_superuser) else "user"

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Permite login con 'email' (o con 'username' como fallback).
    Añade claims personalizadas: role, email, name.
    """
    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        email = (attrs.get("email") or attrs.get("username") or "").strip().lower()
        if not email:
            raise serializers.ValidationError({"email": "Este campo es requerido."})
        attrs["username"] = email

        return super().validate(attrs)

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = get_role(user)
        token["email"] = user.email
        token["name"] = f"{user.first_name} {user.last_name}".strip() or user.username
        return token
