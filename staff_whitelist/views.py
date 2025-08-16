from rest_framework import viewsets, status, mixins
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework import filters

from .models import StaffWhitelist
from .serializers import StaffWhitelistSerializer
from .services import StaffWhitelistService

@api_view(["POST"])
@permission_classes([AllowAny])
def check_whitelist(request):
    email = request.data.get("email", "").strip().lower()
    exists = StaffWhitelist.objects.filter(email=email, is_active=True).exists()
    return Response({"allowed": exists})


class StaffWhitelistViewSet(viewsets.GenericViewSet,
                            mixins.ListModelMixin,
                            mixins.RetrieveModelMixin,
                            mixins.CreateModelMixin,
                            mixins.UpdateModelMixin):
    """
    CRUD de entries de whitelist. Solo admins.
    DELETE lógico con la acción custom 'deactivate'.
    """
    queryset = StaffWhitelist.objects.all()
    serializer_class = StaffWhitelistSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["first_name", "last_name", "email"]
    ordering_fields = ["first_name", "last_name", "email", "created_at", "role"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        show_inactive = self.request.query_params.get("show_inactive")
        if show_inactive not in ("1", "true", "True"):
            qs = qs.filter(is_active=True)
        role = self.request.query_params.get("role")
        if role in [c for c, _ in StaffWhitelist.Role.choices]:
            qs = qs.filter(role=role)
        return qs

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
