"""
Tests para el módulo search
"""
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework import status
from apps.search.models import ChatSession, ChatMessage, SearchHit, Feedback
from apps.documents.models import Document, Chunk

User = get_user_model()


@pytest.fixture
def document_factory(db):
    """Factory para crear documentos de prueba"""
    def create_document(
        storage_key="tcp/test_doc.pdf",
        source_slug="tcp",
        **kwargs
    ):
        return Document.objects.create(
            storage_key=storage_key,
            source_slug=source_slug,
            **kwargs
        )
    return create_document


@pytest.fixture
def chunk_factory(db):
    """Factory para crear chunks de prueba"""
    def create_chunk(document, ordinal=1, text="Test chunk text", **kwargs):
        return Chunk.objects.create(
            document=document,
            ordinal=ordinal,
            text=text,
            **kwargs
        )
    return create_chunk


@pytest.fixture
def session_factory(db):
    """Factory para crear sesiones de chat"""
    def create_session(user, title="Test Session", **kwargs):
        return ChatSession.objects.create(
            user=user,
            title=title,
            **kwargs
        )
    return create_session


@pytest.mark.django_db
class TestChatSessionModel:
    """Tests para el modelo ChatSession"""

    def test_create_chat_session(self, regular_user):
        """Prueba creación de sesión de chat"""
        session = ChatSession.objects.create(
            user=regular_user,
            title="Mi primera consulta"
        )
        assert session.user == regular_user
        assert session.title == "Mi primera consulta"
        assert session.deleted_at is None

    def test_chat_session_str_with_title(self, regular_user):
        """Prueba representación en string con título"""
        session = ChatSession.objects.create(
            user=regular_user,
            title="Consulta sobre cosa juzgada"
        )
        assert str(session) == "Consulta sobre cosa juzgada"

    def test_chat_session_str_without_title(self, regular_user):
        """Prueba representación en string sin título"""
        session = ChatSession.objects.create(user=regular_user)
        assert f"Session #{session.pk}" == str(session)

    def test_soft_delete_session(self, regular_user):
        """Prueba soft delete de sesión"""
        session = ChatSession.objects.create(user=regular_user)
        assert session.deleted_at is None
        
        session.soft_delete()
        assert session.deleted_at is not None
        assert session.is_deleted is True

    def test_soft_delete_idempotent(self, regular_user):
        """Prueba que soft delete es idempotente"""
        session = ChatSession.objects.create(user=regular_user)
        session.soft_delete()
        first_deleted_at = session.deleted_at
        
        session.soft_delete()
        assert session.deleted_at == first_deleted_at

    def test_restore_session(self, regular_user):
        """Prueba restauración de sesión"""
        session = ChatSession.objects.create(user=regular_user)
        session.soft_delete()
        assert session.is_deleted is True
        
        session.restore()
        assert session.deleted_at is None
        assert session.is_deleted is False

    def test_is_deleted_property(self, regular_user):
        """Prueba propiedad is_deleted"""
        session = ChatSession.objects.create(user=regular_user)
        assert session.is_deleted is False
        
        session.deleted_at = timezone.now()
        assert session.is_deleted is True


@pytest.mark.django_db
class TestChatMessageModel:
    """Tests para el modelo ChatMessage"""

    def test_create_user_message(self, session_factory, regular_user):
        """Prueba creación de mensaje de usuario"""
        session = session_factory(regular_user)
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            text="¿Qué es la cosa juzgada constitucional?"
        )
        assert message.session == session
        assert message.role == ChatMessage.ROLE_USER
        assert "cosa juzgada" in message.text

    def test_create_assistant_message(self, session_factory, regular_user):
        """Prueba creación de mensaje del asistente"""
        session = session_factory(regular_user)
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text="La cosa juzgada constitucional es...",
            latency_ms=1500
        )
        assert message.role == ChatMessage.ROLE_ASSISTANT
        assert message.latency_ms == 1500

    def test_message_with_answer_json(self, session_factory, regular_user):
        """Prueba mensaje con JSON de respuesta"""
        session = session_factory(regular_user)
        answer_data = {
            "sources": ["SCP 0001/2024", "SCP 0002/2024"],
            "confidence": 0.95
        }
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text="Respuesta...",
            answer_json=answer_data
        )
        assert message.answer_json == answer_data

    def test_message_ordering(self, session_factory, regular_user):
        """Prueba ordenamiento de mensajes"""
        session = session_factory(regular_user)
        msg1 = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            text="Primera pregunta"
        )
        msg2 = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text="Primera respuesta"
        )
        msg3 = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_USER,
            text="Segunda pregunta"
        )
        
        messages = list(session.messages.all())
        assert messages[0] == msg1
        assert messages[1] == msg2
        assert messages[2] == msg3

    def test_message_cascade_delete(self, session_factory, regular_user):
        """Prueba que los mensajes se eliminan al eliminar la sesión"""
        session = session_factory(regular_user)
        ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, text="Test")
        ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, text="Response")
        
        assert session.messages.count() == 2
        session_id = session.id
        session.delete()
        assert ChatMessage.objects.filter(session_id=session_id).count() == 0


@pytest.mark.django_db
class TestSearchHitModel:
    """Tests para el modelo SearchHit"""

    def test_create_search_hit(self, session_factory, regular_user, document_factory, chunk_factory):
        """Prueba creación de hit de búsqueda"""
        session = session_factory(regular_user)
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text="Respuesta"
        )
        doc = document_factory()
        chunk = chunk_factory(doc)
        
        hit = SearchHit.objects.create(
            message=message,
            document=doc,
            chunk=chunk,
            rank=1,
            score_vector=0.85,
            score_lexical=7.5,
            score_rerank=0.92
        )
        assert hit.message == message
        assert hit.document == doc
        assert hit.chunk == chunk
        assert hit.rank == 1
        assert hit.score_vector == 0.85

    def test_search_hit_ordering(self, session_factory, regular_user, document_factory, chunk_factory):
        """Prueba ordenamiento de hits por rank"""
        session = session_factory(regular_user)
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text="Respuesta"
        )
        doc = document_factory()
        chunk1 = chunk_factory(doc, ordinal=1)
        chunk2 = chunk_factory(doc, ordinal=2)
        chunk3 = chunk_factory(doc, ordinal=3)
        
        hit3 = SearchHit.objects.create(
            message=message, document=doc, chunk=chunk3,
            rank=3, score_vector=0.75
        )
        hit1 = SearchHit.objects.create(
            message=message, document=doc, chunk=chunk1,
            rank=1, score_vector=0.95
        )
        hit2 = SearchHit.objects.create(
            message=message, document=doc, chunk=chunk2,
            rank=2, score_vector=0.85
        )
        
        hits = list(message.hits.all())
        assert hits[0] == hit1
        assert hits[1] == hit2
        assert hits[2] == hit3

    def test_search_hit_with_meta_json(self, session_factory, regular_user, document_factory, chunk_factory):
        """Prueba hit con metadatos JSON"""
        session = session_factory(regular_user)
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text="Respuesta"
        )
        doc = document_factory()
        chunk = chunk_factory(doc)
        
        meta = {"retrieval_method": "hybrid", "query_expansion": True}
        hit = SearchHit.objects.create(
            message=message,
            document=doc,
            chunk=chunk,
            rank=1,
            score_vector=0.85,
            meta_json=meta
        )
        assert hit.meta_json == meta


@pytest.mark.django_db
class TestFeedbackModel:
    """Tests para el modelo Feedback"""

    def test_create_message_feedback(self, session_factory, regular_user):
        """Prueba creación de feedback para mensaje"""
        session = session_factory(regular_user)
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text="Respuesta"
        )
        
        feedback = Feedback.objects.create(
            user=regular_user,
            message=message,
            label=Feedback.LABEL_USEFUL,
            comment="Muy útil"
        )
        assert feedback.user == regular_user
        assert feedback.message == message
        assert feedback.label == Feedback.LABEL_USEFUL
        assert feedback.comment == "Muy útil"

    def test_create_hit_feedback(self, session_factory, regular_user, document_factory, chunk_factory):
        """Prueba creación de feedback para hit"""
        session = session_factory(regular_user)
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text="Respuesta"
        )
        doc = document_factory()
        chunk = chunk_factory(doc)
        hit = SearchHit.objects.create(
            message=message,
            document=doc,
            chunk=chunk,
            rank=1,
            score_vector=0.85
        )
        
        feedback = Feedback.objects.create(
            user=regular_user,
            hit=hit,
            label=Feedback.LABEL_NOT_USEFUL
        )
        assert feedback.hit == hit
        assert feedback.label == Feedback.LABEL_NOT_USEFUL


@pytest.mark.django_db
class TestChatSessionAPI:
    """Tests para los endpoints de la API de sesiones"""

    def test_list_sessions(self, authenticated_client, session_factory, regular_user):
        """Prueba listar sesiones"""
        session_factory(regular_user, title="Sesión 1")
        session_factory(regular_user, title="Sesión 2")
        
        response = authenticated_client.get("/api/search/sessions/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) >= 2

    def test_list_sessions_requires_auth(self, api_client):
        """Prueba que listar sesiones requiere autenticación"""
        response = api_client.get("/api/search/sessions/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_session(self, authenticated_client):
        """Prueba crear sesión"""
        data = {"title": "Nueva consulta"}
        response = authenticated_client.post("/api/search/sessions/", data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "Nueva consulta"

    def test_create_session_without_title(self, authenticated_client):
        """Prueba crear sesión sin título"""
        response = authenticated_client.post("/api/search/sessions/", {})
        assert response.status_code == status.HTTP_201_CREATED

    def test_retrieve_session(self, authenticated_client, session_factory, regular_user):
        """Prueba obtener detalle de sesión"""
        session = session_factory(regular_user, title="Test Session")
        response = authenticated_client.get(f"/api/search/sessions/{session.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Test Session"

    def test_update_session_title(self, authenticated_client, session_factory, regular_user):
        """Prueba actualizar título de sesión"""
        session = session_factory(regular_user, title="Old Title")
        data = {"title": "New Title"}
        response = authenticated_client.patch(f"/api/search/sessions/{session.id}/", data)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "New Title"

    def test_list_sessions_excludes_deleted_by_default(self, authenticated_client, session_factory, regular_user):
        """Prueba que por defecto no muestra sesiones eliminadas"""
        active_session = session_factory(regular_user, title="Active")
        deleted_session = session_factory(regular_user, title="Deleted")
        deleted_session.soft_delete()
        
        response = authenticated_client.get("/api/search/sessions/")
        assert response.status_code == status.HTTP_200_OK
        titles = [s["title"] for s in response.data["results"]]
        assert "Active" in titles
        assert "Deleted" not in titles

    def test_user_can_only_see_own_sessions(self, authenticated_client, session_factory, regular_user, user_factory):
        """Prueba que usuario solo ve sus propias sesiones"""
        other_user = user_factory(email="other@example.com")
        session_factory(regular_user, title="My Session")
        session_factory(other_user, title="Other Session")
        
        response = authenticated_client.get("/api/search/sessions/")
        assert response.status_code == status.HTTP_200_OK
        titles = [s["title"] for s in response.data["results"]]
        assert "My Session" in titles
        assert "Other Session" not in titles


@pytest.mark.django_db
class TestChatMessagesAPI:
    """Tests para los endpoints de mensajes"""

    def test_list_messages_from_session(self, authenticated_client, session_factory, regular_user):
        """Prueba listar mensajes de una sesión"""
        session = session_factory(regular_user)
        ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_USER, text="Pregunta")
        ChatMessage.objects.create(session=session, role=ChatMessage.ROLE_ASSISTANT, text="Respuesta")
        
        response = authenticated_client.get(f"/api/search/sessions/{session.id}/messages/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_messages_require_auth(self, api_client, session_factory, regular_user):
        """Prueba que listar mensajes requiere autenticación"""
        session = session_factory(regular_user)
        response = api_client.get(f"/api/search/sessions/{session.id}/messages/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestFeedbackAPI:
    """Tests para los endpoints de feedback"""

    def test_create_message_feedback(self, authenticated_client, session_factory, regular_user):
        """Prueba crear feedback para mensaje"""
        session = session_factory(regular_user)
        message = ChatMessage.objects.create(
            session=session,
            role=ChatMessage.ROLE_ASSISTANT,
            text="Respuesta"
        )
        
        data = {
            "message": message.id,
            "label": "useful",
            "comment": "Muy útil"
        }
        response = authenticated_client.post("/api/search/feedback/", data)
        assert response.status_code == status.HTTP_201_CREATED

    def test_feedback_requires_auth(self, api_client):
        """Prueba que crear feedback requiere autenticación"""
        data = {"message": 1, "label": "useful"}
        response = api_client.post("/api/search/feedback/", data)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
