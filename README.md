
# Alexandria — Backend & AI Retrieval Engine

Backend API and AI-powered information retrieval system for **Alexandria**, a legal research assistant designed for the Bolivian legal context.

Alexandria was developed as a Computer Systems Engineering degree project for Sanjinés & Asociados. It helps legal professionals find relevant legislation and case law through natural-language queries, hybrid retrieval, and evidence-grounded AI responses.

## Tech Stack

| Area | Technologies |
|---|---|
| Language | Python |
| Backend | Django, Django REST Framework |
| Database | PostgreSQL, pgvector |
| Cache & Tasks | Redis, Celery |
| Authentication | JWT, Email OTP, RBAC |
| AI / NLP | RAG, BGE-M3, BGE Reranker, Llama 3 |
| Search | BM25 / Full-Text Search, Vector Similarity, RRF |
| Infrastructure | Docker |
| Testing | Django unit tests, Postman |

## Core Features

### Authentication & Access Control

- Controlled registration through a user whitelist
- Email-based OTP verification
- JWT authentication
- Password recovery using email OTP
- Role-based access control (`admin` / `user`)
- Request throttling and access validation

### AI-Powered Legal Research

Alexandria implements a Retrieval-Augmented Generation (RAG) pipeline designed to retrieve and prioritize relevant Bolivian legal documents before generating responses.

**Retrieval pipeline:**

1. Collect publicly available legal documents.
2. Extract, normalize, and segment document content.
3. Generate semantic embeddings using BGE-M3.
4. Store document metadata and vectors in PostgreSQL with pgvector.
5. Retrieve candidates through BM25 and vector similarity search.
6. Combine retrieval signals using Reciprocal Rank Fusion (RRF).
7. Re-rank candidates using a cross-encoder and legal relevance signals.
8. Generate evidence-grounded responses using Llama 3.
9. Return supporting citations and document references.

### Document Processing

- Legal document ingestion through web scraping
- Text extraction and normalization
- Document chunking and metadata preservation
- Lexical and semantic indexing
- Background processing with Celery
- Source traceability for retrieved documents

### Search & Session Management

- Natural-language legal queries
- Query history and session management
- Retrieved document references
- Integrated document access
- Relevance feedback on search results

### Feedback & Ranking Improvement

The system incorporates feedback from legal professionals to evaluate and refine retrieval quality.

- Feedback collection at result level
- Ranking decision tracking
- Training of updated ranking weights
- Version evaluation and controlled promotion
- Retrieval quality and latency monitoring

## Architecture

The backend follows a layered architecture:

```text
React Client
     |
     v
Django REST Framework
     |
     v
Application / Business Logic
     |
     +-- Authentication & Authorization
     +-- Search & RAG Pipeline
     +-- Session Management
     +-- Feedback & Ranking
     |
     v
Infrastructure
     |
     +-- PostgreSQL + pgvector
     +-- Redis
     +-- Celery Workers
     +-- Document Storage
     +-- Embedding / Reranking Models
     +-- Language Model
```

The separation between API delivery, application logic, and infrastructure helps keep the system modular and maintainable.

## Evaluation & Results

The system was evaluated through functional tests, technical tests, and user testing with legal professionals.

Results demonstrated:

- Identification of useful legal documents within seconds
- Reduction of document collection time from over an hour to minutes
- Fewer manual search iterations and document openings
- Improved access to supporting legal sources
- Positive feedback on usability and research workflow integration

## Development

The project uses Docker-based infrastructure with PostgreSQL and Redis.

Refer to the repository's configuration files for the exact environment variables, services, migrations, and startup commands required for local development.

## Project Context

Alexandria was developed in 2025 as an applied research and software engineering project at Universidad Privada del Valle (Univalle), Bolivia.

**Author:** Sabine Lohner Villarroel

**Focus:** Backend Engineering, Information Retrieval, Applied Machine Learning, Natural Language Processing, and LegalTech.

## Disclaimer

Alexandria is a legal research support tool. AI-generated responses must be verified against their cited legal sources and do not constitute legal advice.
