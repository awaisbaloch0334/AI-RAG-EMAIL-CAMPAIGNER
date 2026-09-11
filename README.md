# Embeddable Website-Specific RAG Chatbot Platform

A production-grade, multi-tenant RAG chatbot platform that crawls any website, generates canonical Markdown knowledge, chunks and embeds content into PostgreSQL with pgvector, and serves an embeddable, customizable JavaScript chat widget with real-time SSE streaming.

---

## Architecture Overview

```text
Customer enters Website URL
        ↓
Create Bot & Trigger Ingestion
        ↓
Celery Worker discovers & crawls website pages (with SSRF defenses)
        ↓
Canonical website.md generated → Semantic Chunker → FastEmbed (BAAI/bge-small-en-v1.5)
        ↓
Vectors stored in PostgreSQL + pgvector (Bot-scoped multi-tenant isolation)
        ↓
Bot becomes READY
        ↓
Customer embeds <script src=".../widget.js" data-bot-id="...">
        ↓
Sandboxed Iframe Chatbot UI queries Bot-scoped Vector Retriever
        ↓
Anti-Prompt-Injection Prompt Builder → Grounded LLM Response streamed via SSE
```

---

## Quick Start: Development Environment

### 1. Prerequisites
- **Python 3.11+**
- **Docker & Docker Compose** (for PostgreSQL pgvector and Redis)
- **Node.js** (optional)

### 2. Start PostgreSQL & Redis
```powershell
docker compose up -d
```
Verify containers `rag_postgres` (port 5432) and `rag_redis` (port 6379) are healthy.

---

### 3. Run the Services

You have two options to launch the development environment:

#### Option A: One-Click Startup Script (Recommended)
Run the pre-configured script from the repository root:
```powershell
# In PowerShell:
.\start_dev.ps1

# Or in Windows Command Prompt:
start_dev.bat
```
This automatically verifies Docker containers and launches both the **Uvicorn API Server** and the **Celery Background Worker** in separate console windows.

#### Option B: Two-Terminal Manual Startup

**Terminal 1 — FastAPI Server:**
```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload
```

**Terminal 2 — Celery Background Worker:**
```powershell
cd backend
.\.venv\Scripts\python.exe -m celery -A app.tasks.celery_app.celery_app worker --loglevel=info -P solo
```
> [!NOTE]
> On Windows, the `-P solo` flag is mandatory for Celery to run tasks reliably without POSIX `fork()`.

---

## Application URLs

| Interface | URL | Description |
|---|---|---|
| **Customer Admin Dashboard** | `http://localhost:8000/dashboard` | Fixed dark design system SPA for bot management, crawl inspection, branding customization, and chat logs |
| **Chat Widget Live Demo** | `http://localhost:8000/static/demo.html` | Demo customer website ("Acme Cloud") hosting the embeddable `widget.js` |
| **Interactive API Docs** | `http://localhost:8000/docs` | Swagger OpenAPI documentation for all backend endpoints |
| **Health Endpoint** | `http://localhost:8000/health` | Service health status check |

---

## Crawl Diagnostics & Worker Failover

- **Automatic Failover**: When `POST /api/bots/{bot_id}/crawl` is called, the backend checks for active Celery workers. If a Celery worker is online, the task is dispatched to Celery. If no worker is detected, the API automatically falls back to FastAPI `BackgroundTasks`, preventing crawls from silently getting stranded in `PENDING`.
- **Dashboard Diagnostic Warning**: In the **Crawl & Knowledge** view of the Admin Dashboard, if a crawl remains queued for more than 20 seconds without discovering pages, an amber diagnostic banner appears with the exact command to run the Celery worker and a one-click copy button.
- **Real-Time Polling**: The dashboard automatically polls crawl progress every 3 seconds while ingestion is active, eliminating the need to manually refresh the browser.

---

## Running Automated Tests

Run the complete test suite across all 7 milestones:
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -v tests/
```
All 27 automated tests cover models, authentication, crawler, SSRF security, vector indexing, anti-prompt-injection defenses, SSE streaming, widget loader, and dashboard APIs.

