from rest_framework import viewsets, permissions, mixins, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action

from .models import ChatSession, ChatMessage, SearchHit, Feedback
from .serializers import (
    ChatSessionSerializer,
    ChatMessageSerializer,
    SearchHitSerializer,
    AskRequestSerializer,
    AskResponseSerializer,
    FeedbackSerializer,
)
from .services import ask as ask_service
from .throttles import BurstRateThrottle, SustainedRateThrottle


class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        u = request.user
        if not u.is_authenticated:
            return False
        if getattr(u, "is_staff", False) or getattr(u, "is_superuser", False):
            return True
        owner = getattr(obj, "user", None)
        return owner == u


class ChatSessionViewSet(mixins.ListModelMixin,
                         mixins.RetrieveModelMixin,
                         mixins.CreateModelMixin,
                         mixins.UpdateModelMixin,          
                         mixins.DestroyModelMixin,        
                         viewsets.GenericViewSet):
    """
    CRUD de sesiones del usuario:
      - Create: asigna request.user como dueño.
      - List/Retrieve: sólo del dueño (salvo admin/superuser).
      - Update (PATCH): renombrar sesión (title).
      - Destroy (DELETE): soft delete (marca deleted_at).
      - restore (POST /sessions/{id}/restore/): revierte soft delete.
    """
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = ChatSession.objects.all().order_by("-updated_at", "-id")
        u = self.request.user

        include_deleted = self.request.query_params.get("include_deleted") == "1"
        if not include_deleted:
            qs = qs.filter(deleted_at__isnull=True)

        see_all = self.request.query_params.get("all") == "1"
        if not ((u.is_staff or u.is_superuser) and see_all):
            qs = qs.filter(user=u)

        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance: ChatSession):
        # Soft delete
        instance.soft_delete()

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        "Restaura una sesión soft-deleted (si pertenece al usuario)."
        session = self.get_object()  # respeta permisos/propiedad
        if not session.deleted_at:
            return Response({"detail": "Session is not deleted"}, status=status.HTTP_400_BAD_REQUEST)
        session.restore()
        return Response(self.get_serializer(session).data, status=status.HTTP_200_OK)


class ChatMessageViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Lista mensajes de una sesión específica.
    Garantiza propiedad de la sesión para usuarios no admin.
    """
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

def get_queryset(self):
    session_id = self.kwargs.get("session_pk")
    u = self.request.user
    see_all = self.request.query_params.get("all") == "1"

    qs = (ChatMessage.objects
          .filter(session_id=session_id, session__deleted_at__isnull=True)
          .select_related("session")
          .order_by("created_at"))

    if not ((u.is_staff or u.is_superuser) and see_all):
        qs = qs.filter(session__user=u)

    return qs



class AskView(APIView):
    """
    Orquesta una pregunta:
      - Valida 'session_id' si viene y confirma propiedad.
      - Si no hay 'session_id', ask_service crea una nueva sesión con user=request.user.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request, *args, **kwargs):
        s = AskRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        session = None
        if "session_id" in data and data["session_id"]:
            try:
                session = ChatSession.objects.get(pk=data["session_id"])
            except ChatSession.DoesNotExist:
                return Response({"detail": "Session not found"}, status=status.HTTP_404_NOT_FOUND)

            # Propiedad
            if not (request.user.is_staff or request.user.is_superuser):
                if session.user_id != request.user.id:
                    return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

            # No permitir preguntar en una sesión borrada
            if session.deleted_at is not None:
                return Response({"detail": "Session was deleted"}, status=status.HTTP_410_GONE)

        # ask_service crea la sesión si 'session' es None y asigna user=request.user
        msg, hits = ask_service(request.user, data["query"], session=session)
        out = AskResponseSerializer({"message": msg, "hits": hits})
        return Response(out.data, status=200)


class FeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        s = FeedbackSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        fb = s.save(user=request.user)
        return Response(FeedbackSerializer(fb).data, status=201)
