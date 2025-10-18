from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StaffWhitelistViewSet, check_whitelist

router = DefaultRouter()
router.register(r"whitelist", StaffWhitelistViewSet, basename="staff-whitelist")

urlpatterns = [
    path("", include(router.urls)),
    path("whitelist/check/", check_whitelist, name="check-whitelist"),

    path("", include(router.urls)),
    path("whitelist/check", check_whitelist, name="check-whitelist"),
]
