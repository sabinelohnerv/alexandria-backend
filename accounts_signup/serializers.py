from rest_framework import serializers

class RequestOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)

class ConfirmOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp_code = serializers.CharField(max_length=6)

class ResendOtpSerializer(serializers.Serializer):
    email = serializers.EmailField()

class StatusRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()