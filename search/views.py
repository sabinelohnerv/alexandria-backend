from rest_framework import viewsets, permissions, mixins, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action

from django.db.models import Count, Q, Subquery, OuterRef, CharField
from django.db.models.functions import Cast
from django.utils.text import slugify

from .models import ChatSession, ChatMessage, SearchHit, Feedback
from .serializers import (
    ChatSessionSerializer,
    ChatMessageSerializer,
    SearchHitWithDocSerializer,
    AskRequestSerializer,
    AskResponseSerializer,
    FeedbackSerializer,
)
from .services import ask as ask_service
from .throttles import BurstRateThrottle, SustainedRateThrottle
from common.services.minio_storage import presign_get_url

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
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.kwargs.get("session_pk")
        u = self.request.user
        see_all = self.request.query_params.get("all") == "1"


        my_vote_subq = (Feedback.objects
            .filter(user=u, message=OuterRef("pk"))
            .values("label")[:1])

        qs = (ChatMessage.objects
            .filter(session_id=session_id, session__deleted_at__isnull=True)
            .select_related("session")
            .annotate(
                useful_count=Count("feedbacks", filter=Q(feedbacks__label=Feedback.LABEL_USEFUL)),
                not_useful_count=Count("feedbacks", filter=Q(feedbacks__label=Feedback.LABEL_NOT_USEFUL)),
                my_feedback_label=Cast(Subquery(my_vote_subq), CharField()),
            )
            .order_by("created_at"))

        if not ((u.is_staff or u.is_superuser) and see_all):
            qs = qs.filter(session__user=u)

        return qs
    
    @action(detail=True, methods=["get"], url_path="hits")
    def hits(self, request, session_pk=None, pk=None):
        """
        Lista los hits del mensaje con metadatos del documento/chunk y feedback por hit:
          - useful_count / not_useful_count
          - my_feedback_label (voto del usuario actual)
        Parámetros:
          - include_snippet=1  -> añade 'snippet' (texto truncado del chunk)
          - limit=N            -> límite si NO usas paginación DRF
        """
        message = self.get_object()
        u = request.user

        my_vote_hit_subq = (Feedback.objects
            .filter(user=u, hit=OuterRef("pk"))
            .values("label")[:1])

        qs = (SearchHit.objects
              .filter(message=message)
              .select_related("document", "chunk")
              .annotate(
                  useful_count=Count("feedbacks", filter=Q(feedbacks__label=Feedback.LABEL_USEFUL)),
                  not_useful_count=Count("feedbacks", filter=Q(feedbacks__label=Feedback.LABEL_NOT_USEFUL)),
                  my_feedback_label=Cast(Subquery(my_vote_hit_subq), CharField()),
              )
              .order_by("rank"))

        limit = request.query_params.get("limit")
        if limit and str(limit).isdigit() and not self.paginator:
            qs = qs[:int(limit)]

        include_snippet = request.query_params.get("include_snippet") == "1"

        page = self.paginate_queryset(qs)
        data_qs = page if page is not None else qs

        ser = SearchHitWithDocSerializer(
            data_qs, many=True,
            context={"request": request, "include_snippet": include_snippet}
        )

        if page is not None:
            return self.get_paginated_response(ser.data)
        return Response(ser.data, status=200)

class AskView(APIView):

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
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request, *args, **kwargs):
        s = FeedbackSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        fb = s.save()
        return Response(FeedbackSerializer(fb).data, status=201)

    def delete(self, request, *args, **kwargs):
        msg_id = request.query_params.get("message_id")
        hit_id = request.query_params.get("hit_id")
        if not msg_id and not hit_id:
            return Response({"detail": "message_id o hit_id requerido"}, status=400)

        qs = Feedback.objects.filter(user=request.user)
        if msg_id:
            qs = qs.filter(message_id=msg_id)
        if hit_id:
            qs = qs.filter(hit_id=hit_id)

        deleted, _ = qs.delete()
        return Response({"deleted": deleted}, status=200)

class HitFileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def get(self, request, session_id: int, message_id: int, hit_id: int):
        try:
            hit = (SearchHit.objects
                   .select_related("message__session", "document")
                   .get(pk=hit_id, message_id=message_id))
        except SearchHit.DoesNotExist:
            return Response({"detail": "Hit not found"}, status=status.HTTP_404_NOT_FOUND)

        sess = hit.message.session
        if sess.deleted_at is not None:
            return Response({"detail": "Session was deleted"}, status=status.HTTP_410_GONE)

        u = request.user
        if not (u.is_staff or u.is_superuser):
            if sess.user_id != u.id or sess.id != int(session_id):
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        doc = hit.document
        title = doc.title or f"document-{doc.id}"
        fname = f"{slugify(title) or 'document'}-{doc.id}.pdf"

        url = presign_get_url(
            key=doc.storage_key,
            filename=fname,
            content_type="application/pdf",
            inline=True,
        )
        return Response(status=302, headers={"Location": url})