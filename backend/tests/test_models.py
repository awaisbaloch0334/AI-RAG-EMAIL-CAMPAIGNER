import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models import (
    User,
    Bot,
    CrawlJob,
    Page,
    Document,
    Chunk,
    Asset,
    BrandSettings,
    Conversation,
    Message,
)


@pytest.fixture
def db_session():
    """Provides a transactional database session for tests and rolls back or cleans up."""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_user_and_bot_creation(db_session: Session):
    # 1. Create a user
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=test_email,
        password_hash="hashed_secret_test",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.email == test_email

    # 2. Create a bot under this user
    bot = Bot(
        user_id=user.id,
        name="Acme Support Bot",
        website_url="https://acme.example.com",
        status="PENDING",
    )
    db_session.add(bot)
    db_session.commit()
    db_session.refresh(bot)

    assert bot.id.startswith("bot_")
    assert bot.user_id == user.id
    assert bot.user.email == test_email

    # Cleanup
    db_session.delete(user)
    db_session.commit()


def test_full_model_hierarchy_and_cascade(db_session: Session):
    # Create user
    user = User(
        email=f"cascade_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hashed_secret_cascade",
    )
    db_session.add(user)
    db_session.flush()

    # Create bot
    bot = Bot(
        user_id=user.id,
        name="Full Flow Bot",
        website_url="https://flow.example.com",
        status="READY",
    )
    db_session.add(bot)
    db_session.flush()

    # Create BrandSettings
    branding = BrandSettings(
        bot_id=bot.id,
        company_name="Flow Inc",
        primary_color="#1E40AF",
        position="bottom-right",
    )
    db_session.add(branding)

    # Create CrawlJob
    crawl_job = CrawlJob(
        bot_id=bot.id,
        status="COMPLETED",
        total_pages=2,
        processed_pages=2,
        failed_pages=0,
    )
    db_session.add(crawl_job)

    # Create Page
    page = Page(
        bot_id=bot.id,
        url="https://flow.example.com/about",
        title="About Flow",
        content="Flow Inc provides streaming automation.",
        crawl_status="SUCCESS",
    )
    db_session.add(page)
    db_session.flush()

    # Create Document
    doc = Document(
        bot_id=bot.id,
        page_id=page.id,
        type="page",
        markdown_content="# About Flow\nFlow Inc provides streaming automation.",
        source_url=page.url,
    )
    db_session.add(doc)

    # Create Chunk with pgvector embedding
    test_embedding = [0.1] * 1536
    chunk = Chunk(
        bot_id=bot.id,
        page_id=page.id,
        content="Flow Inc provides streaming automation.",
        embedding=test_embedding,
        chunk_index=0,
        chunk_metadata={"source_url": page.url, "section": "About"},
    )
    db_session.add(chunk)

    # Create Asset
    asset = Asset(
        bot_id=bot.id,
        page_id=page.id,
        type="logo",
        source_url="https://flow.example.com/logo.png",
        asset_metadata={"alt": "Flow Logo"},
    )
    db_session.add(asset)

    # Create Conversation & Message
    conv = Conversation(
        bot_id=bot.id,
        session_id=f"sess_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(conv)
    db_session.flush()

    msg1 = Message(
        conversation_id=conv.id,
        role="user",
        content="What does Flow Inc do?",
    )
    msg2 = Message(
        conversation_id=conv.id,
        role="assistant",
        content="Flow Inc provides streaming automation.",
    )
    db_session.add_all([msg1, msg2])
    db_session.commit()

    # Verify everything exists and is linked
    saved_bot = db_session.get(Bot, bot.id)
    assert saved_bot is not None
    assert saved_bot.brand_settings.company_name == "Flow Inc"
    assert len(saved_bot.crawl_jobs) == 1
    assert len(saved_bot.pages) == 1
    assert len(saved_bot.documents) == 1
    assert len(saved_bot.chunks) == 1
    assert len(saved_bot.assets) == 1
    assert len(saved_bot.conversations) == 1
    assert len(saved_bot.conversations[0].messages) == 2

    # Verify pgvector embedding storage
    saved_chunk = db_session.get(Chunk, chunk.id)
    assert saved_chunk is not None
    assert len(saved_chunk.embedding) == 1536

    # Test Cascade Deletion: Deleting the bot must delete all child records
    db_session.delete(saved_bot)
    db_session.commit()

    assert db_session.get(BrandSettings, bot.id) is None
    assert db_session.get(CrawlJob, crawl_job.id) is None
    assert db_session.get(Page, page.id) is None
    assert db_session.get(Document, doc.id) is None
    assert db_session.get(Chunk, chunk.id) is None
    assert db_session.get(Asset, asset.id) is None
    assert db_session.get(Conversation, conv.id) is None
    assert db_session.get(Message, msg1.id) is None

    # Cleanup user
    db_session.delete(user)
    db_session.commit()


def test_tenant_isolation_rule(db_session: Session):
    """
    CRITICAL NON-NEGOTIABLE INVARIANT:
    Bot A must never retrieve Bot B's knowledge.
    Enforced strictly at the bot_id scoping layer.
    """
    # User A with Bot A
    user_a = User(
        email=f"user_a_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hash_a",
    )
    db_session.add(user_a)
    db_session.flush()

    bot_a = Bot(
        user_id=user_a.id,
        name="Bot A (Healthcare)",
        website_url="https://health.example.com",
        status="READY",
    )
    db_session.add(bot_a)
    db_session.flush()

    chunk_a = Chunk(
        bot_id=bot_a.id,
        content="Patient record secret information for Hospital A.",
        embedding=[0.2] * 1536,
        chunk_index=0,
    )
    db_session.add(chunk_a)

    # User B with Bot B
    user_b = User(
        email=f"user_b_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="hash_b",
    )
    db_session.add(user_b)
    db_session.flush()

    bot_b = Bot(
        user_id=user_b.id,
        name="Bot B (Finance)",
        website_url="https://finance.example.com",
        status="READY",
    )
    db_session.add(bot_b)
    db_session.flush()

    chunk_b = Chunk(
        bot_id=bot_b.id,
        content="Financial balance sheet confidential data for Bank B.",
        embedding=[0.8] * 1536,
        chunk_index=0,
    )
    db_session.add(chunk_b)
    db_session.commit()

    # Query scoped strictly to Bot A
    stmt_a = select(Chunk).where(Chunk.bot_id == bot_a.id)
    results_a = db_session.scalars(stmt_a).all()

    assert len(results_a) == 1
    assert results_a[0].content == "Patient record secret information for Hospital A."
    assert "Bank B" not in results_a[0].content

    # Query scoped strictly to Bot B
    stmt_b = select(Chunk).where(Chunk.bot_id == bot_b.id)
    results_b = db_session.scalars(stmt_b).all()

    assert len(results_b) == 1
    assert results_b[0].content == "Financial balance sheet confidential data for Bank B."
    assert "Hospital A" not in results_b[0].content

    # Test pgvector vector cosine distance retrieval scoped by bot_id
    query_vector = [0.2] * 1536
    vector_search_stmt = (
        select(Chunk)
        .where(Chunk.bot_id == bot_a.id)
        .order_by(Chunk.embedding.cosine_distance(query_vector))
        .limit(5)
    )
    retrieved_for_a = db_session.scalars(vector_search_stmt).all()

    assert len(retrieved_for_a) == 1
    assert retrieved_for_a[0].id == chunk_a.id

    # Cleanup
    db_session.delete(user_a)
    db_session.delete(user_b)
    db_session.commit()

