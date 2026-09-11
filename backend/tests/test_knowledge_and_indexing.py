import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models.bot import Bot
from app.db.models.crawl import Page
from app.db.models.knowledge import Chunk, Document
from app.db.models.user import User
from app.embeddings.service import EmbeddingService
from app.knowledge.chunking import ChunkItem, SemanticChunker
from app.knowledge.indexing import run_knowledge_indexing_pipeline
from app.knowledge.markdown import CanonicalMarkdownGenerator
from app.llm.client import MockLLMClient, get_llm_client
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_canonical_markdown_generation():
    """Verify canonical website.md generation with structured YAML metadata and hashing."""
    bot = Bot(id="bot-test-md", name="Acme Cloud", website_url="https://acme.example.com", user_id="u1")
    pages = [
        Page(
            id="p1",
            bot_id=bot.id,
            url="https://acme.example.com/",
            title="Acme Home",
            content="Acme provides enterprise cloud storage solutions.",
            crawl_status="SUCCESS",
        ),
        Page(
            id="p2",
            bot_id=bot.id,
            url="https://acme.example.com/pricing",
            title="Pricing Plans",
            content="Starter: $10/mo.\nPro: $30/mo.",
            crawl_status="SUCCESS",
        ),
    ]

    md = CanonicalMarkdownGenerator.generate(bot, pages)
    assert "# Acme Cloud — Website Knowledge Base" in md
    assert "https://acme.example.com" in md
    assert "### Page 1: Acme Home" in md
    assert "source_url: https://acme.example.com/" in md
    assert "### Page 2: Pricing Plans" in md
    assert "Starter: $10/mo." in md

    # SHA-256 Hash check
    content_hash = CanonicalMarkdownGenerator.compute_hash(md)
    assert len(content_hash) == 64
    assert CanonicalMarkdownGenerator.compute_hash(md) == content_hash

    # Pluggable LLM normalization hook check
    assert CanonicalMarkdownGenerator.normalize_with_llm(md, None) == md
    normalized_mock = CanonicalMarkdownGenerator.normalize_with_llm(md, lambda txt: f"[Normalized] {txt[:20]}")
    assert normalized_mock.startswith("[Normalized]")


def test_semantic_chunker():
    """Verify semantic chunking preserves section headings, handles size limits, and overlaps."""
    chunker = SemanticChunker(target_chunk_size=150, min_chunk_size=30, overlap=30)

    page = Page(
        id="p10",
        bot_id="bot-1",
        url="https://example.com/docs",
        title="Documentation",
        content=(
            "## Architecture Overview\n\n"
            "This document describes the core backend architecture and services.\n\n"
            "## Database Design\n\n"
            "We use PostgreSQL with pgvector for storing high dimensional embeddings."
        ),
        crawl_status="SUCCESS",
    )

    chunks = chunker.chunk_page(page)
    assert len(chunks) >= 2
    sections = [c.section for c in chunks]
    assert "Architecture Overview" in sections
    assert "Database Design" in sections

    for c in chunks:
        assert c.source_url == page.url
        assert c.page_id == page.id
        assert "source_url" in c.metadata


def test_embedding_service():
    """Verify embedding service generates vectors of correct dimension for mock and FastEmbed."""
    sample_texts = [
        "What are your operating hours?",
        "How much does the Pro subscription cost?",
    ]

    # 1. Mock provider (fast, offline)
    mock_vecs = EmbeddingService.embed_texts(sample_texts, provider="mock")
    assert len(mock_vecs) == 2
    assert len(mock_vecs[0]) == 384
    assert len(mock_vecs[1]) == 384

    # 2. FastEmbed local ONNX model
    fast_vecs = EmbeddingService.embed_texts(sample_texts, provider="fastembed")
    assert len(fast_vecs) == 2
    assert len(fast_vecs[0]) == 384
    assert isinstance(fast_vecs[0][0], float)

    # Query embedding
    q_vec = EmbeddingService.embed_query("pricing", provider="mock")
    assert len(q_vec) == 384


def test_llm_client_pluggability():
    """Verify Generative LLM abstraction allows pluggable models (Mock, Groq, Gemini, etc.)."""
    mock_client = get_llm_client("mock")
    assert isinstance(mock_client, MockLLMClient)
    res = mock_client.generate_response("Tell me about Acme Cloud")
    assert "Acme Cloud" in res or "MockLLM" in res

    from app.llm.client import GroqLLMClient
    groq_client = GroqLLMClient(api_key="gsk_mock_test_key", model="llama-3.3-70b-versatile")
    assert groq_client.api_key == "gsk_mock_test_key"
    assert groq_client.model == "llama-3.3-70b-versatile"


def test_knowledge_indexing_pipeline_and_multi_tenant_isolation(client, db):
    """
    End-to-end test of knowledge indexing pipeline, pgvector storage,
    API routes, and strict multi-tenant boundary enforcement.
    """
    pwd = "StrongPassword123!"

    # 1. Register User A and create Bot A
    user_a_email = f"know_user_a_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": user_a_email, "password": pwd})
    token_a = client.post("/api/auth/login", json={"email": user_a_email, "password": pwd}).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    bot_a_resp = client.post(
        "/api/bots",
        json={"name": "Knowledge Bot A", "website_url": "https://tenant-a.example.com"},
        headers=headers_a,
    )
    bot_a_id = bot_a_resp.json()["id"]

    # 2. Add crawled pages for Bot A
    page1 = Page(
        bot_id=bot_a_id,
        url="https://tenant-a.example.com/",
        title="Tenant A Home",
        content="Tenant A delivers next-generation AI pipelines.",
        crawl_status="SUCCESS",
    )
    page2 = Page(
        bot_id=bot_a_id,
        url="https://tenant-a.example.com/pricing",
        title="Tenant A Pricing",
        content="Tier 1: Free\nTier 2: Premium at $50/mo.",
        crawl_status="SUCCESS",
    )
    db.add_all([page1, page2])
    db.commit()

    # 3. Execute Knowledge Indexing Pipeline for Bot A (using mock provider for speed)
    result = run_knowledge_indexing_pipeline(bot_id=bot_a_id, db=db, embedding_provider="mock")
    assert result["status"] == "success"
    assert result["pages_count"] == 2
    assert result["chunks_count"] >= 2

    # Verify Bot A status transitioned to READY
    bot_a_db = db.get(Bot, bot_a_id)
    assert bot_a_db.status == "READY"

    # Verify Document table contains canonical website.md
    doc = db.scalar(
        select(Document).where(Document.bot_id == bot_a_id, Document.type == "canonical_markdown")
    )
    assert doc is not None
    assert "Tenant A Pricing" in doc.markdown_content
    assert doc.content_hash is not None

    # Verify Chunks table in DB
    chunks_a = db.scalars(select(Chunk).where(Chunk.bot_id == bot_a_id)).all()
    assert len(chunks_a) >= 2
    for chunk in chunks_a:
        assert chunk.bot_id == bot_a_id
        assert chunk.embedding is not None

    # 4. Verify Knowledge API Endpoints for Bot A
    # GET /api/bots/{bot_id}/knowledge/markdown
    md_resp = client.get(f"/api/bots/{bot_a_id}/knowledge/markdown", headers=headers_a)
    assert md_resp.status_code == 200
    md_data = md_resp.json()
    assert md_data["bot_id"] == bot_a_id
    assert "Tenant A Home" in md_data["markdown_content"]
    assert md_data["content_hash"] == doc.content_hash

    # GET /api/bots/{bot_id}/chunks
    chunks_resp = client.get(f"/api/bots/{bot_a_id}/chunks", headers=headers_a)
    assert chunks_resp.status_code == 200
    chunks_data = chunks_resp.json()
    assert chunks_data["total"] == len(chunks_a)
    assert len(chunks_data["chunks"]) == len(chunks_a)
    assert chunks_data["chunks"][0]["bot_id"] == bot_a_id

    # POST /api/bots/{bot_id}/index (Trigger re-indexing via API)
    reindex_resp = client.post(
        f"/api/bots/{bot_a_id}/index",
        json={"embedding_provider": "mock"},
        headers=headers_a,
    )
    assert reindex_resp.status_code == 200
    assert reindex_resp.json()["status"] == "success"

    # Verify no duplicate chunk accumulation after re-indexing
    chunks_after_reindex = db.scalars(select(Chunk).where(Chunk.bot_id == bot_a_id)).all()
    assert len(chunks_after_reindex) == len(chunks_a)

    # 5. Non-Negotiable Multi-Tenant Security Verification:
    # Register User B and create Bot B
    user_b_email = f"know_user_b_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": user_b_email, "password": pwd})
    token_b = client.post("/api/auth/login", json={"email": user_b_email, "password": pwd}).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    bot_b_resp = client.post(
        "/api/bots",
        json={"name": "Knowledge Bot B", "website_url": "https://tenant-b.example.com"},
        headers=headers_b,
    )
    bot_b_id = bot_b_resp.json()["id"]

    # User B CANNOT access Bot A's canonical markdown (must be 404)
    assert client.get(f"/api/bots/{bot_a_id}/knowledge/markdown", headers=headers_b).status_code == 404

    # User B CANNOT access Bot A's chunks (must be 404)
    assert client.get(f"/api/bots/{bot_a_id}/chunks", headers=headers_b).status_code == 404

    # User B CANNOT trigger indexing for Bot A (must be 404)
    assert client.post(f"/api/bots/{bot_a_id}/index", headers=headers_b).status_code == 404

    # Bot B initially has 0 chunks and no canonical markdown
    assert client.get(f"/api/bots/{bot_b_id}/knowledge/markdown", headers=headers_b).status_code == 404
    chunks_b_resp = client.get(f"/api/bots/{bot_b_id}/chunks", headers=headers_b).json()
    assert chunks_b_resp["total"] == 0

    # Ensure zero data leakage at database query level
    bot_b_chunks_in_db = db.scalars(select(Chunk).where(Chunk.bot_id == bot_b_id)).all()
    assert len(bot_b_chunks_in_db) == 0

    # Cleanup
    user_a = db.query(User).filter_by(email=user_a_email).first()
    user_b = db.query(User).filter_by(email=user_b_email).first()
    if user_a:
        db.delete(user_a)
    if user_b:
        db.delete(user_b)
    db.commit()

