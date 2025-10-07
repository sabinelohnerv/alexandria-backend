# urls.py
from django.urls import path, include
from rest_framework_nested import routers
from .views import ChatSessionViewSet, ChatMessageViewSet, AskView, FeedbackView, HitFileView

router = routers.SimpleRouter()
router.register(r"sessions", ChatSessionViewSet, basename="chat-sessions")

# nested: /sessions/{session_id}/messages/
msgs = routers.NestedSimpleRouter(router, r"sessions", lookup="session")
msgs.register(r"messages", ChatMessageViewSet, basename="session-messages")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(msgs.urls)),

    path("ask/", AskView.as_view(), name="search-ask"),
    path("feedback/", FeedbackView.as_view(), name="search-feedback"),

    path(
        "sessions/<int:session_id>/messages/<int:message_id>/hits/<int:hit_id>/file/",
        HitFileView.as_view(),
        name="hit-file",
    ),
]
