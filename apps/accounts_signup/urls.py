from django.urls import path
from .views import RequestRegistrationOtpView, ConfirmRegistrationOtpView, ResendRegistrationOtpView, RegistrationStatusView

urlpatterns = [
   path("register/request-otp/", RequestRegistrationOtpView.as_view()),
    path("register/resend-otp/", ResendRegistrationOtpView.as_view()),
    path("register/confirm/", ConfirmRegistrationOtpView.as_view()),
    path("register/status/", RegistrationStatusView.as_view()),

    path("register/request-otp", RequestRegistrationOtpView.as_view()),
    path("register/resend-otp", ResendRegistrationOtpView.as_view()),
    path("register/confirm", ConfirmRegistrationOtpView.as_view()),
    path("register/status", RegistrationStatusView.as_view()),
]
