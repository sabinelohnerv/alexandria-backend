from rest_framework import serializers
from .models import StaffWhitelist

class StaffWhitelistSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffWhitelist
        fields = ["id", "first_name", "last_name", "email", "role", "is_active", "created_by", "created_at", "updated_at"]
        read_only_fields = ["id", "is_active", "created_by", "created_at", "updated_at"]

    def validate_email(self, value):
        # Normaliza email en minúsculas
        return value.strip().lower()
    
    def validate_role(self, value):
        value = (value or "").strip().lower()
        valid = [c for c, _ in StaffWhitelist.Role.choices]
        if value == "":
            return StaffWhitelist.Role.USER  # default
        if value not in valid:
            raise serializers.ValidationError(f"Valor inválido para role. Usa uno de: {valid}")
        return value
