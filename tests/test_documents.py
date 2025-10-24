"""
Tests para el módulo documents
"""
import pytest
from datetime import date
from apps.documents.models import Document, Chunk


@pytest.mark.django_db
class TestDocumentModel:
    """Tests para el modelo Document"""

    def test_create_document(self):
        """Prueba creación de documento"""
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp",
            authority="TCP",
            doc_type="sentencia",
            number="0001/2024",
            year="2024",
            title="Sentencia Constitucional Plurinacional 0001/2024",
            state="PENDING"
        )
        assert doc.storage_key == "tcp/sentencia_001.pdf"
        assert doc.source_slug == "tcp"
        assert doc.authority == "TCP"
        assert doc.state == "PENDING"

    def test_document_str_representation(self):
        """Prueba representación en string del documento"""
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp"
        )
        assert "tcp:tcp/sentencia_001.pdf" == str(doc)

    def test_document_unique_storage_key(self):
        """Prueba que storage_key debe ser único"""
        Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp"
        )
        with pytest.raises(Exception):
            Document.objects.create(
                storage_key="tcp/sentencia_001.pdf",
                source_slug="tcp"
            )

    def test_document_with_published_date(self):
        """Prueba documento con fecha de publicación"""
        pub_date = date(2024, 1, 15)
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp",
            published_date=pub_date
        )
        assert doc.published_date == pub_date

    def test_document_meta_json_field(self):
        """Prueba campo JSON de metadatos"""
        meta_data = {
            "magistrado_relator": "Dr. Juan Pérez",
            "sala": "Primera"
        }
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp",
            meta=meta_data
        )
        assert doc.meta == meta_data

    def test_document_state_choices(self):
        """Prueba diferentes estados del documento"""
        states = ["PENDING", "EXTRACTED", "CHUNKED", "INDEXED", "FAILED"]
        for state in states:
            doc = Document.objects.create(
                storage_key=f"tcp/doc_{state}.pdf",
                source_slug="tcp",
                state=state
            )
            assert doc.state == state

    def test_document_source_choices(self):
        """Prueba diferentes fuentes de documentos"""
        sources = ["tcp", "tsj", "normativa"]
        for source in sources:
            doc = Document.objects.create(
                storage_key=f"{source}/doc_001.pdf",
                source_slug=source
            )
            assert doc.source_slug == source


@pytest.mark.django_db
class TestChunkModel:
    """Tests para el modelo Chunk"""

    def test_create_chunk(self):
        """Prueba creación de chunk"""
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp"
        )
        chunk = Chunk.objects.create(
            document=doc,
            ordinal=1,
            section="Fundamentos jurídicos",
            text="Este es el texto del chunk",
            token_count=10
        )
        assert chunk.document == doc
        assert chunk.ordinal == 1
        assert chunk.section == "Fundamentos jurídicos"
        assert chunk.token_count == 10

    def test_chunk_unique_together(self):
        """Prueba que document + ordinal deben ser únicos"""
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp"
        )
        Chunk.objects.create(
            document=doc,
            ordinal=1,
            text="Chunk 1"
        )
        with pytest.raises(Exception):
            Chunk.objects.create(
                document=doc,
                ordinal=1,
                text="Chunk 1 duplicado"
            )

    def test_chunk_with_section_and_block(self):
        """Prueba chunk con sección y bloque"""
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp"
        )
        chunk = Chunk.objects.create(
            document=doc,
            ordinal=1,
            section="Fundamentos jurídicos",
            block="Considerando I",
            text="Texto del considerando"
        )
        assert chunk.section == "Fundamentos jurídicos"
        assert chunk.block == "Considerando I"

    def test_chunk_cascade_delete(self):
        """Prueba que los chunks se eliminan al eliminar el documento"""
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp"
        )
        Chunk.objects.create(document=doc, ordinal=1, text="Chunk 1")
        Chunk.objects.create(document=doc, ordinal=2, text="Chunk 2")
        
        assert doc.chunks.count() == 2
        doc_id = doc.id
        doc.delete()
        assert Chunk.objects.filter(document_id=doc_id).count() == 0

    def test_multiple_documents_with_chunks(self):
        """Prueba múltiples documentos con sus chunks"""
        doc1 = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp"
        )
        doc2 = Document.objects.create(
            storage_key="tcp/sentencia_002.pdf",
            source_slug="tcp"
        )
        
        Chunk.objects.create(document=doc1, ordinal=1, text="Doc1 Chunk1")
        Chunk.objects.create(document=doc1, ordinal=2, text="Doc1 Chunk2")
        Chunk.objects.create(document=doc2, ordinal=1, text="Doc2 Chunk1")
        
        assert doc1.chunks.count() == 2
        assert doc2.chunks.count() == 1


@pytest.mark.django_db
class TestDocumentChunkRelationship:
    """Tests para la relación entre Document y Chunk"""

    def test_document_chunks_relationship(self):
        """Prueba relación de documento con chunks"""
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp"
        )
        chunk1 = Chunk.objects.create(document=doc, ordinal=1, text="Chunk 1")
        chunk2 = Chunk.objects.create(document=doc, ordinal=2, text="Chunk 2")
        
        assert doc.chunks.count() == 2
        assert chunk1 in doc.chunks.all()
        assert chunk2 in doc.chunks.all()

    def test_chunk_document_relationship(self):
        """Prueba relación inversa de chunk a documento"""
        doc = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp",
            title="Sentencia 001"
        )
        chunk = Chunk.objects.create(document=doc, ordinal=1, text="Chunk 1")
        
        assert chunk.document == doc
        assert chunk.document.title == "Sentencia 001"

    def test_filter_chunks_by_document(self):
        """Prueba filtrar chunks por documento"""
        doc1 = Document.objects.create(
            storage_key="tcp/sentencia_001.pdf",
            source_slug="tcp"
        )
        doc2 = Document.objects.create(
            storage_key="tcp/sentencia_002.pdf",
            source_slug="tcp"
        )
        
        Chunk.objects.create(document=doc1, ordinal=1, text="Doc1 Chunk1")
        Chunk.objects.create(document=doc2, ordinal=1, text="Doc2 Chunk1")
        
        doc1_chunks = Chunk.objects.filter(document=doc1)
        assert doc1_chunks.count() == 1
        assert doc1_chunks.first().text == "Doc1 Chunk1"


@pytest.mark.django_db
class TestDocumentQuerysets:
    """Tests para querysets y filtros de documentos"""

    def test_filter_by_source(self):
        """Prueba filtrar documentos por fuente"""
        Document.objects.create(storage_key="tcp/doc1.pdf", source_slug="tcp")
        Document.objects.create(storage_key="tsj/doc2.pdf", source_slug="tsj")
        
        tcp_docs = Document.objects.filter(source_slug="tcp")
        assert tcp_docs.count() == 1
        assert tcp_docs.first().source_slug == "tcp"

    def test_filter_by_state(self):
        """Prueba filtrar documentos por estado"""
        Document.objects.create(
            storage_key="tcp/doc1.pdf",
            source_slug="tcp",
            state="INDEXED"
        )
        Document.objects.create(
            storage_key="tcp/doc2.pdf",
            source_slug="tcp",
            state="PENDING"
        )
        
        indexed_docs = Document.objects.filter(state="INDEXED")
        assert indexed_docs.count() == 1

    def test_filter_by_year(self):
        """Prueba filtrar documentos por año"""
        Document.objects.create(
            storage_key="tcp/doc1.pdf",
            source_slug="tcp",
            year="2024"
        )
        Document.objects.create(
            storage_key="tcp/doc2.pdf",
            source_slug="tcp",
            year="2023"
        )
        
        docs_2024 = Document.objects.filter(year="2024")
        assert docs_2024.count() == 1

    def test_order_by_created_at(self):
        """Prueba ordenar documentos por fecha de creación"""
        doc1 = Document.objects.create(
            storage_key="tcp/doc1.pdf",
            source_slug="tcp"
        )
        doc2 = Document.objects.create(
            storage_key="tcp/doc2.pdf",
            source_slug="tcp"
        )
        
        docs = Document.objects.all().order_by("-created_at")
        assert docs.first() == doc2
        assert docs.last() == doc1
