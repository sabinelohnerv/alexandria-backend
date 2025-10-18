from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from .serializers import (
    RequestResetSerializer, ResendResetSerializer, ConfirmResetSerializer, ResetStatusRequestSerializer
)
from .services import (
    request_password_reset, resend_password_reset, confirm_password_reset,
    OTP_TTL_MINUTES, RESEND_COOLDOWN_SECONDS, MAX_OTP_ATTEMPTS
)
from .throttles import (
    PwdResetIPThrottle, PwdResetEmailThrottle,
    PwdResendIPThrottle, PwdResendEmailThrottle,
    PwdStatusIPThrottle, PwdStatusEmailThrottle
)
from .models import PasswordResetTicket
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class PasswordRequestResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PwdResetIPThrottle, PwdResetEmailThrottle]

    def post(self, request):
        s = RequestResetSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            request_password_reset(email=s.validated_data["email"])
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Si el email existe, hemos enviado un código de verificación."}, status=200)

class PasswordResendResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PwdResendIPThrottle, PwdResendEmailThrottle]

    def post(self, request):
        s = ResendResetSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            resend_password_reset(email=s.validated_data["email"])
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Si el email existe, hemos reenviado el código."}, status=200)

class PasswordConfirmResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = ConfirmResetSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            confirm_password_reset(
                email=s.validated_data["email"],
                otp_code=s.validated_data["otp_code"],
                new_password=s.validated_data["new_password"],
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Tu contraseña ha sido actualizada correctamente."}, status=200)

class PasswordResetStatusView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PwdStatusIPThrottle, PwdStatusEmailThrottle]

    def get(self, request):
        email = (request.query_params.get("email") or "").strip().lower()
        s = ResetStatusRequestSerializer(data={"email": email})
        s.is_valid(raise_exception=True)
        return Response(self._status_for_email(email=s.validated_data["email"]))

    def post(self, request):
        s = ResetStatusRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(self._status_for_email(email=s.validated_data["email"]))

    def _status_for_email(self, *, email: str):
        data = {
            "email": email,
            "has_ticket": False,
            "status": "none",  # none | pending | expired | used
            "expires_in_seconds": 0,
            "attempts_left": MAX_OTP_ATTEMPTS,
            "resend_available": False,
            "resend_in_seconds": 0,
            "resend_count": 0,
            "cooldown_seconds": RESEND_COOLDOWN_SECONDS,
            "ttl_minutes": OTP_TTL_MINUTES,
        }
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if not user:
            return data
        ticket = PasswordResetTicket.objects.filter(user=user, is_used=False).order_by("-created_at").first()
        if not ticket:
            return data

        data["has_ticket"] = True
        now = timezone.now()
        expired = now > ticket.expires_at
        data["status"] = "expired" if expired else "pending"
        if not expired:
            data["expires_in_seconds"] = max(0, int((ticket.expires_at - now).total_seconds()))
            data["attempts_left"] = max(0, MAX_OTP_ATTEMPTS - ticket.attempts)
        delta = int((now - ticket.otp_sent_at).total_seconds())
        remain = max(0, RESEND_COOLDOWN_SECONDS - delta)
        data["resend_in_seconds"] = remain
        data["resend_available"] = remain == 0 and not expired
        data["resend_count"] = ticket.resend_count
        return data
