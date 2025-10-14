from rest_framework import serializers
from .models import ChatSession, ChatMessage, SearchHit, Feedback
from documents.models import Document, Chunk

class ChatSessionSerializer(serializers.ModelSerializer):
    is_deleted = serializers.BooleanField(read_only=True)

    class Meta:
        model = ChatSession
        fields = ["id", "title", "created_at", "updated_at", "is_deleted"]


class ChatMessageSerializer(serializers.ModelSerializer):
    session_title = serializers.CharField(source="session.title", read_only=True)
    useful_count = serializers.IntegerField(read_only=True)
    not_useful_count = serializers.IntegerField(read_only=True)
    my_feedback_label = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = ChatMessage
        fields = [
            "id", "session", "session_title", "role", "text", "answer_json",
            "latency_ms", "created_at",
            # --- feedback agregado ---
            "useful_count", "not_useful_count", "my_feedback_label",
        ]

class SearchHitSerializer(serializers.ModelSerializer):
    document_id = serializers.IntegerField(source="document.id", read_only=True)
    chunk_id = serializers.IntegerField(source="chunk.id", read_only=True)

    class Meta:
        model = SearchHit
        fields = [
            "id",
            "message",
            "document_id",
            "chunk_id",
            "rank",
            "score_vector",
            "score_lexical",
            "score_rerank",
            "meta_json",
            "created_at",
        ]


# ----- payloads para /ask y /feedback -----

class AskRequestSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=False)
    query = serializers.CharField(max_length=2000)


class AskResponseSerializer(serializers.Serializer):
    message = ChatMessageSerializer()
    hits = SearchHitSerializer(many=True)


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = ["id", "message", "hit", "label", "comment", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        request = self.context["request"]
        u = request.user
        is_admin = getattr(u, "is_staff", False) or getattr(u, "is_superuser", False)
        msg = attrs.get("message")
        hit = attrs.get("hit")

        if msg and hit and hit.message_id != msg.id:
            raise serializers.ValidationError("El hit no corresponde al mensaje indicado.")

        if hit and not msg:
            msg = hit.message
            attrs["message"] = msg

        if msg and msg.role != ChatMessage.ROLE_ASSISTANT:
            raise serializers.ValidationError("Solo se permite feedback sobre mensajes del asistente.")

        if msg and msg.session.deleted_at is not None:
            raise serializers.ValidationError("No se puede registrar feedback sobre una sesión eliminada.")

        if not is_admin:
            owner_id = msg.session.user_id if msg else (hit.message.session.user_id if hit else None)
            if owner_id != u.id:
                raise serializers.ValidationError("No puedes dar feedback sobre contenido de otro usuario.")

        # 6) Sanitizar comentario y límite de longitud
        comment = (attrs.get("comment") or "").strip()
        if len(comment) > 2000:
            raise serializers.ValidationError("El comentario excede 2000 caracteres.")
        attrs["comment"] = comment

        return attrs

    def create(self, validated):
        """
        Idempotencia por (user,message) o (user,hit):
        si existe, se actualiza; si no, se crea.
        """
        u = self.context["request"].user
        validated["user"] = u
        msg = validated.get("message")
        hit = validated.get("hit")

        qs = Feedback.objects.filter(user=u)
        if msg:
            qs = qs.filter(message=msg, hit__isnull=True) if not hit else qs.filter(message=msg, hit=hit)
        elif hit:
            qs = qs.filter(hit=hit, message__isnull=True)

        existing = qs.first()
        if existing:
            existing.label = validated["label"]
            existing.comment = validated.get("comment", "")
            existing.save(update_fields=["label", "comment"])
            return existing
        return super().create(validated)

class DocumentBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id", "title", "source_slug", "authority", "doc_type",
            "number", "year", "published_date", "state"
        ]

class ChunkBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = ["id", "ordinal", "section", "block", "token_count"]

class SearchHitWithDocSerializer(serializers.ModelSerializer):
    document = DocumentBriefSerializer(read_only=True)
    chunk = ChunkBriefSerializer(read_only=True)

    # feedback por hit (los llena la vista vía annotate)
    useful_count = serializers.IntegerField(read_only=True)
    not_useful_count = serializers.IntegerField(read_only=True)
    my_feedback_label = serializers.CharField(read_only=True, allow_null=True)

    # snippet opcional
    snippet = serializers.SerializerMethodField()

    class Meta:
        model = SearchHit
        fields = [
            "id","rank",
            "score_vector","score_lexical","score_rerank",
            "meta_json","created_at",
            "document","chunk",
            "useful_count","not_useful_count","my_feedback_label",
            "snippet",
        ]

    def get_snippet(self, obj):
        include_snippet = self.context.get("include_snippet") is True
        if not include_snippet:
            return None
        text = getattr(obj.chunk, "block", None) or getattr(obj.chunk, "text", "") or ""
        return (text[:500] + "…") if len(text) > 500 else text