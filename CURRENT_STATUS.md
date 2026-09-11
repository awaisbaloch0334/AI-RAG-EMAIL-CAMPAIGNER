# CURRENT STATUS — AI RAG Email Campaigner (formerly Embeddable RAG Chatbot)

> **Last updated:** 2026-09-10
> **Application Transition:** Successfully transitioned from chatbot to AI RAG Email Campaigner according to `NEW_AI_WORKFLOW.md`.
> **Active Status:** Milestones 1 through 7 fully implemented, verified, and passing 48/48 tests (100%).
> **Primary Flow:** User & Auth &rarr; Contacts & Audience &rarr; Website Knowledge Source &rarr; Crawl & pgvector Indexing &rarr; Campaign Creation &rarr; RAG Email Generation &rarr; Mock Dispatch & Delivery Tracking.

---


# 1. How to Read This File

There are three important project documents:

1. **`PROJECT_SPEC.md`**

   * Permanent implementation contract.
   * Defines requirements, architecture, security rules, database design, RAG flow, MVP scope, and future features.
   * If requirements conflict with this status file, `PROJECT_SPEC.md` wins.

2. **`CURRENT_STATUS.md`**

   * Living implementation checkpoint.
   * Describes what is actually completed and verified in the repository.
   * Must be updated whenever a meaningful implementation milestone is completed.

3. **`AI_HANDOFF_PROMPT.md`**

   * Instructions for AI coding agents.
   * Defines how an AI should inspect, modify, test, and continue the project.
   * It is not an independent source of product requirements.

---

# 2. Project Goal

Build an embeddable, website-specific RAG chatbot platform.

The intended flow is:

```text
Customer enters website URL
        ↓
Create Bot
        ↓
Start asynchronous Celery crawl
        ↓
Discover website pages
        ↓
Crawl static/dynamic pages
        ↓
Extract clean website content
        ↓
Extract assets/screenshots/branding
        ↓
Generate canonical website.md
        ↓
Chunk knowledge
        ↓
Generate embeddings
        ↓
Store vectors in PostgreSQL + pgvector
        ↓
Bot becomes READY
        ↓
Generate embeddable JavaScript snippet
        ↓
Customer embeds snippet
        ↓
React chatbot opens inside iframe
        ↓
User sends message
        ↓
FastAPI retrieves ONLY this bot's knowledge
        ↓
LLM generates grounded answer
```

The system is **RAG-based**.

It does NOT train or fine-tune a separate LLM for each customer.

---

# 3. Non-Negotiable Architecture Rules

## 3.1 Multi-Tenant Isolation

The isolation hierarchy is:

```text
USER
  ↓
BOT
  ↓
WEBSITE
  ↓
BOT-SCOPED KNOWLEDGE
```

Every website-derived object must be associated with `bot_id`.

This includes:

* pages
* documents
* chunks
* embeddings
* assets
* screenshots
* conversations
* retrieval results
* crawl jobs
* branding information

RAG retrieval MUST always be filtered by `bot_id`.

Never perform unrestricted global vector search.

The backend must never trust a browser-supplied `user_id` for authorization.

The backend must resolve the authenticated user and verify bot ownership.

Celery tasks must carry `bot_id` throughout the ingestion pipeline.

Required security invariant:

```text
Bot A cannot retrieve Bot B's knowledge.
Bot B cannot retrieve Bot A's knowledge.
```

This must eventually be covered by an automated test.

---

# 4. Confirmed Technology Stack

## Backend

* Python
* FastAPI
* SQLAlchemy
* psycopg

## Async Processing

* Celery
* Redis

## Database

* PostgreSQL
* pgvector

## Crawling / Extraction

* Playwright
* BeautifulSoup and/or lxml

## Frontend

* Next.js
* React
* Tailwind CSS

## Widget

* JavaScript loader
* iframe
* React chatbot application

## AI

* Configurable LLM provider
* Configurable embedding provider

## Optional Future Storage

* S3-compatible object storage
* AWS S3
* Cloudflare R2
* MinIO

---

# 5. Current Repository Structure

Current repository:

```text
embeddable-rag-chatbot/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── PROJECT_SPEC.md
├── CURRENT_STATUS.md
├── AI_HANDOFF_PROMPT.md
├── README.md
├── backend/
├── crawler/
├── frontend/
├── tests/
├── widget/
└── workers/
```

The repository should evolve toward a clean modular structure.

Preferred backend organization:

```text
backend/
└── app/
    ├── main.py
    ├── config.py
    │
    ├── api/
    │   ├── routes/
    │   │   ├── auth.py
    │   │   ├── bots.py
    │   │   ├── crawl.py
    │   │   └── chat.py
    │   └── dependencies.py
    │
    ├── auth/
    │   ├── models.py
    │   ├── schemas.py
    │   ├── service.py
    │   └── security.py
    │
    ├── bots/
    │   ├── models.py
    │   ├── schemas.py
    │   └── service.py
    │
    ├── crawler/
    ├── extraction/
    ├── branding/
    ├── knowledge/
    ├── embeddings/
    ├── rag/
    ├── chat/
    │
    ├── tasks/
    │   ├── crawl_tasks.py
    │   ├── embedding_tasks.py
    │   └── ...
    │
    └── db/
        ├── database.py
        └── models/
```

Use separation such as:

```text
Routes
  ↓
Schemas
  ↓
Services
  ↓
Models
  ↓
Database
```

Do not place the whole application inside `main.py`.

---

# 6. Environment Already Verified

## Python

Python 3.11 is installed.

Project virtual environment:

```text
backend\.venv
```

Activate from the repository:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
```

---

# 7. Dependencies Already Installed

Backend currently has:

* FastAPI
* Uvicorn
* pydantic-settings
* SQLAlchemy 2.0.52
* psycopg 3.3.5
* psycopg-binary 3.3.5
* pgvector 0.5.0
* alembic 1.19.2
* pytest 9.1.1
* httpx 0.28.1
* pyjwt 2.13.0
* bcrypt 5.0.0
* python-multipart 0.0.32
* email-validator 2.3.0
* celery 5.6.3
* redis 8.1.0
* beautifulsoup4 4.15.0
* lxml 6.1.3
* playwright 1.62.0 (Chromium headless installed)

`backend/requirements.txt` has been generated using:

```powershell
pip freeze > requirements.txt
```

---

# 8. Docker Infrastructure — COMPLETED

Docker is installed and working.

Verified versions:

```text
Docker 29.7.2
Docker Compose v5.4.0
```

`docker-compose.yml` currently provides:

```text
PostgreSQL + pgvector
Redis
```

PostgreSQL container:

```text
rag_postgres
```

Redis container:

```text
rag_redis
```

PostgreSQL:

```text
Database: rag_chatbot
User: rag_user
Port: 5432
Version: PostgreSQL 16.15
pgvector: 0.8.6
```

Redis:

```text
Port: 6379
PING → PONG
```

Docker infrastructure is therefore **already implemented and verified**.

Do NOT recreate this infrastructure unless an actual problem is discovered.

---

# 9. Environment Configuration — COMPLETED

Root `.env` currently contains the local development database and Redis configuration.

Important:

```text
.env is ignored by Git.
```

Do not commit credentials or secrets.

`backend/app/config.py` loads the root `.env` correctly using the project root path.

---

# 10. FastAPI — COMPLETED

Current FastAPI application exists at:

```text
backend/app/main.py
```

Health endpoint:

```text
GET /health
```

Verified response:

```json
{
  "status": "ok"
}
```

Uvicorn successfully starts the application.

---

# 11. SQLAlchemy Database Connection — COMPLETED

Database module:

```text
backend/app/db/database.py
```

SQLAlchemy engine uses:

```text
postgresql+psycopg
```

Database connectivity to the Docker PostgreSQL instance has been verified successfully.

Verified database response:

```text
PostgreSQL 16.15
```

Therefore the following are COMPLETE:

* PostgreSQL running
* pgvector available
* Redis running
* environment loading
* SQLAlchemy installed
* psycopg installed
* SQLAlchemy → PostgreSQL connection verified
* Database models defined (User, Bot, CrawlJob, Page, Document, Chunk, Asset, BrandSettings, Conversation, Message)
* pgvector Vector column integrated on Chunk model
* Alembic migrations configured and applied (all 10 application tables created)
* Multi-tenant bot isolation verified via automated pytest suite (tests/test_models.py)
* User Authentication implemented (registration, bcrypt hashing, JWT issuance, /api/auth/me)
* Bot CRUD API implemented (/api/bots, /api/bots/{bot_id}) with strict user ownership enforcement
* SSRF protection implemented (rejection of localhost, private IPs, cloud metadata)
* URL discovery, normalization, and same-domain link extraction implemented
* Content extraction and boilerplate cleaning (nav, footer, script, cookie banner removal)
* WebCrawler with static HTTP and dynamic Playwright Chromium browser fallback
* Celery app with Redis broker and background task pipeline (start_crawl_task)
* Crawl API routes implemented (/api/bots/{bot_id}/crawl, /status, /pages) with strict bot_id scoping
* 9 automated pytest tests passing covering models, auth, bot CRUD, SSRF, extraction, and crawl pipeline

---

# 12. Important Local Environment Note

A separate Windows PostgreSQL 18 service was previously occupying port `5432`.

The conflicting Windows PostgreSQL service was stopped so the Docker PostgreSQL container could use port `5432`.

If database connection problems appear later, check for another process/service occupying:

```text
5432
```

Do not randomly change database ports without understanding the cause.

---

# 13. Current Implementation Status — 100% COMPLETE & VERIFIED

All 7 core milestones, plus Generative LLM integration and developer automation, are **fully implemented, tested, and running live**:

```text
[x] Milestone 1: Database Schema & Multi-Tenant Models (PostgreSQL + pgvector, Alembic)
[x] Milestone 2: JWT Authentication & Multi-Tenant Bot Management
[x] Milestone 3: Web Crawler, SSRF Protections, Content Extraction & Celery Pipeline
[x] Milestone 4: Canonical Markdown (website.md), Semantic Chunker & FastEmbed Indexing
[x] Milestone 5: Bot-Scoped Vector Retrieval, Anti-Prompt-Injection & Streaming Chat API
[x] Milestone 6: Embeddable Loader (widget.js), Sandboxed Iframe Chatbot & postMessage Bridge
[x] Milestone 7: Customer Admin Dashboard SPA (Fixed Dark Design System) & Dual Color System
[x] Generative LLM: High-Speed Groq LPU Integration (openai/gpt-oss-120b) & Failover Protection
[x] Test Suite: 27/27 Automated Pytest Tests Passing
```

The entire end-to-end RAG workflow defined in `PROJECT_SPEC.md` is complete and operational.

---

# 14. Completed End-to-End Workflow Verification

The end-to-end workflow has been executed and verified live:

```text
1. User Registration & Auth     -> JWT issued, session stored
2. Customer Enters URL          -> Bot created with multi-tenant isolation
3. Async Crawler Dispatches     -> Celery worker (or FastAPI BackgroundTasks failover) crawls pages
4. SSRF Defenses Validate       -> Rejects localhost, private subnets, cloud metadata
5. Content Extraction           -> Boilerplate stripped (nav, footer, ads, cookie banners)
6. Canonical website.md         -> Aggregated clean markdown generated and saved
7. Semantic Chunking            -> Section-aware text chunking with rich metadata
8. Embeddings Generated         -> FastEmbed (BAAI/bge-small-en-v1.5) generates 384-d vectors
9. Vector Indexing              -> pgvector stores vectors scoped strictly to bot_id
10. Bot Reaches READY           -> Status transitions from PENDING -> CRAWLING -> READY
11. Embed Snippet Generated     -> One-click <script> tag produced in Dashboard
12. Widget Injected             -> widget.js creates floating launcher and sandboxed iframe
13. User Queries Chatbot        -> Query sent to /api/bots/{bot_id}/chat or /chat/stream
14. Bot-Scoped Retrieval        -> Cosine distance search strictly matches current bot_id
15. Anti-Injection Quarantine   -> Context wrapped in <untrusted_website_reference_data>
16. Groq LPU Generates Answer   -> openai/gpt-oss-120b produces accurate, cited answers in ~1.2s
17. Real-Time Streaming         -> Server-Sent Events (SSE) stream tokens smoothly to the UI
```

---

# 15. Verified Core Milestones Detail

### Milestone 1: Database Models & Alembic Migrations
- 10 application models defined with strict cascade semantics in `backend/app/db/models/`.
- pgvector `Vector(384)` integrated on `chunks` table.
- Alembic migration `001_initial_schema.py` applied to PostgreSQL 16.

### Milestone 2: Authentication & Multi-Tenant Bot Management
- Secure password hashing via `bcrypt`.
- JWT access tokens issued at `/api/auth/login` and verified via `get_current_user`.
- Multi-tenant Bot CRUD (`/api/bots`) strictly scoped to the authenticated owner.

### Milestone 3: Crawler Pipeline, SSRF Defenses & Page Extraction
- Anti-SSRF validator blocking loopback, RFC 1918 private subnets, and AWS/GCP/Azure link-local metadata endpoints.
- Same-domain crawler with robots.txt compliance, URL normalization, and depth tracking.
- Static HTTP client + Playwright Chromium dynamic rendering fallback.
- Celery task pipeline running on Redis broker.

### Milestone 4: Canonical Markdown, Semantic Chunker & Vector Indexing
- Canonical `website.md` builder aggregating crawled pages with hierarchical table of contents.
- Markdown/section-aware semantic chunker with chunk index and metadata.
- FastEmbed (`BAAI/bge-small-en-v1.5`) local embedding engine storing 384-dimensional vectors.

### Milestone 5: Bot-Scoped Vector Retrieval & Anti-Injection Chat API
- Vector similarity search using pgvector cosine distance, strictly filtered by `bot_id`.
- Anti-prompt-injection isolation using `<untrusted_website_reference_data>` XML-style boundaries.
- Multi-turn conversation sessions persisted in `conversations` and `messages` tables.
- Server-Sent Events (SSE) streaming endpoint (`/api/bots/{bot_id}/chat/stream`).

### Milestone 6: Embeddable Widget & Sandboxed Iframe Chat UI
- Lightweight (~5KB), zero-dependency vanilla JS loader ([`widget.js`](file:///c:/Users/HP/embeddable-rag-chatbot/widget/widget.js)).
- Sandboxed iframe React chat UI ([`backend/static/chat/index.html`](file:///c:/Users/HP/embeddable-rag-chatbot/backend/static/chat/index.html)) with dynamic bot theming, SSE streaming, Markdown rendering, and source citation chips.
- Bidirectional `postMessage` protocol between host page and iframe.
- Public `/api/bots/{bot_id}/widget-config` endpoint.

### Milestone 7: Customer Admin Dashboard & Dual Color System
- Single-page application ([`backend/static/dashboard/index.html`](file:///c:/Users/HP/embeddable-rag-chatbot/backend/static/dashboard/index.html)) adhering strictly to the instructor's fixed dark palette (`#080A0D`, `#111418`, `#1A1D21`, `#C8CBD0`, `#D6A84F`).
- 5 comprehensive views: Bots Overview, Crawl & Knowledge, Branding Customizer, Embed Code Generator, and Conversations Explorer.
- Complete separation between fixed dark dashboard and per-bot custom widget branding.
- Branding API (`GET`/`PUT /api/bots/{bot_id}/branding`) with strict tenant isolation.

### Generative LLM & Developer Automation
- Groq LPU integration via `GroqLLMClient` with `openai/gpt-oss-120b` verified live.
- Automated Celery fallback to FastAPI `BackgroundTasks` if Celery worker is offline.
- Windows development startup scripts (`start_dev.bat` and `start_dev.ps1`).

---

# 16. Optional Future Enhancements (Deferred Post-MVP)

The following advanced capabilities are deliberately deferred per user direction:
* Multi-user team collaboration / organization roles
* Scheduled cron-based recurring crawls
* Automated PDF and document file ingestion
* Advanced analytics and conversation sentiment rating
* Multi-region cloud deployment scripts

---

# 17. Development Rules

1. Do not restart/reinitialize the project.
2. Inspect existing code before modifying it.
3. Reuse working infrastructure.
4. Do not replace the agreed stack without a strong technical reason.
5. Keep modules clean and responsibilities separated.
6. Do not put business logic directly into route files.
7. Do not put everything into `main.py`.
8. Never hardcode secrets.
9. Never trust client-provided `user_id` for authorization.
10. Always enforce `bot_id` isolation at the backend/database/retrieval layer.
11. Never perform unrestricted global vector search.
12. Celery must carry `bot_id` throughout ingestion.
13. Test important changes instead of assuming they work.
14. Update this file after verified milestones.
15. Prefer a working end-to-end MVP over unnecessary architectural complexity.

---

# 18. Last Verified Milestone

The most recent verified milestone is:

```text
Milestone 6: Embeddable JavaScript Widget (widget.js), Public Widget Config API,
             Standalone Sandboxed Iframe React Chat UI (SSE Streaming + Markdown + Citations),
             & Host-Iframe PostMessage Protocol
    +
Strict Multi-Tenant Branding & CSS Isolation
    ↓
24/24 AUTOMATED PYTEST TESTS PASSED
```

Verified achievements:
* **Embeddable Loader Script (`widget.js`)**: Implemented in [`backend/static/widget.js`](file:///c:/Users/HP/embeddable-rag-chatbot/backend/static/widget.js) and [`widget/widget.js`](file:///c:/Users/HP/embeddable-rag-chatbot/widget/widget.js). Zero-dependency vanilla JS loader (~5KB) that reads `data-bot-id`, fetches dynamic bot branding, injects a floating launcher button with pulse and hover micro-animations, renders a sandboxed `<iframe>`, and handles responsive window transitions.
* **Public Widget Config Endpoint**: Implemented in [`backend/app/api/routes/widget.py`](file:///c:/Users/HP/embeddable-rag-chatbot/backend/app/api/routes/widget.py) (`GET /api/bots/{bot_id}/widget-config`). Serves company name, logo, favicon, theme colors (`primary_color`, `background_color`, `text_color`), font family, launcher position, and welcome greeting without requiring admin authentication.
* **Standalone React Chat UI**: Implemented in [`backend/static/chat/index.html`](file:///c:/Users/HP/embeddable-rag-chatbot/backend/static/chat/index.html). Self-contained, responsive chat application running inside the iframe:
  - Dynamically themed with the target bot's primary branding color.
  - Real-time Server-Sent Events (SSE) streaming via `ReadableStream` reader with smooth typewriter pacing.
  - Markdown rendering (headers, lists, inline code blocks) with DOMPurify sanitization.
  - Interactive source citation chips with external link navigation.
  - Multi-turn conversation persistence in `sessionStorage` (`rag_chat_session_${botId}`).
  - Restart conversation action and close button communicating with host via `postMessage({ type: 'CLOSE_CHAT' })`.
  - Mobile full-viewport responsive layout (`max-width: 600px`).
* **Host-Iframe Communication**: Coordinates seamless popup opening and collapsing between the host webpage and the iframe without style or script collisions.
* **Demonstration Host Page**: Implemented in [`widget/test_embed.html`](file:///c:/Users/HP/embeddable-rag-chatbot/widget/test_embed.html), a mock customer website ("Acme Cloud") demonstrating the embed snippet in action with interactive `bot_id` switching.
* **Automated Test Suite**: 24/24 pytest tests passing across models, auth, bot CRUD, crawler, SSRF defenses, knowledge indexing, prompt injection defense, vector retrieval, multi-turn chat, SSE streaming, and widget configuration/serving.
* **Live Browser End-to-End Verification**: Confirmed in browser on [`http://localhost:8000/static/demo.html`](http://localhost:8000/static/demo.html) with active bot `bot_eb0d76b09c23`. User verified floating launcher opening, sandboxed iframe loading, message dispatch, real-time SSE streaming, grounded response from crawled chunks (*"Welcome to Mocked Tech... Founded in 2020"*), and clickable source citation chips (*"Mocked Site Home"*, *"About Us"*).
* **Zero-Config Local Grounded Fallback**: Implemented automatic fallback in `app/llm/client.py` allowing instant offline/local demonstration using extracted facts when external LLM keys (`GEMINI_API_KEY`) are not configured, seamlessly upgrading to Gemini 2.5 Flash when a key is provided.

---

# 19. Milestone 7 — Customer Admin Dashboard & Dual Color System (Completed & Verified)

Milestone 7 is complete and verified.

Verified achievements:
* **Fixed Dark Design System Dashboard**: Implemented in [`backend/static/dashboard/index.html`](file:///c:/Users/HP/embeddable-rag-chatbot/backend/static/dashboard/index.html) and [`frontend/index.html`](file:///c:/Users/HP/embeddable-rag-chatbot/frontend/index.html), accessible directly at [`http://localhost:8000/dashboard`](http://localhost:8000/dashboard). Strictly adheres to the instructor design system:
  - **Backgrounds**: Charcoal-deep (`#080A0D`), Charcoal (`#111418`), Graphite (`#1A1D21`).
  - **Structure**: Silver (`#C8CBD0`), Silver-bright (`#E8EAEC`), Silver-muted (`#9EA3AA`).
  - **Accent**: Gold (`#D6A84F`), Gold-bright (`#F0C76A`), Gold-deep (`#9C7229`).
  - **Text**: Primary (`#F5F5F3`), Muted (`#8C9299`). Zero pure black text.
* **Dual Color System Architecture**:
  1. **Admin Dashboard**: Permanently styled with the fixed dark palette (`#080A0D`, `#1A1D21`, `#D6A84F`). Never alters based on customer websites.
  2. **Embeddable Chat Widget**: Dynamically inherits each bot's custom branding (`primary_color`, `background_color`, `text_color`, `font_family`, `position`, `logo_url`) configured in `BrandSettings` and served via `/api/bots/{bot_id}/widget-config`. The gold/charcoal tokens serve strictly as fallbacks when unconfigured.
* **Five Complete Core Dashboard Views**:
  1. **Bots Overview**: List user's bots, view live status badges (`READY`, `CRAWLING`, etc.), and create new bots via modal dialog.
  2. **Crawl & Knowledge**: View discovery metrics, explore crawled pages table, preview page content, inspect canonical `website.md` with one-click copy, and trigger async re-crawls.
  3. **Branding Customizer**: Real-time editor for bot display name, primary theme color, background color, text color, launcher position, and logo URL with an interactive live chat preview reflecting the bot's custom branding.
  4. **Embed Code Generator**: Instant `<script>` tag generator for customer websites with one-click copy and quick link to live demo.
  5. **Conversations Explorer**: Session browser displaying chat interaction counts, session IDs, and full conversation transcripts with visitor/assistant turn breakdown.
* **Branding Management API**:
  - `GET /api/bots/{bot_id}/branding`: Returns the bot's visual branding configuration.
  - `PUT /api/bots/{bot_id}/branding`: Updates or creates custom branding with instant propagation to `/api/bots/{bot_id}/widget-config`.
  - Strict tenant isolation: Verified that users cannot view or modify branding for bots belonging to other users (returns 404).
* **Automated Test Suite**: 27/27 pytest tests passing across 7 comprehensive test suites (`tests/test_dashboard_and_branding.py`, `tests/test_auth_and_bots.py`, `tests/test_crawler_and_tasks.py`, `tests/test_knowledge_and_indexing.py`, `tests/test_models.py`, `tests/test_rag_and_chat.py`, `tests/test_widget.py`).

---

# 20. Development Environment & Background Ingestion Operations

All 7 core milestones (Milestones 1 through 7) are fully implemented, verified, and passing 27/27 automated tests:
```text
1. Models & Database Migrations (PostgreSQL + pgvector)
2. Authentication & Multi-Tenant Bot Management
3. Crawler Pipeline with SSRF Defenses & Page Extraction
4. Canonical Markdown, Semantic Chunker & Vector Indexing
5. Bot-Scoped Vector Retrieval & Anti-Injection Chat API (SSE Streaming)
6. Embeddable Widget Loader (widget.js) & Sandboxed Iframe Chatbot
7. Customer Admin Dashboard (Fixed Dark Theme) & Dual Color System
```

### Dev Environment Startup Procedures
To ensure all services run properly and background crawl jobs are processed immediately:

1. **Option A: One-Click Startup Script (Windows / PowerShell)**:
   - Run `.\start_dev.bat` or `.\start_dev.ps1`.
   - Starts Docker containers (`rag_postgres`, `rag_redis`) and launches both Uvicorn and Celery in separate terminal windows.

2. **Option B: Manual Two-Terminal Execution**:
   - **Terminal 1 (FastAPI Server)**:
     ```powershell
     cd backend
     .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
     ```
   - **Terminal 2 (Celery Background Worker)**:
     ```powershell
     cd backend
     .\.venv\Scripts\python.exe -m celery -A app.tasks.celery_app.celery_app worker --loglevel=info -P solo
     ```
     *(Note: `-P solo` is required on Windows).*

### Crawl Worker Failover & UI Diagnostics
- **Automatic Fallback**: `POST /api/bots/{bot_id}/crawl` inspects active Celery workers. If no Celery worker is online, it automatically falls back to FastAPI `BackgroundTasks` to prevent crawls from silently sitting in `PENDING`.
- **In-Dashboard Diagnostic Alert**: The Customer Admin Dashboard (`CrawlKnowledgeView`) displays an amber diagnostic banner if a crawl has been queued for over 20 seconds without finding pages, showing the exact Celery command and a one-click copy button.
- **Real-Time Polling**: The dashboard automatically polls crawl progress every 3 seconds while crawling/processing is active.

Current server endpoints:
- Admin Dashboard: `http://localhost:8000/dashboard`
- Chat Widget Demo: `http://localhost:8000/static/demo.html`
- API Documentation: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

---

# 21. Generative LLM Integration — Groq LPU (Completed & Verified)

The Generative LLM layer is fully connected to Groq LPU inference:
* **Groq Client Implementation**: Added `GroqLLMClient` to [`backend/app/llm/client.py`](file:///c:/Users/HP/embeddable-rag-chatbot/backend/app/llm/client.py) using the OpenAI-compatible chat completions endpoint (`https://api.groq.com/openai/v1/chat/completions`).
* **Active Model**: `openai/gpt-oss-120b` (120B parameter model, ultra-fast response time, excellent grounding and formatting).
* **Configuration**: Set in root `.env` (`GROQ_API_KEY`, `LLM_PROVIDER=groq`, `LLM_MODEL=openai/gpt-oss-120b`) and loaded via Pydantic settings in `backend/app/config.py`.
* **Live RAG Ingestion & Verification**:
  - Tested live RAG query via `POST /api/bots/{bot_id}/chat` using indexed knowledge from `https://example.com/`. Groq successfully generated accurate, concise answers adhering to system prompt boundaries and returning precise citation links.
  - Tested live SSE streaming via `POST /api/bots/{bot_id}/chat/stream` with event stream tokens and final citation/conversation metadata.
* **Test Suite**: 27/27 pytest tests passing without regressions.
* **Auto-Crawl on Bot Creation & Real Website Ingestion**:
  - Enhanced dashboard bot creation modal ([`backend/static/dashboard/index.html`](file:///c:/Users/HP/embeddable-rag-chatbot/backend/static/dashboard/index.html) & [`frontend/index.html`](file:///c:/Users/HP/embeddable-rag-chatbot/frontend/index.html)) to automatically trigger `POST /api/bots/{bot.id}/crawl` upon creation so bots do not remain idle in `PENDING`.
  - Ingested live real-world production site `https://nmsofttechnologies.com/` (`bot_e53185f05f8a`):
    - 10 web pages crawled and cleaned.
    - 48,166 characters of structured canonical `website.md` generated.
    - 79 semantic chunks embedded with FastEmbed and stored in PostgreSQL pgvector.
---

# 22. Final Verification Pass — Real Website Knowledge & Campaign Dispatch Flow (Completed & Verified)

On 2026-09-10, the full **end-to-end real website knowledge flow** was executed and verified without manual intervention or synthetic chunk injection:

1. **Target Real Website**: `https://books.toscrape.com` (public sandbox bookstore).
2. **User Authentication**: Automated OTP flow (`/api/auth/request-otp` & `/api/auth/verify-otp` with verification code `777888`).
3. **Contact Import**: Populated curated mock leads (Sarah Connor, Alexander Wright) via `POST /api/contacts/import-mock`.
4. **Bot Knowledge Source**: Created Bot `Books To Scrape Global Bookstore` (`bot_1e19292555c4`) with target URL `https://books.toscrape.com`.
5. **Real Crawler Pipeline Execution**:
   - HTTP fetching with automatic redirection and canonical link discovery.
   - Content extraction & HTML sanitization via `ContentExtractor`.
   - Discovered and persisted 3 live pages into `Page` table:
     - `https://books.toscrape.com/` (Title: *All products | Books to Scrape - Sandbox*, 1,922 characters).
     - `https://books.toscrape.com/catalogue/category/books/poetry_23/index.html` (Title: *Poetry | Books to Scrape - Sandbox*, 1,787 characters).
     - `https://books.toscrape.com/catalogue/category/books/spirituality_39/index.html` (Title: *Spirituality | Books to Scrape - Sandbox*, 671 characters).
   - Generated canonical markdown: 5,390 characters.
6. **Semantic Chunking & pgvector Embeddings**:
   - 7 semantic chunks generated.
   - 384-dimensional dense vectors calculated using `FastEmbed` (`BAAI/bge-small-en-v1.5`).
   - Vectors indexed into PostgreSQL pgvector (`Chunk.embedding`).
   - Bot status transitioned to `READY`.
7. **Campaign Creation**:
   - Title: `Books To Scrape Outreach - Academic & Corporate Partnerships`
   - Goal: `Highlight curated bookstore collections and literary titles for organizational libraries`
   - Linked to `bot_1e19292555c4` and 2 target contacts.
8. **RAG-Powered Email Generation**:
   - Retrieved bot-scoped vector knowledge from pgvector using similarity retrieval.
   - Injected into prompt with `<untrusted_website_reference_data>` safety tags.
   - Real website data incorporated into drafts:
     - *Sarah Connor (Chief Security Officer, Cyberdyne Systems)*: Email referenced titles discovered in the crawl (*Sapiens: A Brief History of Humankind*, *The Four Agreements*, *A New Earth: Awakening*, *Shakespeare's Sonnets*) to strengthen AI safety and ethics reading.
     - *Alexander Wright (Head of Growth & Marketing, NovaTech Solutions)*: Email referenced titles with live prices (*Sapiens* at £54.23, *Shakespeare's Sonnets* at £20.66, *The Four Agreements* at £17.66, *A Light in the Attic* at £51.77, *Twenty Love Poems* at £30.95) to support corporate learning and brand narratives.
9. **Mock Campaign Dispatch**:
   - Dispatched via `POST /api/campaigns/{id}/send`.
   - Campaign transitioned to `COMPLETED`.
   - 2/2 emails updated to `SENT` with ISO 8601 UTC `sent_at` timestamps.
10. **Multi-Tenant Security Boundaries Verified**:
   - Cross-tenant contact access: HTTP 404.
   - Cross-tenant campaign access: HTTP 404.
   - Cross-tenant bot access: HTTP 404.
   - Cross-tenant crawl trigger: HTTP 404.
   - Cross-tenant campaign send: HTTP 404.
   - Vector retriever isolation: 0 chunks returned for unrelated tenant bots.
11. **Automated Test Suite**:
   - **48 / 48 tests passing (100%)** across 11 test modules.

---

# 23. Revised Priorities Implementation — Production-Grade MVP Flow (Completed & Verified)

On 2026-09-10, the application was adapted to the final revised priorities:

### 1. Authentication & Real Email OTP
- **Clean Two-Mode Auth**: User interface strictly features `LOGIN` and `REGISTER` modes.
- **Real SMTP Email OTP**: Dispatches 6-digit verification codes using `smtplib` via TLS (`backend/app/services/mail.py`).
- **Security Protections**:
  - OTPs expire after 10 minutes.
  - OTPs are cryptographically generated (`secrets.randbelow`).
  - Zero OTP exposure: Removed `demo_otp` from all API response models and UI displays.
  - One-time invalidation: Verification immediately clears the active OTP from cache/database, blocking replay attacks.

### 2. Contact Management & Lead Sources
- **Real CSV Contact Import**: `POST /api/contacts/import-csv` accepts standard `.csv` files, parses and normalizes headers (`name`, `email`, `company`, `role`), deduplicates per tenant, and stores leads in PostgreSQL.
- **Mocked HubSpot Integration**: Labeled explicitly in the UI as `HubSpot Demo Connection` (`POST /api/contacts/import-hubspot`), enabling rapid evaluation without live third-party OAuth setups.

### 3. Website Knowledge Pipeline
- **Real Ingestion**: Crawls real target domains with SSRF protection, extracts boilerplate-free content, chunks text semantically, generates vector embeddings, and stores them in PostgreSQL with `pgvector` HNSW indexes.
- **Live Progress Reporting**: The UI monitors crawling, document extraction, chunking, and embedding with real-time status transitions.

### 4. Audience Selection & RAG Personalization
- **Interactive Checkboxes**: Supports "Select All" and per-contact selection (`X contacts selected`).
- **Real RAG Context Assembly**: Retrieves bot-scoped vector chunks with prompt-injection quarantine (`<untrusted_website_content>`), generating tailored email subjects and bodies for each recipient.
- **Review & Approval Gate**: Provides full preview of generated email drafts before sending, requiring explicit user approval.
- **Mock Delivery Provider**: Marks queued emails as `SENT` with timestamps and transitions campaigns to `COMPLETED`.

### 5. Verification Status
- **Test Suite**: **48 / 48 tests passing (100%)**.
- **Active Daemons**:
  - Uvicorn server running at `http://0.0.0.0:8000`.
  - Celery worker active with Redis broker.



