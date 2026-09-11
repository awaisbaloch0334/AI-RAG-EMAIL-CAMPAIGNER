import uuid
import pytest
from fastapi.testclient import TestClient

from app.crawler.discovery import extract_links, is_same_domain, normalize_url
from app.crawler.ssrf import is_safe_url, validate_url
from app.db.database import SessionLocal
from app.db.models.bot import Bot
from app.db.models.crawl import CrawlJob, Page
from app.db.models.user import User
from app.extraction.extractor import ContentExtractor
from app.main import app
from app.tasks.crawl_tasks import run_crawl_pipeline


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


def test_ssrf_protection():
    """Verify SSRF defenses reject internal, private, and metadata targets."""
    # Blocked hosts and private IPs
    assert not is_safe_url("http://localhost:8000/api")[0]
    assert not is_safe_url("http://127.0.0.1:5432/")[0]
    assert not is_safe_url("http://169.254.169.254/latest/meta-data/")[0]
    assert not is_safe_url("http://10.0.0.5/admin")[0]
    assert not is_safe_url("http://192.168.1.1/")[0]
    assert not is_safe_url("file:///etc/passwd")[0]
    assert not is_safe_url("gopher://127.0.0.1:6379")[0]

    with pytest.raises(ValueError):
        validate_url("http://localhost/secret")

    # Allowed external URLs
    assert is_safe_url("https://example.com")[0]
    assert is_safe_url("http://example.com/about")[0]


def test_url_discovery_and_normalization():
    """Verify link normalization, tracking parameter stripping, and domain checking."""
    raw_url = "https://example.com/pricing/?utm_source=twitter&utm_medium=social#features"
    normalized = normalize_url(raw_url)
    assert "utm_source" not in normalized
    assert "#features" not in normalized
    assert normalized == "https://example.com/pricing"

    assert is_same_domain("https://example.com/blog", "https://example.com")
    assert is_same_domain("https://www.example.com", "https://example.com")
    assert not is_same_domain("https://other-site.com", "https://example.com")

    sample_html = """
    <html>
      <body>
        <a href="/about">About Us</a>
        <a href="https://example.com/products">Products</a>
        <a href="https://external.com/partner">External Partner</a>
        <a href="/manual.pdf">User Manual PDF</a>
        <a href="mailto:support@example.com">Email Us</a>
      </body>
    </html>
    """
    links = extract_links(sample_html, "https://example.com")
    assert "https://example.com/about" in links
    assert "https://example.com/products" in links
    assert "https://external.com/partner" not in links  # External domain excluded
    assert "https://example.com/manual.pdf" not in links  # Non-HTML extension excluded


def test_content_extraction_and_boilerplate_removal():
    """Verify HTML cleaning, boilerplate stripping, and content hashing."""
    sample_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Acme Corp | Smart Robotics</title>
        <script>console.log("tracking script");</script>
        <style>.ads { color: red; }</style>
      </head>
      <body>
        <header>
          <nav><a href="/">Home</a><a href="/contact">Contact</a></nav>
        </header>

        <div class="cookie-banner">
          <p>We use cookies to track you. Accept?</p>
        </div>

        <main>
          <h1>Autonomous Fleet Navigation</h1>
          <p>Acme Corp builds enterprise autonomous mobile robots for warehouses.</p>
          <h2>Key Specifications</h2>
          <p>Payload capacity is 1500kg with 12-hour continuous battery life.</p>
          <img src="/images/robot.png" alt="Acme Autonomous Robot" />
        </main>

        <footer>
          <p>Copyright 2026 Acme Corp. All rights reserved.</p>
        </footer>
      </body>
    </html>
    """
    data = ContentExtractor.extract(sample_html, "https://example.com/products/robot")

    assert data.title == "Acme Corp | Smart Robotics"
    assert "Autonomous Fleet Navigation" in data.headings
    assert "Key Specifications" in data.headings

    # Boilerplate check: nav, footer, script, and cookie text MUST be stripped
    assert "tracking script" not in data.clean_text
    assert "We use cookies" not in data.clean_text
    assert "Copyright 2026" not in data.clean_text

    # Main content check
    assert "Acme Corp builds enterprise autonomous mobile robots" in data.clean_text
    assert "Payload capacity is 1500kg" in data.clean_text

    # Images & hash check
    assert len(data.images) == 1
    assert data.images[0]["url"] == "https://example.com/images/robot.png"
    assert len(data.content_hash) == 64  # SHA-256


def test_crawl_pipeline_and_api(client: TestClient, db, monkeypatch):
    """
    Test the ingestion pipeline and crawl API endpoints with strict tenant scoping.
    """
    # 1. Setup User A and Bot A
    user_email = f"crawler_user_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "password123!"
    client.post("/api/auth/register", json={"email": user_email, "password": pwd})
    token = client.post("/api/auth/login", json={"email": user_email, "password": pwd}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    bot_resp = client.post(
        "/api/bots",
        json={"name": "Crawler Test Bot", "website_url": "https://crawler-test.example.com"},
        headers=headers,
    )
    bot_id = bot_resp.json()["id"]

    # 2. Mock WebCrawler to return predictable test content without external internet dependency
    mock_html = """
    <html>
      <head><title>Mocked Site Home</title></head>
      <body>
        <h1>Welcome to Mocked Tech</h1>
        <p>Mocked Tech provides cloud hosting solutions.</p>
      </body>
    </html>
    """
    from urllib.parse import urljoin
    from app.crawler.crawler import WebCrawler

    def mock_crawl_site(self, start_url, *args, **kwargs):
        base = normalize_url(start_url)
        about_url = urljoin(base if base.endswith("/") else base + "/", "about")
        return [
            ContentExtractor.extract(mock_html, base),
            ContentExtractor.extract("<html><body><h1>About Us</h1><p>Founded in 2020.</p></body></html>", about_url),
        ]

    monkeypatch.setattr(WebCrawler, "crawl_site", mock_crawl_site)
    monkeypatch.setattr("app.api.routes.crawl.start_crawl_task.delay", lambda *args, **kwargs: None)

    # 3. Trigger Crawl API
    crawl_resp = client.post(f"/api/bots/{bot_id}/crawl", json={"max_pages": 5}, headers=headers)
    assert crawl_resp.status_code == 202
    job_data = crawl_resp.json()
    assert job_data["bot_id"] == bot_id
    job_id = job_data["id"]

    # 4. Execute pipeline directly (simulating worker completion)
    pipeline_result = run_crawl_pipeline(bot_id=bot_id, job_id=job_id, max_pages=5)
    assert pipeline_result["status"] == "success"
    assert pipeline_result["total_pages"] == 2
    assert pipeline_result["processed_pages"] == 2

    # 5. Check Crawl Status API
    status_resp = client.get(f"/api/bots/{bot_id}/crawl/status", headers=headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "COMPLETED"
    assert status_data["total_pages"] == 2
    assert status_data["processed_pages"] == 2

    # 6. Check Pages API
    pages_resp = client.get(f"/api/bots/{bot_id}/pages", headers=headers)
    assert pages_resp.status_code == 200
    pages_data = pages_resp.json()
    assert pages_data["total"] == 2
    urls = [p["url"] for p in pages_data["pages"]]
    assert "https://crawler-test.example.com/" in urls
    assert "https://crawler-test.example.com/about" in urls

    # Verify all pages in DB have bot_id strictly matching bot_id
    pages_in_db = db.query(Page).filter_by(bot_id=bot_id).all()
    assert len(pages_in_db) == 2
    for p in pages_in_db:
        assert p.bot_id == bot_id

    # 7. Cross-Tenant Security Invariant: User B cannot view pages or trigger crawl for Bot A
    user_b_email = f"user_b_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/auth/register", json={"email": user_b_email, "password": pwd})
    token_b = client.post("/api/auth/login", json={"email": user_b_email, "password": pwd}).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    assert client.get(f"/api/bots/{bot_id}/pages", headers=headers_b).status_code == 404
    assert client.post(f"/api/bots/{bot_id}/crawl", json={"max_pages": 5}, headers=headers_b).status_code == 404
    assert client.get(f"/api/bots/{bot_id}/crawl/status", headers=headers_b).status_code == 404

    # Cleanup
    user_a = db.query(User).filter_by(email=user_email).first()
    user_b = db.query(User).filter_by(email=user_b_email).first()
    if user_a:
        db.delete(user_a)
    if user_b:
        db.delete(user_b)
    db.commit()
