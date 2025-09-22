from rest_framework import viewsets, permissions, mixins, status
from rest_framework.response import Response
from rest_framework.views import APIView

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
                         viewsets.GenericViewSet):
    """
    Crear sesión:
      - No confíes en 'user' desde el payload: lo seteamos siempre a request.user.
      - Lista/Detalle: solo del dueño, salvo staff/superuser.
    """
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = (ChatSession.objects
            .only("id", "title", "user_id", "created_at", "updated_at")
            .order_by("-updated_at"))
        u = self.request.user
        if not (u.is_staff or u.is_superuser):
            qs = qs.filter(user=u)
        return qs

    def perform_create(self, serializer):
        """
        Inyecta el usuario autenticado como dueño de la sesión.
        Evita que el cliente imponga otro user_id.
        """
        serializer.save(user=self.request.user)


class ChatMessageViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Lista mensajes de una sesión específica.
    Garantiza propiedad de la sesión para usuarios no admin.
    """
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.kwargs.get("session_pk")
        qs = (ChatMessage.objects
            .filter(session_id=session_id)
            .select_related("session")
            .only("id", "session_id", "role", "text", "answer_json", "latency_ms", "created_at")
            .order_by("created_at"))
        u = self.request.user
        if not (u.is_staff or u.is_superuser):
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
            # Validar pertenencia
            try:
                session = ChatSession.objects.get(pk=data["session_id"])
            except ChatSession.DoesNotExist:
                return Response({"detail": "Session not found"}, status=status.HTTP_404_NOT_FOUND)

            if not (request.user.is_staff or request.user.is_superuser):
                if session.user_id != request.user.id:
                    return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

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
