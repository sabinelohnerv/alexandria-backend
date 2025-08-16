from django.urls import path
from .views import RequestRegistrationOtpView, ConfirmRegistrationOtpView, ResendRegistrationOtpView, RegistrationStatusView

urlpatterns = [
    path("register/request-otp/", RequestRegistrationOtpView.as_view(), name="register-request-otp"),
    path("register/confirm/", ConfirmRegistrationOtpView.as_view(), name="register-confirm"),
    path("register/resend-otp/", ResendRegistrationOtpView.as_view(), name="register-resend-otp"),
    path("register/status/", RegistrationStatusView.as_view(), name="register-status"),
]
