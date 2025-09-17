from django.urls import path, include
from rest_framework_nested import routers
from .views import ChatSessionViewSet, ChatMessageViewSet, AskView, FeedbackView

router = routers.SimpleRouter()
router.register(r"sessions", ChatSessionViewSet, basename="chat-sessions")

# nested: /sessions/{id}/messages
msgs = routers.NestedSimpleRouter(router, r"sessions", lookup="session")
msgs.register(r"messages", ChatMessageViewSet, basename="chat-messages")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(msgs.urls)),
    path("ask/", AskView.as_view(), name="search-ask"),
    path("feedback/", FeedbackView.as_view(), name="search-feedback"),
]
