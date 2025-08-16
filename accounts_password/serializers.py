from rest_framework import serializers

class RequestResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ResendResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

class ConfirmResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6)
    new_password = serializers.CharField(min_length=8, write_only=True)

class ResetStatusRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
