from rest_framework import viewsets, permissions, mixins, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action

from django.db.models import Count, Q, Subquery, OuterRef, CharField
from django.db.models.functions import Cast
from django.utils.text import slugify
from django.db import DatabaseError, OperationalError
import logging

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
from .services.guards import check_query_guards, QueryGuardException
from .throttles import BurstRateThrottle, SustainedRateThrottle
from common.services.minio_storage import presign_get_url
from apps.ranking_adaptive.models import RankingDecision

logger = logging.getLogger(__name__)

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
        instance.soft_delete()

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        session = self.get_object()
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
    
    @action(detail=True, methods=["get"], url_path="explainability")
    def explainability(self, request, session_pk=None, pk=None):
        """
        Obtiene la explicabilidad completa de un mensaje, incluyendo:
        - Tiempos de cada fase (timings)
        - Decisiones de ranking (rank_before vs rank_after)
        - Señales utilizadas para cada hit
        - Configuración de pesos activos
        """
        message = self.get_object()
        u = request.user
        
        # Verificar permisos
        if not (u.is_staff or u.is_superuser):
            if message.session.user_id != u.id:
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        
        # Obtener datos básicos del mensaje
        answer_json = message.answer_json or {}
        timings = answer_json.get("timings", {})
        
        # Obtener hits con sus metadatos
        hits = (SearchHit.objects
                .filter(message=message)
                .select_related("document", "chunk")
                .order_by("rank"))
        
        hits_data = []
        for hit in hits:
            meta = hit.meta_json or {}
            hits_data.append({
                "rank": hit.rank,
                "document_id": hit.document_id,
                "document_title": hit.document.title,
                "chunk_id": hit.chunk_id,
                "section": meta.get("section"),
                "scores": {
                    "vector": float(hit.score_vector or 0),
                    "lexical": float(meta.get("lex", 0)),
                    "base_rrf": float(meta.get("base_rrf", 0)),
                    "rerank_ce": meta.get("rerank_ce"),
                    "rerank_ce_raw": meta.get("rerank_ce_raw"),
                    "final_score": float(meta.get("final_score", 0)),
                },
                "signals": meta.get("signals", {}),
            })
        
        # Obtener decisiones de ranking si existen
        try:
            decisions = (RankingDecision.objects
                        .filter(message_id=message.id)
                        .order_by("shown_pos"))
            
            decisions_data = []
            for dec in decisions:
                decisions_data.append({
                    "hit_id": dec.hit_id,
                    "rank_before": dec.rank_before,
                    "rank_after": dec.rank_after,
                    "shown_pos": dec.shown_pos,
                    "score_ce": float(dec.score_ce or 0),
                    "signals": dec.signals,
                    "signal_names": dec.signal_names,
                    "model_version": dec.model_version,
                })
        except Exception:
            decisions_data = []
        
        # Construir respuesta completa
        response_data = {
            "message_id": message.id,
            "query": message.session.messages.filter(role=ChatMessage.ROLE_USER).last().text if message.session.messages.filter(role=ChatMessage.ROLE_USER).exists() else "",
            "created_at": message.created_at,
            "latency_ms": message.latency_ms,
            
            # Fases y tiempos
            "phases": {
                "setup": {
                    "duration_ms": timings.get("setup_ms", 0),
                    "description": "Creación de sesión y mensaje de usuario"
                },
                "embedding": {
                    "duration_ms": timings.get("embedding_ms", 0),
                    "description": "Generación del embedding de la consulta"
                },
                "search": {
                    "duration_ms": timings.get("search_ms", 0),
                    "description": "Búsqueda vectorial y léxica en paralelo"
                },
                "rrf_fusion": {
                    "duration_ms": timings.get("rrf_fusion_ms", 0),
                    "description": "Fusión RRF de resultados vectoriales y léxicos"
                },
                "retrieve_total": {
                    "duration_ms": timings.get("retrieve_total_ms", 0),
                    "description": "Tiempo total de recuperación"
                },
                "rerank": {
                    "duration_ms": timings.get("rerank_ms", 0),
                    "description": "Reranking con cross-encoder"
                },
                "signals_scoring": {
                    "duration_ms": timings.get("signals_scoring_ms", 0),
                    "description": "Cálculo de señales y scoring final"
                },
                "mmr": {
                    "duration_ms": timings.get("mmr_ms", 0),
                    "description": "Selección MMR para diversidad"
                },
                "llm_synthesis": {
                    "duration_ms": timings.get("llm_synthesis_ms", 0),
                    "description": "Generación de respuesta con LLM"
                },
                "persistence": {
                    "duration_ms": timings.get("persistence_ms", 0),
                    "description": "Persistencia en base de datos"
                },
                "total": {
                    "duration_ms": timings.get("total_ms", message.latency_ms),
                    "description": "Tiempo total de procesamiento"
                }
            },
            
            # Configuración utilizada
            "configuration": {
                "enable_rerank": answer_json.get("enable_rerank", True),
                "weights": answer_json.get("weights", {}),
                "org_weights": answer_json.get("org_weights", {}),
                "weights_version_used": answer_json.get("weights_version_used", "active"),
                "experiment_bucket": answer_json.get("experiment_bucket", "control"),
                "rerank_score_mode": answer_json.get("rerank_score_mode", "sigmoid_minmax"),
            },
            
            # Resultados
            "hits": hits_data,
            "ranking_decisions": decisions_data,
            "total_hits": len(hits_data),
        }
        
        return Response(response_data, status=200)

class AskView(APIView):

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [BurstRateThrottle, SustainedRateThrottle]

    def post(self, request, *args, **kwargs):
        s = AskRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        # Validar que la consulta sea jurídica y no demasiado vaga
        try:
            check_query_guards(data["query"])
        except QueryGuardException as e:
            return Response(
                {"detail": e.message, "code": e.code},
                status=status.HTTP_400_BAD_REQUEST
            )

        session = None
        if "session_id" in data and data["session_id"]:
            try:
                session = ChatSession.objects.get(pk=data["session_id"])
            except ChatSession.DoesNotExist:
                return Response({"detail": "Session not found"}, status=status.HTTP_404_NOT_FOUND)
            except (DatabaseError, OperationalError) as e:
                logger.error(f"Database error retrieving session: {e}", exc_info=True)
                return Response(
                    {"detail": "Error de base de datos. Por favor, intenta nuevamente.", "code": "database_error"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            if not (request.user.is_staff or request.user.is_superuser):
                if session.user_id != request.user.id:
                    return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

            if session.deleted_at is not None:
                return Response({"detail": "Session was deleted"}, status=status.HTTP_410_GONE)

        # Intentar generar respuesta con manejo de errores completo
        try:
            msg, hits = ask_service(request.user, data["query"], session=session)
            out = AskResponseSerializer({"message": msg, "hits": hits})
            return Response(out.data, status=200)
        
        except (DatabaseError, OperationalError) as e:
            logger.error(f"Database error during ask_service: {e}", exc_info=True)
            return Response(
                {
                    "detail": "Error de base de datos al procesar tu consulta. Por favor, intenta nuevamente.",
                    "code": "database_error"
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        except ConnectionError as e:
            logger.error(f"Connection error during ask_service: {e}", exc_info=True)
            return Response(
                {
                    "detail": "Error de conexión con los servicios externos. Por favor, intenta nuevamente.",
                    "code": "connection_error"
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        except TimeoutError as e:
            logger.error(f"Timeout error during ask_service: {e}", exc_info=True)
            return Response(
                {
                    "detail": "La solicitud tardó demasiado tiempo. Por favor, intenta con una consulta más específica.",
                    "code": "timeout_error"
                },
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        
        except Exception as e:
            logger.error(f"Unexpected error during ask_service: {e}", exc_info=True)
            return Response(
                {
                    "detail": "Ocurrió un error inesperado al procesar tu consulta. Por favor, intenta nuevamente.",
                    "code": "internal_error"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

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