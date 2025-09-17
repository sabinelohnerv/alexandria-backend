from rest_framework import serializers
from .models import ChatSession, ChatMessage, SearchHit, Feedback

class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ["id", "title", "created_at", "updated_at"]


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "session", "role", "text", "answer_json", "latency_ms", "created_at"]


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
