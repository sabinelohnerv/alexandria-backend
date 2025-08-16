from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .serializers import RequestOtpSerializer, ConfirmOtpSerializer, ResendOtpSerializer, StatusRequestSerializer
from .services import request_registration_otp, confirm_registration_with_otp, resend_registration_otp, get_registration_status
from .throttles import (
    OTPRequestIPThrottle, OTPRequestEmailThrottle,
    OTPResendIPThrottle, OTPResendEmailThrottle,
    StatusIPThrottle, StatusEmailThrottle
)

class RequestRegistrationOtpView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestIPThrottle, OTPRequestEmailThrottle]

    def post(self, request):
        serializer = RequestOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            request_registration_otp(
                first_name=data["first_name"],
                last_name=data["last_name"],
                email=data["email"],
                password=data["password"],
            )
        except PermissionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
        return Response({"detail": "OTP enviado al correo."}, status=status.HTTP_200_OK)

class ConfirmRegistrationOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ConfirmOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = confirm_registration_with_otp(
                email=data["email"],
                otp_code=data["otp_code"],
            )
        except PermissionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "detail": "Usuario verificado y creado.",
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_staff": user.is_staff,
            }
        }, status=status.HTTP_201_CREATED)

class ResendRegistrationOtpView(APIView):
    permission_classes = [AllowAny]
    # Throttling por IP y por email (tasas distintas a request-otp)
    throttle_classes = [OTPResendIPThrottle, OTPResendEmailThrottle]

    def post(self, request):
        serializer = ResendOtpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        try:
            resend_registration_otp(email=email)
        except PermissionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "OTP reenviado al correo."}, status=status.HTTP_200_OK)

class RegistrationStatusView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [StatusEmailThrottle, StatusIPThrottle]

    def post(self, request):
        serializer = StatusRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        data = get_registration_status(email=email)
        return Response(data, status=status.HTTP_200_OK)