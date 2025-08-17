from rest_framework import viewsets, status, mixins, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend

from .models import StaffWhitelist
from .serializers import StaffWhitelistSerializer
from .services import StaffWhitelistService
from .filters import StaffWhitelistFilter


@api_view(["POST"])
@permission_classes([AllowAny])
def check_whitelist(request):
    email = request.data.get("email", "").strip().lower()
    exists = StaffWhitelist.objects.filter(email=email, is_active=True).exists()
    return Response({"allowed": exists})


class StaffWhitelistViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
):
    """
    CRUD de entries de whitelist. Solo admins.
    DELETE lógico con la acción custom 'deactivate'.
    """
    queryset = StaffWhitelist.objects.all()
    serializer_class = StaffWhitelistSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = StaffWhitelistFilter
    search_fields = ["first_name", "last_name", "email"]
    ordering_fields = ["first_name", "last_name", "email", "created_at", "role"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()

        # ---- Compat: show_inactive=1|true para incluir inactivos además de activos ----
        show_inactive = self.request.query_params.get("show_inactive")
        # ---- Nuevo: status=active|inactive|all (más explícito) ----
        status_param = (self.request.query_params.get("status") or "").lower()
        has_is_active_param = "is_active" in self.request.query_params  # django-filter lo manejará

        if has_is_active_param:
            pass  
        elif status_param in ("active", "inactive", "all"):
            if status_param == "active":
                qs = qs.filter(is_active=True)
            elif status_param == "inactive":
                qs = qs.filter(is_active=False)
            else: 
                pass  
        elif show_inactive in ("1", "true", "True"):
            pass  
        else:
            qs = qs.filter(is_active=True) 

        return qs
    
    def get_object(self):
        if getattr(self, "action", None) == "reactivate":
            return StaffWhitelist.objects.get(pk=self.kwargs["pk"])
        return super().get_object()

    def perform_create(self, serializer):
        data = serializer.validated_data
        entry = StaffWhitelistService.create_entry(
            first_name=data["first_name"],
            last_name=data["last_name"],
            email=data["email"],
            role=data.get("role"),
            created_by=self.request.user,
        )
        serializer.instance = entry

    def perform_update(self, serializer):
        entry = self.get_object()
        data = serializer.validated_data
        updated = StaffWhitelistService.update_entry(
            entry=entry,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            role=data.get("role"),
            email=data.get("email"),
        )
        serializer.instance = updated

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        entry = self.get_object()
        StaffWhitelistService.deactivate_entry(entry=entry)
        return Response({"status": "deactivated"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        entry = self.get_object()
        StaffWhitelistService.reactivate_entry(entry=entry)
        return Response({"status": "reactivated"}, status=status.HTTP_200_OK)
