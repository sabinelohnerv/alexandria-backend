from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import StaffWhitelist

User = get_user_model()

class StaffWhitelistSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffWhitelist
        fields = [
            "id", "first_name", "last_name", "email", "role",
            "is_active", "created_by", "created_at", "updated_at"
        ]
        read_only_fields = ["id", "is_active", "created_by", "created_at", "updated_at"]

    def validate_email(self, value):
        return value.strip().lower()

    def validate_role(self, value):
        value = (value or "").strip().lower()
        valid = [c for c, _ in StaffWhitelist.Role.choices]
        if value == "":
            return StaffWhitelist.Role.USER  
        if value not in valid:
            raise serializers.ValidationError(f"Valor inválido para role. Usa uno de: {valid}")
        return value

    def validate(self, attrs):
        instance = getattr(self, "instance", None) 
        new_email = attrs.get("email")

        if instance and new_email:
            current_email_norm = (instance.email or "").strip().lower()
            if new_email != current_email_norm:
                if User.objects.filter(email__iexact=current_email_norm, is_active=True).exists():
                    raise serializers.ValidationError({
                        "email": "No se puede cambiar el email porque hay un usuario activo asociado a la entrada."
                    })

        return attrs
