# AUDIT REPORT — Embeddable Website-Specific RAG Chatbot Platform

Repository inspected: `embeddable-rag-chatbot.zip`. This report is a read-only inspection. No files in the repository were modified, created, or deleted.

---

## 1. PROJECT ARCHITECTURE

Monolithic **FastAPI backend** + **Celery/Redis async workers** + **PostgreSQL/pgvector** + two **no-build-step, CDN-based React SPAs** (Admin Dashboard, Chat iframe) + a **vanilla-JS embeddable widget loader**.

```
embeddable-rag-chatbot/
├── backend/
│   ├── app/
│   │   ├── api/routes/        FastAPI route handlers (auth, bots, crawl, knowledge, chat, widget)
│   │   ├── api/dependencies.py  Auth + bot-ownership dependency injection
│   │   ├── auth/               Password hashing, JWT, register/login service
│   │   ├── bots/                Bot CRUD + branding service
│   │   ├── crawler/            BFS crawler, SSRF guard, link discovery
│   │   ├── extraction/         HTML → clean text/contact/logo/color extraction
│   │   ├── knowledge/          Canonical Markdown, semantic chunker, indexing pipeline
│   │   ├── embeddings/         Pluggable embedding provider (FastEmbed/OpenAI/Gemini/Mock)
│   │   ├── rag/                Vector retriever + prompt builder (anti-injection)
│   │   ├── llm/                Pluggable generative LLM client (Groq/Gemini/Claude/OpenAI/Mock)
│   │   ├── chat/                Conversation orchestration, SSE streaming
│   │   ├── tasks/               Celery app + crawl/indexing task chain
│   │   ├── db/                  SQLAlchemy models + session/engine
│   │   ├── config.py            pydantic-settings Settings (.env driven)
│   │   └── main.py              FastAPI app assembly, CORS, static mount
│   ├── static/                  Served build artifacts: dashboard/, chat/, widget.js, demo.html
│   ├── alembic/                 Single migration, `CREATE EXTENSION vector` in env.py
│   └── tests/                   7 pytest files, 24 test functions
├── frontend/index.html          Dev-source copy of the Admin Dashboard (identical to backend/static/dashboard/index.html)
├── widget/widget.js              Dev-source copy of the widget loader (identical to backend/static/widget.js)
├── docker-compose.yml            Postgres (pgvector image) + Redis only — backend/frontend NOT containerized
└── PROJECT_SPEC.md / CURRENT_STATUS.md / AI_HANDOFF_PROMPT.md   Design docs (spec is aspirational source of truth; status doc tracks actual implementation)
```

**Module responsibilities**

| Module | Responsibility |
|---|---|
| `api/routes/*` | Thin HTTP layer; delegates to services |
| `auth/` | bcrypt hashing, JWT issuance/decoding, register/authenticate |
| `bots/` | Bot + BrandSettings CRUD, ownership-scoped queries |
| `crawler/` | SSRF-safe BFS crawl (static httpx + Playwright fallback for JS/SPA) |
| `extraction/` | BeautifulSoup-based cleaning, logo/contact/theme-color heuristics |
| `knowledge/` | Canonical `website.md` assembly, semantic chunking, orchpipeline |
| `embeddings/` | Provider-abstracted text→vector |
| `rag/` | Bot-scoped pgvector similarity search + injection-hardened prompt construction |
| `llm/` | Provider-abstracted chat completion, with automatic Mock fallback if no key |
| `chat/` | Conversation/message persistence, RAG orchestration, SSE (simulated streaming) |
| `tasks/` | Celery task definitions; also directly callable as plain functions (BackgroundTasks fallback) |
| `db/` | ORM models, engine/session factory |

---

## 2. CURRENT TECH STACK

**Backend (Python 3.11+, pinned in `backend/requirements.txt`, identical copy at repo root):**
- FastAPI 0.141.1, Uvicorn 0.52.4, Starlette
- SQLAlchemy 2.0 (declarative + `Mapped`/`mapped_column` style), Alembic 1.19
- psycopg 3 (`postgresql+psycopg://`)
- pgvector 0.5.0 (Python client) — Postgres extension `vector`
- Celery 5.6 + Redis (broker & result backend)
- FastEmbed 0.8 (ONNX runtime, local embedding inference, default model `BAAI/bge-small-en-v1.5`)
- httpx (outbound HTTP for crawling and LLM/embedding REST calls)
- BeautifulSoup4 + lxml (HTML parsing)
- Playwright 1.62 (headless Chromium fallback for JS-rendered pages and CTA color detection)
- Pillow (dominant-color extraction from logo images)
- PyJWT 2.13 + bcrypt 5.0 (auth)
- pydantic 2 / pydantic-settings 2 (config & schemas)
- pytest 9.1 (test suite)

**Frontend / Widget:** No build tooling anywhere in the project.
- Admin Dashboard (`static/dashboard/index.html`, 1443 lines): React 18 (UMD) + ReactDOM + Babel Standalone (in-browser JSX transpile) + Tailwind CDN (`cdn.tailwindcss.com`) + `marked.js` + `DOMPurify`. Single self-contained HTML file.
- Chat iframe (`static/chat/index.html`, 458 lines): similarly a self-contained HTML app served by the backend, consumed inside the widget's sandboxed iframe.
- `widget/widget.js` (217 lines, also at `static/widget.js`): dependency-free vanilla JS embed loader — injects launcher button + iframe, exposes `window.RAGChatWidget`.

**Infra:** `docker-compose.yml` defines only Postgres (`pgvector/pgvector:pg16`) and Redis (`redis:7-alpine`) as containers. Backend, Celery worker, and frontend all run natively on the host (Windows-oriented: `start_dev.ps1`/`start_dev.bat`, Celery run with `-P solo`).

---

## 3. DATABASE

- **Technology:** PostgreSQL (via `pgvector/pgvector:pg16` Docker image).
- **Extension:** `vector` (pgvector), created automatically in `alembic/env.py` (`CREATE EXTENSION IF NOT EXISTS vector;`) before migrations run — not embedded in the versioned migration itself.
- **Migration state:** exactly one Alembic revision (`3f9399d049cb_create_initial_models.py`) creates the entire schema. No later migrations exist.

**Tables / models** (`app/db/models/`):

| Table | Key columns | Notes |
|---|---|---|
| `users` | `id` (str uuid PK), `email` (unique, indexed), `password_hash`, `created_at`, `updated_at` | 1 user → many bots (cascade delete) |
| `bots` | `id` (PK, `bot_<12 hex>`), `user_id` (FK→users, indexed, CASCADE), `name`, `website_url`, `status` (indexed; PENDING/CRAWLING/PROCESSING/INDEXING*/READY/FAILED), timestamps | **Core tenant-isolation boundary.** *Note: "INDEXING" is documented in the status enum comment but the pipeline code never actually sets that value — it goes PENDING→CRAWLING→PROCESSING→READY/FAILED.* |
| `brand_settings` | `bot_id` (PK+FK, 1:1), `company_name`, `logo_url`, `favicon_url`, `primary_color`, `secondary_color`, `background_color`, `text_color`, `font_family`, `position` | Auto-enriched post-crawl from crawled HTML (og:site_name, logo heuristics, dominant color, live CTA color via Playwright) |
| `crawl_jobs` | `id`, `bot_id` (FK, indexed), `status` (indexed; PENDING/RUNNING/COMPLETED/FAILED), `total_pages`, `processed_pages`, `failed_pages`, `started_at`, `completed_at` | One row per crawl trigger |
| `pages` | `id`, `bot_id` (FK, indexed), `url`, `title`, `content` (Text), `content_hash` (indexed), `crawl_status`, timestamps | Raw+cleaned per-URL content |
| `documents` | `id`, `bot_id` (FK, indexed), `page_id` (FK→pages, SET NULL, indexed), `type` (`page`/`canonical_markdown`), `content`, `markdown_content`, `source_url`, `content_hash`, timestamps | Canonical `website.md` stored as `type='canonical_markdown'`, one per bot (upserted) |
| `chunks` | `id`, `bot_id` (FK, indexed), `page_id` (FK, SET NULL, indexed), `content` (Text), `embedding` (`pgvector.Vector()`, **unbounded/dynamic dimension** — no fixed size declared), `chunk_index`, `chunk_metadata` (JSONB, column name `metadata`), `created_at` | **Retrieval unit; must always be filtered by `bot_id`.** No vector index (ivfflat/hnsw) defined — cosine search is a full sequential scan (`<=>` operator) per bot. |
| `assets` | `id`, `bot_id` (FK, indexed), `page_id` (FK, SET NULL, indexed), `type`, `source_url`, `storage_url`, `asset_metadata` (JSONB) | Model exists; **not populated anywhere in the pipeline** — no code writes `Asset` rows. Effectively unused/dead table today. |
| `conversations` | `id`, `bot_id` (FK, indexed), `session_id` (indexed), `created_at` | Session-scoped |
| `messages` | `id`, `conversation_id` (FK, indexed), `role`, `content` (Text), `created_at` | Turn-by-turn transcript |

**Relationships:** standard 1:N via SQLAlchemy `relationship()`/`back_populates`, all with `cascade="all, delete-orphan"` from `Bot`/`User` downward — deleting a `Bot` cascades to jobs, pages, documents, chunks, assets, brand_settings, conversations→messages. Deleting a `User` cascades to all their bots and everything beneath.

**Tenant isolation logic:** every content-bearing table carries an explicit `bot_id` column; every service/route query filters `WHERE bot_id = :bot_id`. Ownership is enforced once, at the HTTP boundary, via `get_current_bot` (see §4), and the invariant is re-stated as a docstring/comment in nearly every model and query (`VectorRetriever`, `indexing.py`, etc.) — a deliberate, consistently-applied convention rather than incidental.

**Indexes:** `users.email` (unique), `bots.user_id`, `bots.status`, `crawl_jobs.bot_id`, `crawl_jobs.status`, `pages.bot_id`, `pages.content_hash`, `documents.bot_id`, `documents.page_id`, `chunks.bot_id`, `chunks.page_id`, `assets.bot_id`, `assets.page_id`, `conversations.bot_id`, `conversations.session_id`, `messages.conversation_id`. No composite/vector indexes.

---

## 4. AUTHENTICATION

- **Signup:** `POST /api/auth/register` (`app/api/routes/auth.py` → `AuthService.register_user`). Email normalized (`strip().lower()`), uniqueness checked, password bcrypt-hashed (`app/auth/security.py`, `bcrypt.gensalt()`), `User` row created. Password minimum length 6 (Pydantic `Field(min_length=6)`), no other complexity rule.
- **Login:** `POST /api/auth/login` → `AuthService.authenticate_user` looks up by normalized email, `bcrypt.checkpw`, issues JWT via `create_access_token`.
- **Password handling:** bcrypt only, industry-standard, no plaintext storage anywhere observed.
- **Sessions/JWT:** stateless JWT (`PyJWT`), `HS256`, secret = `settings.jwt_secret_key` (defaults to a **hardcoded dev value** `"rag-chatbot-dev-secret-key-32-chars-min-change-prod"` if not overridden by env — **not set in the provided `.env`/`.env.example`**, so the dev default is what's currently active). Expiry 24h (`jwt_access_token_expire_minutes = 60*24`). Claims: `sub` (user id), `iat`, `exp`. No refresh-token mechanism.
- **OTP / email verification:** **NOT IMPLEMENTED.** No email-sending code, no OTP model/table, no verification-status column on `users`, no mention outside doc prose. Registration immediately creates an active, usable account.
- **Authorization / ownership:** `get_current_user` (`api/dependencies.py`) validates the Bearer JWT and loads the `User`; **never trusts a client-supplied user id**. `get_current_bot` additionally loads the `Bot` by path `bot_id` and 404s (not 403 — deliberately non-leaking) if `bot.user_id != current_user.id`. All owner-only routes depend on `get_current_bot`.
- **Public/unauthenticated surface (by design):** `POST /api/bots/{bot_id}/chat`, `POST /api/bots/{bot_id}/chat/stream`, `GET /api/bots/{bot_id}/widget-config`, `GET /widget/chat`, `GET /static/*` — these are meant to be called by the embeddable widget from any third-party site and require no auth, only a valid `bot_id` and (for chat) `bot.status in (READY, PROCESSING)`.
- CORS is currently wide open (`allow_origins=["*"]`, `allow_credentials=True`) in `main.py` — acceptable for the public widget endpoints, but also exposes the authenticated dashboard endpoints to any origin.

---

## 5. CRAWLER / INGESTION PIPELINE

Full flow, file-by-file:

1. **Trigger** — `POST /api/bots/{bot_id}/crawl` (`api/routes/crawl.py`). Creates a `CrawlJob`, sets `bot.status="CRAWLING"`, then pings Celery (`celery_app.control.inspect().ping()`, 0.3s timeout); if a worker responds, dispatches `start_crawl_task.delay(...)`; **otherwise transparently falls back** to `FastAPI BackgroundTasks.add_task(run_crawl_pipeline, ...)`, so the pipeline runs even with no Celery worker online.
2. **Page discovery** — `app/crawler/discovery.py`: `normalize_url` (strip fragments/tracking params/trailing slash), `is_same_domain`, `is_crawlable_page` (scheme + domain + extension filter), `extract_links` (BeautifulSoup anchor extraction + `urljoin`).
3. **Crawling** — `app/crawler/crawler.py` (`WebCrawler.crawl_site`): concurrent BFS with `ThreadPoolExecutor(max_workers=5)`, `deque` frontier, `max_pages` (default 60, capped 1–100 via `CrawlTriggerRequest`) and `max_depth=3` bounds. Each URL: `fetch_static` (httpx GET) first; if the extracted text is short (<150 chars) and the page looks like an SPA shell (React/Next/Vite markers) or has zero discovered links, falls back to `fetch_dynamic` (Playwright headless Chromium). SSRF check (`app/crawler/ssrf.py::is_safe_url`) is applied both to the crawl root and to every fetch (`fetch_static`/`fetch_dynamic`) — blocks non-http(s) schemes, localhost/loopback/link-local/private/multicast/reserved IPs, and cloud metadata hosts (`169.254.169.254`, `metadata.google.internal`), with DNS-resolution-time re-checking to defend against DNS rebinding.
4. **Extraction/cleaning** — `app/extraction/extractor.py` (`ContentExtractor.extract`): title/site-name (OG tags → `<title>` → `<h1>`), headings, favicon, theme-color, image inventory with logo classification heuristics, structured contact/address/phone extraction from footer/contact sections, boilerplate stripping (`nav/script/style/iframe/svg/aside/footer` + cookie/consent/ad selectors), block-level text concatenation, SHA-256 content hash. Each crawled page persisted incrementally via the `on_page_crawled` callback in `crawl_tasks.py` → upserted into `pages` (keyed by `bot_id`+`url`).
5. **Documents / canonical Markdown** — `app/knowledge/markdown.py` (`CanonicalMarkdownGenerator.generate`): assembles all `SUCCESS`-status `Page` rows for the bot into one `website.md`-style document (header + per-page YAML-fenced metadata block + cleaned text), computes its own hash, and upserts into `documents` as `type="canonical_markdown"`. An optional (currently unused/unwired) `normalize_with_llm` hook exists for future LLM-based cleanup.
6. **Chunking** — `app/knowledge/chunking.py` (`SemanticChunker`): paragraph-based, heading-aware chunking of each `Page.content` (not of the assembled canonical doc) — target 700 chars, min 80, 80-char overlap for oversized paragraphs, tracks `section` (last seen markdown heading) and per-chunk metadata (`source_url`, `page_title`, `section`, `chunk_index`).
7. **Embeddings** — `app/embeddings/service.py` (`EmbeddingService.embed_texts`): provider-selectable (`fastembed` default / `mock` / `openai` / `gemini`), FastEmbed loads `BAAI/bge-small-en-v1.5` locally via ONNX (lazy singleton).
8. **Vector storage** — `app/knowledge/indexing.py` (`run_knowledge_indexing_pipeline`): atomically deletes all existing `Chunk` rows for the bot, bulk-inserts new `Chunk` rows (content + `pgvector` embedding + metadata), then sets `bot.status="READY"`.
9. **Chaining** — `run_crawl_pipeline` (`app/tasks/crawl_tasks.py`) calls `auto_enrich_bot_branding` (heuristic company/logo/color detection) then directly calls `run_knowledge_indexing_pipeline` at the end — crawl and indexing are one continuous synchronous pipeline (whether run inside a Celery task or a BackgroundTask), not two independently user-triggered steps in normal operation (the `/index` endpoint exists for manual re-indexing too).

---

## 6. CELERY / REDIS

- **Config** — `app/tasks/celery_app.py`: `Celery("rag_chatbot", broker=redis://…/0, backend=redis://…/0)`, JSON serialization, UTC timezone, `task_track_started=True`. Only `app.tasks.crawl_tasks` is registered via `include=[...]`.
- **Broker/result backend:** same Redis instance/DB (index 0) for both.
- **Tasks:** exactly one registered task — `start_crawl_task` (`bind=True`, name `app.tasks.crawl_tasks.start_crawl_task`) — a thin wrapper that calls the plain function `run_crawl_pipeline(bot_id, job_id, max_pages)`.
- **Chains/dependencies:** no Celery `chain()`/`chord()`/`group()` — everything (crawl → branding enrichment → indexing) happens **inside** `run_crawl_pipeline` as sequential Python calls in a single task/thread, not as separate Celery tasks. There is no dedicated `index_bot_task`; indexing is only invoked as a plain function call (from inside the crawl pipeline, or synchronously inline in the `/index` HTTP route).
- **Async execution model:** effectively **optional** — the presence of a live worker is auto-detected per-request (`celery_app.control.inspect().ping()`); if none is found, `run_crawl_pipeline` runs synchronously inside a FastAPI `BackgroundTasks` callback on the API process itself. This is a deliberate resilience feature (documented in the README as "Automatic Failover") but means the "Celery" pipeline is not guaranteed to actually execute via Celery.
- **Errors/status/progress:** progress is tracked via DB mutation, not Celery result state — `CrawlJob.total_pages`/`processed_pages` updated incrementally in the `on_page_crawled` callback (each callback commits), polled by the dashboard via `GET /crawl/status` every 3s (per README). On exception, `run_crawl_pipeline` sets `CrawlJob.status="FAILED"` and `Bot.status="FAILED"` and returns an error dict; Celery's own task failure state is not specially handled/reported to the client.

---

## 7. RAG SYSTEM

- **Embeddings** — `app/embeddings/service.py`, as in §5/§6. Query embedding uses `EmbeddingService.embed_query` (single-text wrapper around `embed_texts`), same provider as indexing by default (mismatched providers between index-time and query-time would silently break retrieval since dimensions could differ — no dimension-compatibility check exists).
- **Vector storage** — `chunks.embedding` (`pgvector.sqlalchemy.Vector()`, dimension not fixed at the SQLAlchemy/DB level — inferred from whatever the active embedding provider emits, 384-dim for the default FastEmbed model).
- **Retrieval** — `app/rag/retriever.py` (`VectorRetriever.retrieve`): embeds the query, runs `Chunk.embedding.cosine_distance(query_vector)` ordered ascending, `LIMIT top_k` (default 5), **always** filtered `WHERE bot_id = :bot_id AND embedding IS NOT NULL`. No ANN index — this is an exact/sequential scan per query (fine at MVP scale, a scaling concern noted below).
- **Metadata filtering:** only `bot_id` is enforced as a hard filter; `score_threshold` is supported as an optional post-hoc cutoff but is not used by the chat service (`top_k=5` with no threshold is passed). Per-chunk metadata (`source_url`, `page_title`, `section`) is carried through for citations but not used to further filter retrieval.
- **bot_id isolation** — enforced at exactly one point, the `WHERE Chunk.bot_id == bot_id` clause in `VectorRetriever.retrieve`; called from `ChatService` with `bot.id` taken from the authenticated/owned or publicly-looked-up `Bot` row, never from client input directly.
- **Prompt construction** — `app/rag/prompt.py` (`RAGPromptBuilder`):
  - `build_system_prompt`: establishes assistant identity as "the official AI assistant for {company}", instructs it to answer broad/ambiguous questions about the company as a whole, and contains an explicit prompt-injection defense clause (treat `<untrusted_website_reference_data>` as passive data, ignore embedded instructions, ground answers only in supplied data, admit when data is insufficient).
  - `build_user_prompt`: wraps retrieved chunks (with source URL/title/section) inside `<untrusted_website_reference_data>…</untrusted_website_reference_data>` delimiters, appends up to the last 6 turns of conversation history, then the current question.
- **LLM response generation** — `app/chat/service.py` (`ChatService`): retrieves chunks → builds prompts → `get_llm_client(provider)` (`app/llm/client.py`) → `generate_response`. Supports Groq (default provider, OpenAI-compatible endpoint), Gemini, Claude (Anthropic Messages API), OpenAI, and a rule-based `MockLLMClient` that extracts facts straight out of the untrusted-reference block via regex when no answer engine/API key is available — this is also the **automatic fallback** whenever the configured provider's API key is unset, so the system is always runnable offline/keyless in a degraded-but-functional mode.
- **"Streaming"** (`chat/service.py::stream_message`, `POST /chat/stream`): the full LLM answer is generated **non-streaming** first, then re-emitted word-by-word over SSE with a fixed `asyncio.sleep(0.015)` between tokens purely for UI typing effect — **not** true token-by-token provider streaming.
- **Query contextualization** — `ChatService._prepare_retrieval_query_and_company`: detects short/generic/pronoun-heavy queries ("it", "this", "what is", etc.) and prepends the resolved clean company name to the retrieval query before embedding, to bias retrieval toward company-overview chunks.
- Key files: `app/embeddings/service.py`, `app/rag/retriever.py`, `app/rag/prompt.py`, `app/llm/client.py`, `app/chat/service.py`.

---

## 8. FRONTEND

Two independent, no-build, single-HTML-file React apps served directly by FastAPI (`app/api/routes/widget.py`), plus a legacy demo page.

- **Admin Dashboard** (`GET /dashboard` → `backend/static/dashboard/index.html`, byte-identical to `frontend/index.html`): React 18 + Babel Standalone loaded from CDN, Tailwind CDN, `marked`+`DOMPurify` for rendering the canonical Markdown viewer. All state client-side; talks to the backend exclusively via `fetch()` calls to `window.location.origin` (`API_BASE`) with `Authorization: Bearer <jwt>` from `localStorage`/state. Screens (inferred from fetch calls): login/register, bot list/create, crawl trigger + live polling of `/crawl/status`, page list, canonical markdown viewer, chunk browser, branding editor (`PUT /branding`), embed-snippet generator, conversation/transcript viewer.
- **Chat iframe app** (`GET /widget/chat` → `backend/static/chat/index.html`): standalone HTML app parameterized via query string (`bot_id`, `api_host`) injected by `widget.js`; fetches `widget-config` for branding/greeting, then calls `POST /api/bots/{bot_id}/chat/stream` and consumes the SSE stream to render the conversation. Uses `postMessage` (`CLOSE_CHAT`/`OPEN_CHAT`) to talk to the parent `widget.js` for open/close control.
- **Legacy/demo:** `backend/static/demo.html` — a sample "Acme Cloud" host page referenced by the README as the widget live-demo target.

---

## 9. EMBEDDABLE WIDGET

- **Loader script** — `widget/widget.js` (source) / `backend/static/widget.js` (served, identical): a self-executing, dependency-free vanilla-JS IIFE. Reads `data-bot-id` (required) and optional `data-api-host` off its own `<script>` tag; guards against double-injection (`window.__RAG_WIDGET_LOADED__`). Fetches `GET /api/bots/{bot_id}/widget-config` for branding (falls back to hardcoded defaults on failure), then injects: a floating launcher button (fixed-position, brand-colored, responsive mobile full-screen breakpoint), a container `<div>`, and a **sandboxed `<iframe>`** pointed at `GET /widget/chat?bot_id=…&api_host=…` — the actual chat UI lives entirely inside that iframe, isolating third-party host page CSS/JS from the chat widget's DOM. Exposes `window.RAGChatWidget.{open, close, toggle, isOpen, botId}` for host-page programmatic control, and listens for `postMessage` events from the iframe to toggle visibility.
- **Test harness:** `widget/test_embed.html` — a minimal standalone HTML page that embeds the widget script for manual/local testing.
- No separate widget backend endpoints beyond `widget-config` and `/widget/chat` (both public, unauthenticated, in `app/api/routes/widget.py`).

---

## 10. TESTING

`backend/tests/` — 7 files, **24** `def test_*` functions (README states "27 automated tests"; the discrepancy is likely stale documentation or a differently-counted subset — verified count in the current tree is 24). Uses pytest + FastAPI `TestClient` + a `db`/`db_session` fixture (not shown in this audit's scope beyond usage, presumably in an untracked `conftest.py`, not separately enumerated here since fixtures weren't part of the requested file list — **note:** worth locating `conftest.py` before modifying tests).

| File | Verifies |
|---|---|
| `test_models.py` | User/Bot creation, full model hierarchy + cascade deletes, tenant-isolation invariant at the ORM level |
| `test_auth_and_bots.py` | Registration/login flow, bot CRUD + multi-tenant ownership enforcement |
| `test_crawler_and_tasks.py` | SSRF protection, URL discovery/normalization, content extraction/boilerplate removal, crawl pipeline + API (with `monkeypatch`) |
| `test_knowledge_and_indexing.py` | Canonical Markdown generation, semantic chunker, embedding service, LLM client pluggability, full indexing pipeline + multi-tenant isolation |
| `test_rag_and_chat.py` | RAG prompt builder untrusted-data isolation, prompt-injection-defense quarantine, vector retriever + multi-tenant isolation, multi-turn chat API, SSE streaming endpoint |
| `test_dashboard_and_branding.py` | Dashboard route serves the SPA, branding GET/PUT, branding tenant isolation |
| `test_widget.py` | Widget-config with custom/default branding, 404 on unknown bot, static `widget.js` served, standalone chat iframe served |

Coverage is broad across every layer (auth, crawl, extraction, chunking, embeddings, retrieval, prompt-injection defense, chat, SSE, widget, branding, tenant isolation) but **shallow per feature** — no coverage found for: OTP/email flows (none exist), Celery-actually-dispatched execution (tests appear to exercise the pipeline function directly / via monkeypatch rather than a live Celery worker+broker), asset/screenshot storage (feature unused), pagination edge cases, or JWT expiry/tampering paths.

---

## 11. ENVIRONMENT / RUNNING THE PROJECT

- **Docker services** (`docker-compose.yml`): `postgres` (`pgvector/pgvector:pg16`, port 5432, container `rag_postgres`) and `redis` (`redis:7-alpine`, port 6379, container `rag_redis`). Only infra is containerized.
- **Backend:** run natively — `cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload` (Windows-oriented paths/venv in README; a `.venv` directory and `.pytest_cache` are present in the archive, i.e. a Windows virtualenv was committed into the zip — **should be excluded when reusing this repo**, see Risks).
- **Celery worker:** `cd backend && .venv\Scripts\python.exe -m celery -A app.tasks.celery_app.celery_app worker --loglevel=info -P solo` (`-P solo` required on Windows; execution is optional at runtime due to the BackgroundTasks fallback described in §6).
- **Frontend:** no separate dev server — served directly by FastAPI at `/dashboard`, `/widget/chat`, `/static/*`.
- **One-click scripts:** `start_dev.ps1` / `start_dev.bat` at repo root, launch Docker check + both processes in separate console windows.
- **Ports:** API/dashboard/docs on `:8000`; Postgres `:5432`; Redis `:6379`.
- **Required environment variables** (`app/config.py`, backed by `.env` at repo root, `pydantic-settings`):

  | Variable | Required? | Purpose |
  |---|---|---|
  | `POSTGRES_DB` | yes | DB name |
  | `POSTGRES_USER` | yes | DB user |
  | `POSTGRES_PASSWORD` | yes | DB password |
  | `POSTGRES_HOST` | no (default `localhost`) | DB host |
  | `POSTGRES_PORT` | no (default `5432`) | DB port |
  | `REDIS_HOST` | no (default `localhost`) | Redis host |
  | `REDIS_PORT` | no (default `6379`) | Redis port |
  | `JWT_SECRET_KEY` | no, but **should be set in prod** (insecure hardcoded default otherwise) | JWT signing |
  | `JWT_ALGORITHM` | no (default `HS256`) | JWT alg |
  | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | no (default 1440) | Token TTL |
  | `EMBEDDING_PROVIDER` | no (default `fastembed`) | Embedding backend selector |
  | `EMBEDDING_MODEL` | no (default `BAAI/bge-small-en-v1.5`) | FastEmbed model name / OpenAI embedding model override |
  | `OPENAI_API_KEY` | no (needed only if using OpenAI embeddings or LLM) | |
  | `GEMINI_API_KEY` | no (needed only for Gemini embeddings/LLM) | |
  | `ANTHROPIC_API_KEY` | no (needed only for Claude LLM) | |
  | `GROQ_API_KEY` | no, but **is the default LLM provider** — without it, chat silently degrades to `MockLLMClient` | |
  | `LLM_PROVIDER` | no (default `groq`) | Generative LLM selector |
  | `LLM_MODEL` | no (default `openai/gpt-oss-120b`) | Groq model name |

  The repository's `.env` present in the zip only sets the same variable **names** as `.env.example` (values not reproduced here per instructions); no additional/undocumented variables were found.

---

## 12. REUSABLE COMPONENTS

| Component | Classification | Notes |
|---|---|---|
| Auth (`auth/`, `api/dependencies.py`) | **REUSE DIRECTLY** | Generic JWT+bcrypt user auth, no chatbot-specific logic |
| `User`/`Bot` core models & multi-tenant pattern | **REUSE WITH MODIFICATIONS** | `Bot` concept generalizes cleanly to "Campaign"/"Project"; keep the `user_id`-owns-`X` pattern, rename/extend fields |
| SSRF guard (`crawler/ssrf.py`) | **REUSE DIRECTLY** | Generic URL-safety validator, no domain coupling |
| URL discovery/normalization (`crawler/discovery.py`) | **REUSE DIRECTLY** | Generic |
| Crawler engine (`crawler/crawler.py`) | **REUSE DIRECTLY** | Generic BFS crawler with SSRF + Playwright fallback; needed as-is for "Website URL → Crawl" |
| Content extractor (`extraction/extractor.py`) | **REUSE WITH MODIFICATIONS** | Text/contact extraction generically useful; logo/theme-color/brand-heuristic parts are chatbot-widget-specific and can be dropped or kept optionally |
| Semantic chunker (`knowledge/chunking.py`) | **REUSE DIRECTLY** | Generic text chunking |
| Canonical Markdown generator (`knowledge/markdown.py`) | **REUSE DIRECTLY** | Generic knowledge-assembly step |
| Embedding service (`embeddings/service.py`) | **REUSE DIRECTLY** | Provider-agnostic; works for any RAG use case |
| Indexing pipeline (`knowledge/indexing.py`) | **REUSE WITH MODIFICATIONS** | Logic generalizes from `bot_id` to any owning entity id; keep structure |
| Vector retriever (`rag/retriever.py`) | **REUSE WITH MODIFICATIONS** | Same — rename `bot_id` scoping concept |
| DB models (`Page`, `Document`, `Chunk`) | **REUSE DIRECTLY** | Rename FK column conceptually if desired, structure is sound |
| `CrawlJob` model + crawl task orchestration | **REUSE DIRECTLY** | Generic async job-tracking pattern |
| Celery app + BackgroundTasks fallback pattern | **REUSE DIRECTLY** | Generic resilience pattern, valuable to keep |
| LLM client factory (`llm/client.py`) | **REUSE DIRECTLY** | Generic multi-provider LLM abstraction; prompts inside it are chatbot-specific and get replaced |
| RAG prompt builder (`rag/prompt.py`) | **REPLACE** | Chatbot Q&A persona and untrusted-data framing must become an email-generation persona/prompt; the injection-defense *pattern* (quarantine untrusted scraped data) should be **kept** and reapplied |
| `Conversation`/`Message` models + `ChatService` | **NOT RELEVANT** | Chat-session concept doesn't map to an email campaigner; email generation is single-shot per contact, not multi-turn |
| Widget loader (`widget/widget.js`) | **NOT RELEVANT** | Embeddable chat UI has no equivalent in an email campaigner |
| Chat iframe app (`static/chat/`) | **NOT RELEVANT** | Same |
| `BrandSettings` model + branding auto-enrichment (`auto_enrich_bot_branding`, dominant-color/CTA-color detection) | **NOT RELEVANT** (or **REUSE WITH MODIFICATIONS** if you want branded email templates) | Heavy, widget-display-specific heuristics; could be trimmed to just company-name/logo extraction if email templates want branding |
| Admin Dashboard (`static/dashboard/`) | **REPLACE** | UI shell (React CDN + Tailwind, auth+API-calling pattern) is reusable scaffolding; every screen's content is chatbot-specific and must be rebuilt for contacts/campaigns/email review |
| `Asset` model | **NOT RELEVANT** | Already unused in current project; skip |

---

## 13. CHATBOT-SPECIFIC COMPONENTS

Everything below exists *only* because this is a website chatbot, and is a candidate for removal/replacement in an email-campaigner pivot:

- `Conversation` / `Message` models and all of `app/chat/` (multi-turn session state, SSE token-streaming simulation).
- `app/api/routes/chat.py` (`/chat`, `/chat/stream`, `/conversations*`).
- `app/rag/prompt.py`'s system prompt persona ("You are the official AI assistant for…") and the "answer broad company questions" contextualization logic in `ChatService._prepare_retrieval_query_and_company`.
- `BrandSettings` model + `auto_enrich_bot_branding` + `detect_live_cta_color` + `extract_dominant_color_from_image` (Playwright/Pillow-based visual branding detection) — built purely to theme a chat widget bubble.
- `widget/widget.js`, `backend/static/widget.js`, `backend/static/chat/index.html`, `backend/static/demo.html`, `widget/test_embed.html` — the entire embeddable-iframe delivery mechanism.
- `app/api/routes/widget.py`'s `widget-config` and `/widget/chat` endpoints.
- The `bot.status` "READY for chat" gating logic in `chat.py` routes.
- Dashboard screens for: crawl status polling for chat readiness, embed-snippet generator, conversation/transcript viewer, branding color pickers.
- `Bot.name` as a "bot display name" concept (vs. e.g. a "Campaign name").

---

## 14. POSSIBLE NEW PROJECT DESIGN

Mapping the requested flow — `User → Signup/Login → OTP verification → Connect HubSpot or mock contacts → Website URL → Crawl → Chunk → Embed → Vector DB → Generate personalized promotional emails → Campaign → Send emails` — onto what exists:

1. **Signup/Login** — reuse `auth/` wholesale (`register`, `login`, `get_current_user`). No changes needed to reach a working account system.
2. **OTP verification** — **does not exist**; would need: an OTP/verification-code model (or reuse a field on `User`, e.g. `is_verified`, `otp_code`, `otp_expires_at`), an email-sending integration (none present — no SMTP/SES/SendGrid client anywhere in the repo), and a `/api/auth/verify-otp` route + a gate on login/protected routes until verified. Everything here is new work.
3. **Connect HubSpot or mock contacts** — **does not exist**. Nearest analog is the `Bot` entity (an owned resource tied to `user_id`) — a new `Contact`/`ContactList` model (or `Campaign` owning many `Contact` rows) would follow the exact same `user_id`-ownership + `get_current_*` dependency pattern used for `Bot`. No HubSpot client exists; would be new integration work (OAuth + HubSpot Contacts API), with a "mock contacts" (CSV upload or hardcoded fixture) path as the fast MVP substitute.
4. **Website URL → Crawl → Chunk → Embed → Vector DB** — this is the existing pipeline almost unchanged: `Bot.website_url` → `WebCrawler.crawl_site` → `Page` rows → `SemanticChunker` → `EmbeddingService` → `Chunk` rows in pgvector, scoped by whatever entity replaces `bot_id` (could keep `Bot` as-is and just repurpose it as "the campaign's source website", or rename conceptually to `Campaign`). The `/crawl` and `/index` routes and the Celery/BackgroundTasks dual-dispatch pattern transfer directly.
5. **Generate personalized promotional emails** — reuse `VectorRetriever` (retrieve company knowledge chunks) + `get_llm_client` (any provider) exactly as-is; **replace** `RAGPromptBuilder` with a new prompt builder whose system prompt establishes an email-copywriting persona and whose user prompt combines (a) retrieved website/company knowledge chunks (same untrusted-data quarantine pattern, reused for safety) with (b) per-contact personalization fields (name, company, role — from the `Contact` model). Output shape changes from a chat answer to a structured email (subject + body), so a new Pydantic schema (`EmailDraft{subject, body}`) and possibly structured-output prompting is needed — this is new work built on reused retrieval/LLM plumbing.
6. **Campaign** — new concept: a `Campaign` entity (could subsume today's `Bot`, or reference it) associating a website/knowledge-base with a batch of `Contact`s and generated `EmailDraft`s, plus a status lifecycle analogous to `Bot.status` (`DRAFTING`→`READY`→`SENDING`→`SENT`). This is new modeling work, but the ownership/status-tracking *pattern* is a direct copy of `Bot`+`CrawlJob`.
7. **Send emails** — **does not exist at all**. No SMTP/transactional-email client anywhere in the repo. New integration required (e.g. SendGrid/SES/SMTP), plus a Celery task (`send_campaign_emails_task`) following the exact dispatch/fallback pattern already used for crawling.

---

## 15. GAPS FOR THE NEW PROJECT

Capabilities the existing repo does **not** provide that the email campaigner requires:

1. **OTP / email verification** — no model, no email-sending capability, no verification gate at all.
2. **Outbound transactional email sending** — no SMTP/SendGrid/SES client, no email-delivery Celery task, no bounce/delivery-status tracking.
3. **CRM / contacts integration** — no HubSpot (or any CRM) OAuth/API client; no `Contact` model; no CSV/mock-contact ingestion endpoint.
4. **Campaign entity & lifecycle** — no model representing a batch send, its recipients, and per-recipient generated content/send-status.
5. **Structured/templated email generation** — the current RAG system produces conversational chat answers, not subject+body email drafts; no email-template rendering (e.g. Jinja2/MJML) exists.
6. **Per-contact personalization merge** — no mechanism to merge retrieved knowledge with per-contact fields (name, role, company) into a prompt; `RAGPromptBuilder` has no concept of a "recipient."
7. **Send scheduling / rate limiting / unsubscribe handling** — none of this exists (expected, since it's out of scope for a chatbot).
8. **Any notion of "review before send" workflow / approval UI** — the dashboard has no equivalent of a draft-review screen.
9. **Vector index tuning at scale** — not really an MVP gap, but noted: no ANN index (ivfflat/hnsw) on `chunks.embedding`, fine at demo scale but would need addressing before real production volume regardless of which app is built.

---

## 16. RECOMMENDED MVP (≈3 hours)

Goal: demonstrably working end-to-end flow, prioritizing breadth-of-flow over polish. Suggested cut:

1. **Reuse unchanged:** `auth/` (signup/login/JWT), `crawler/` + `extraction/` + `knowledge/chunking.py` + `knowledge/markdown.py` + `embeddings/service.py` + `rag/retriever.py` (rename nothing yet — keep `Bot` as the "campaign source" entity to avoid a rename pass), `llm/client.py`, Celery/BackgroundTasks dispatch pattern, DB session/engine setup.
2. **Skip/stub OTP:** implement as a **fixed dummy code** (e.g. always `"000000"`) or fully skip and just add an `is_verified=True` default — real email delivery is not feasible to stand up correctly in 3 hours; call this out explicitly as a known MVP shortcut in the demo/video.
3. **Mock contacts only:** skip HubSpot OAuth entirely. Add one new small model `Contact(id, user_id or campaign_id, name, email, role, company)` and a `POST /api/contacts` (or CSV upload) endpoint — reuses the exact `user_id`-ownership pattern from `bots.py`.
4. **Reuse the crawl→index pipeline as-is** against `Bot.website_url` (or rename `Bot`→`Campaign` only if time allows; functionally optional for a demo).
5. **New, minimal:** one `EmailPromptBuilder` (copy `RAGPromptBuilder`'s structure, swap persona + add contact-merge fields) + one route `POST /api/bots/{bot_id}/contacts/{contact_id}/generate-email` returning `{subject, body}` using existing retriever + existing `get_llm_client`. This is the one truly new piece of core logic and is a small, contained change (a few hours' work reduces to well under one hour given how much plumbing is reused).
6. **"Send"**: for a 3-hour MVP, **fake the send** — log the generated email to a `sent_emails` table (or just return it with `status: "sent"` in the response) rather than integrating real SMTP. This satisfies "demonstrates the instructor's requested functionality end-to-end" without needing a real email provider or worrying about deliverability/keys during the demo.
7. **UI:** the absolute minimum — either reuse/trim the existing dashboard's bot-creation + crawl-trigger screens and bolt on one new "Contacts" tab + "Generate Email" button showing the draft, or skip a dashboard entirely and drive the whole demo through `/docs` (Swagger UI) plus a single flat HTML page for the "wow" moment (generated email rendering).

This ordering front-loads everything that's a pure copy/paste (crawl→index→retrieve→LLM) and isolates the only genuinely new logic (prompt + contact merge + fake-send) into the smallest possible surface area.

---

## 17. EXACT FILE MAP

**Reuse unchanged (copy as-is):**
```
backend/app/auth/                         (all files)
backend/app/api/dependencies.py
backend/app/crawler/                      (all files)
backend/app/extraction/extractor.py
backend/app/knowledge/chunking.py
backend/app/knowledge/markdown.py
backend/app/embeddings/service.py
backend/app/rag/retriever.py
backend/app/llm/client.py
backend/app/tasks/celery_app.py
backend/app/db/database.py
backend/app/config.py                     (extend, don't rewrite)
backend/app/main.py                       (extend router includes)
docker-compose.yml
backend/alembic/env.py                    (pgvector extension bootstrap)
backend/requirements.txt / requirements.txt
```

**Modify:**
```
backend/app/db/models/bot.py              → optionally rename concept to Campaign, or keep as-is
backend/app/db/models/__init__.py         → add new Contact/Campaign models to exports
backend/app/api/routes/bots.py            → strip branding endpoints if BrandSettings dropped
backend/app/api/routes/auth.py            → add OTP verify route (or stub)
backend/app/auth/schemas.py               → add OTP fields to register/verify schemas
backend/app/db/models/user.py             → add is_verified / otp fields (or stub true)
backend/app/knowledge/indexing.py         → generalize bot_id references if entity renamed
backend/app/rag/schemas.py                → extend for email-draft output shape
backend/app/tasks/crawl_tasks.py          → drop auto_enrich_bot_branding call if branding is dropped
```

**Create:**
```
backend/app/db/models/contact.py          Contact model
backend/app/contacts/schemas.py           Contact request/response schemas
backend/app/contacts/service.py           Contact CRUD
backend/app/api/routes/contacts.py        Contact endpoints (+ optional CSV import)
backend/app/rag/email_prompt.py           EmailPromptBuilder (persona + contact merge)
backend/app/api/routes/email.py           /generate-email route
backend/app/db/models/email_draft.py      (MVP) EmailDraft / sent-log model
backend/alembic/versions/xxxx_add_contacts_and_emails.py   New migration
```

**Ignore / remove (chatbot-only, not needed for email campaigner):**
```
backend/app/chat/                          (all files)
backend/app/api/routes/chat.py
backend/app/api/routes/widget.py
backend/app/db/models/chat.py
backend/app/db/models/branding.py          (unless keeping brand-styled emails)
backend/app/tasks/crawl_tasks.py::auto_enrich_bot_branding / detect_live_cta_color / extract_dominant_color_from_image
backend/app/rag/prompt.py                  (replaced by email_prompt.py; keep only as a reference for the injection-defense pattern)
backend/static/dashboard/                  (rebuild or heavily trim)
backend/static/chat/
backend/static/widget.js / widget/*
backend/static/demo.html
frontend/index.html                        (dev-source dup of dashboard)
backend/app/db/models/knowledge.py::Asset  (already unused)
```

---

## 18. RISKS / IMPORTANT NOTES

1. **Committed virtualenv/cache dirs**: the zip contains `backend/.venv/`, `backend/.pytest_cache/`, and `__pycache__/` directories. These should not be copied into the new project — regenerate a fresh venv and install from `requirements.txt`.
2. **`.env` is present in the archive** (not just `.env.example`) — treat as a local dev convenience, but rotate/replace all values (especially `JWT_SECRET_KEY`, if ever customized, and any provider API keys) before reuse in a new context; do not commit it.
3. **Hardcoded JWT dev secret**: if `JWT_SECRET_KEY` isn't explicitly set in `.env`, `Settings` silently falls back to a well-known string baked into `config.py`. Must be overridden for any deployment beyond local dev.
4. **CORS is fully open** (`allow_origins=["*"]`) including credentialed requests — fine for public widget endpoints, but the *same app* also serves authenticated dashboard/API routes under that policy. Worth tightening if the new project exposes more sensitive data (contacts, email content).
5. **No embedding-provider/dimension guard**: switching `EMBEDDING_PROVIDER` after chunks have already been indexed with a different provider will silently produce nonsensical similarity search results (different vector spaces / dimensions) since `chunks.embedding` has no fixed dimension constraint and no provider tag is stored per chunk. If the new project changes providers mid-build, re-index everything.
6. **No ANN vector index**: `chunks.embedding` has no ivfflat/hnsw index — cosine search is a sequential scan. Not a correctness risk, but will slow down as chunk volume grows; irrelevant at MVP/demo scale.
7. **Celery is optional, not guaranteed**: because of the auto-fallback to FastAPI `BackgroundTasks`, a developer might believe Celery is wired end-to-end and working, when in fact most local runs (if the worker isn't started) execute the whole crawl+index pipeline synchronously in-process. This is fine functionally but means "Celery" claims in docs should be read as "Celery *or* BackgroundTasks."
8. **`Asset` model is entirely dead code** today — no writer exists. Don't assume image/screenshot storage works; it's schema-only.
9. **SSE "streaming" is fake** (full answer generated first, then chunked for typing effect) — if the new project's email generation needs genuine low-latency streaming UX, this pattern won't provide it; would need real provider-side token streaming (most of the `llm/client.py` provider implementations use blocking, non-streaming HTTP calls today).
10. **Playwright/Pillow dependencies are heavy** (headless Chromium download, image processing) and are only used for branding-color detection and JS-rendering fallback — if branding is dropped for the new project, Playwright can likely be kept only for the JS-page-rendering fallback (still useful for crawling) while the Pillow-based color-extraction code can be removed to lighten the dependency footprint.
11. **Windows-oriented dev workflow**: `start_dev.ps1`/`.bat`, `-P solo` Celery flag, and `.venv\Scripts\python.exe` paths in the README all assume Windows; adjust for the new project's actual dev environment (this doesn't block reuse but affects onboarding scripts).
12. **Test count discrepancy**: README claims 27 tests across "7 milestones"; the actual tree has 24 `def test_*` functions across 7 files. Not a functional risk, just a documentation staleness note — verify test count directly rather than trusting README going forward.
13. **`bot.status` enum drift**: the model comment lists `PENDING, CRAWLING, PROCESSING, INDEXING, READY, FAILED` but the code path never actually sets `"INDEXING"` (indexing happens while status is still `"PROCESSING"`, then jumps straight to `"READY"`). If a new project's UI logic branches on status strings, don't assume `INDEXING` will ever appear.

---

# ANTIGRAVITY HANDOFF SUMMARY

**What this repo is:** A working, tested (24 pytest tests), FastAPI + Celery/Redis + PostgreSQL/pgvector RAG chatbot platform. Flow: user signs up (JWT auth, no OTP) → creates a `Bot` (website_url) → triggers `/crawl` → SSRF-safe BFS crawler (httpx + Playwright JS fallback) extracts+cleans pages → canonical `website.md` assembled → semantically chunked → embedded (FastEmbed local ONNX by default, pluggable to OpenAI/Gemini) → stored in pgvector `chunks` table, strictly scoped by `bot_id` → bot becomes `READY` → an embeddable `<script data-bot-id>` widget (sandboxed iframe) lets any website visitor chat; `POST /chat` and `/chat/stream` retrieve bot-scoped chunks via cosine similarity, build an injection-hardened prompt (`<untrusted_website_reference_data>` quarantine), and call a pluggable LLM (Groq default, falls back to a regex-based Mock if no API key is set — the whole system is runnable with zero API keys).

**Core invariant to preserve in any fork:** every content table (`pages`, `documents`, `chunks`, `assets`, `conversations`) carries `bot_id`, and every query filters on it; ownership is checked once via `get_current_bot`/`get_current_user` dependency injection, never via client-supplied identity. Keep this pattern for whatever entity (`Bot`, `Campaign`, etc.) replaces the tenant boundary.

**What's genuinely reusable as-is for a different RAG application:** `auth/`, `crawler/` (+ SSRF), `extraction/extractor.py`, `knowledge/chunking.py` + `markdown.py`, `embeddings/service.py`, `rag/retriever.py`, `llm/client.py`, the Celery-with-BackgroundTasks-fallback dispatch pattern, and the SQLAlchemy model/migration structure. This is roughly 70% of the codebase and needs zero changes to repurpose.

**What's chatbot-specific and should be dropped/replaced for a non-chat RAG app (e.g. an email campaigner):** `app/chat/` (Conversation/Message/SSE), `app/api/routes/chat.py` + `widget.py`, the entire `widget/` + `static/{chat,dashboard,widget.js,demo.html}` frontend surface, `BrandSettings` + its Playwright/Pillow-based auto-branding heuristics, and `rag/prompt.py`'s chat persona (though its untrusted-data-quarantine *pattern* should be copied into any new prompt builder).

**What does not exist at all and must be built new:** OTP/email verification, any outbound email sending (no SMTP client), any CRM/contacts integration (no HubSpot client, no `Contact` model), and any "Campaign"/batch-send concept. None of these have even placeholder code in the repo — greenfield work.

**Known gotchas before touching code:** (1) hardcoded JWT dev secret in `config.py` if `.env` doesn't override it; (2) `.venv`/`__pycache__` committed in the zip — don't reuse them; (3) Celery execution is best-effort/optional due to the BackgroundTasks fallback — don't assume a worker must be running; (4) no embedding-dimension guard — don't switch embedding providers on already-indexed data without re-indexing; (5) `Asset` model is unused/dead; (6) SSE "streaming" is simulated, not real token streaming; (7) `bot.status` never actually reaches the documented `"INDEXING"` value.

**Fastest path to a demoable new project (~3h budget):** keep `Bot`.`website_url` → crawl → chunk → embed → retrieve pipeline entirely intact; stub OTP (dummy code or skip); add one small `Contact` model + endpoint (mock/CSV, skip real HubSpot OAuth); write one new `EmailPromptBuilder` + one `/generate-email` route reusing the existing retriever and LLM client; fake the "send" step (log/return rather than real SMTP). This isolates all genuinely new work into a handful of small, additive files while reusing the majority of the existing, already-tested pipeline untouched.