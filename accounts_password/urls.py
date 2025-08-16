from django.urls import path
from .views import (
    PasswordRequestResetView, PasswordResendResetView,
    PasswordConfirmResetView, PasswordResetStatusView
)

urlpatterns = [
    path("password/request-reset/", PasswordRequestResetView.as_view(), name="password-request-reset"),
    path("password/resend-reset/", PasswordResendResetView.as_view(), name="password-resend-reset"),
    path("password/confirm/", PasswordConfirmResetView.as_view(), name="password-confirm"),
    path("password/status/", PasswordResetStatusView.as_view(), name="password-status"),

    path("password/request-reset", PasswordRequestResetView.as_view()),
    path("password/resend-reset", PasswordResendResetView.as_view()),
    path("password/confirm", PasswordConfirmResetView.as_view()),
    path("password/status", PasswordResetStatusView.as_view()),
]
