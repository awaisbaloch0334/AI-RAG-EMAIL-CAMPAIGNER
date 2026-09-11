# AI HANDOFF PROMPT — Embeddable Website-Specific RAG Chatbot

You are the primary AI coding agent continuing an existing software project.

Your job is to inspect the repository, understand the existing implementation, and continue building the project toward its MVP.

---

# 1. READ THESE FILES FIRST

Before modifying code, read these three files:

```text
PROJECT_SPEC.md
CURRENT_STATUS.md
AI_HANDOFF_PROMPT.md
```

They have different purposes.

## PROJECT_SPEC.md

This is the permanent product and architecture specification.

It is the authoritative source for:

* requirements
* architecture
* security rules
* database design
* RAG design
* widget flow
* MVP scope
* future features

## CURRENT_STATUS.md

This is the actual implementation checkpoint.

It tells you what has already been built and verified.

Do not assume a component is incomplete merely because it is described in the specification.

Inspect the repository and status file before recreating anything.

## AI_HANDOFF_PROMPT.md

This file contains operating instructions for you as the coding agent.

It does NOT override product requirements in `PROJECT_SPEC.md`.

---

# 2. CONFLICT RESOLUTION

If files appear to conflict:

### Requirement conflict

```text
PROJECT_SPEC.md wins.
```

### Implementation-state conflict

If `CURRENT_STATUS.md` says something is complete but the code suggests otherwise:

```text
Inspect the code.
Run verification.
Then update CURRENT_STATUS.md to match reality.
```

If `CURRENT_STATUS.md` says something is incomplete but the code proves it is complete:

```text
Verify it.
Then update CURRENT_STATUS.md.
```

Never blindly trust stale status information.

---

# 3. DO NOT RESTART THE PROJECT

This is an existing repository.

Do NOT:

* delete the repository
* recreate the project from scratch
* initialize another project
* replace the architecture unnecessarily
* remove working Docker infrastructure
* reinstall working dependencies without reason
* overwrite working code merely for stylistic reasons

Build on what already exists.

---

# 4. CURRENT PROJECT GOAL

Build an embeddable website-specific RAG chatbot platform.

Core flow:

```text
Website URL
    ↓
Bot
    ↓
Asynchronous crawl
    ↓
Page discovery
    ↓
Content extraction
    ↓
Canonical knowledge
    ↓
Chunking
    ↓
Embeddings
    ↓
PostgreSQL + pgvector
    ↓
Bot READY
    ↓
Embeddable widget
    ↓
Chat
    ↓
Bot-scoped retrieval
    ↓
Grounded LLM answer
```

---

# 5. IMPORTANT: THIS IS RAG

Do NOT implement per-customer model training or fine-tuning.

The system should use:

```text
Website
  ↓
Crawl
  ↓
Extract
  ↓
Canonical Markdown / structured knowledge
  ↓
Chunks
  ↓
Embeddings
  ↓
Vector database
  ↓
Retrieval
  ↓
LLM
```

The canonical Markdown is a useful knowledge artifact.

The raw/structured crawl data remains the underlying source of truth.

LLM-generated normalization must never invent website facts.

---

# 6. NON-NEGOTIABLE MULTI-TENANT SECURITY

The system has:

```text
USER
  ↓
BOT
  ↓
WEBSITE
  ↓
BOT-SCOPED KNOWLEDGE
```

Every knowledge object must be associated with:

```text
bot_id
```

This includes:

* pages
* documents
* chunks
* embeddings
* assets
* screenshots
* conversations
* crawl jobs
* retrieval results

RAG retrieval MUST always include bot scope.

Never perform:

```text
SELECT nearest vectors FROM all tenants
```

without bot filtering.

The system must guarantee:

```text
Bot A cannot retrieve Bot B's knowledge.
Bot B cannot retrieve Bot A's knowledge.
```

This is an architectural invariant, not merely a prompt instruction.

---

# 7. AUTHORIZATION

Never trust:

```text
user_id
```

from the browser/client as proof of ownership.

The backend must:

```text
authenticated user
      ↓
resolve identity
      ↓
load bot
      ↓
verify bot.user_id
      ↓
allow operation
```

Every protected bot operation must respect this boundary.

---

# 8. CELERY

Celery is required for asynchronous ingestion.

Use:

```text
Celery + Redis
```

The ingestion pipeline should eventually resemble:

```text
start_crawl
    ↓
discover_pages
    ↓
crawl_pages
    ↓
extract_content
    ↓
extract_assets_and_screenshots
    ↓
analyze_branding
    ↓
generate_canonical_markdown
    ↓
chunk_documents
    ↓
generate_embeddings
    ↓
index_vectors
    ↓
activate_bot
```

Every task must retain the relevant:

```text
bot_id
```

Do not perform full website crawling synchronously inside an HTTP request.

Chat itself should normally remain a direct FastAPI request/stream rather than being unnecessarily placed in Celery.

---

# 9. ARCHITECTURE STYLE

Keep the project modular.

Prefer:

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

Responsibilities should have clear boundaries.

Avoid giant files.

Avoid placing unrelated responsibilities into one module.

Do not place the entire backend inside `main.py`.

Do not introduce microservices unless genuinely required.

A modular monolith is the intended direction.

---

# 10. EXISTING INFRASTRUCTURE

The following has already been implemented and verified:

```text
Docker
PostgreSQL 16
pgvector
Redis
FastAPI
SQLAlchemy
psycopg
environment configuration
database connectivity
```

Do NOT recreate these.

The SQLAlchemy connection to PostgreSQL has already been successfully verified.

Start from the application layer.

---

# 11. CURRENT PRIORITY

Build the first complete vertical slice.

Priority order:

```text
1. Database models
2. User/Bot ownership
3. Authentication
4. Bot creation
5. Celery + Redis
6. Crawl job
7. Website crawling
8. Content extraction
9. Canonical Markdown
10. Chunking
11. Embeddings
12. pgvector indexing
13. Bot-scoped retrieval
14. Chat endpoint
15. RAG answer generation
16. Widget
17. End-to-end testing
18. Multi-tenant isolation testing
```

Do not spend the majority of the remaining development time on advanced features before this flow works.

---

# 12. TIME-CONSTRAINED EXECUTION MODE

The project currently has a short implementation window.

Therefore:

* You may implement larger coherent slices.
* You do not need to wait for approval after every tiny file.
* However, inspect first.
* Make changes deliberately.
* Run tests/verification after each meaningful milestone.
* Fix failures before moving forward.
* Do not make unnecessary redesigns.

The goal is:

```text
WORKING MVP > PERFECT ARCHITECTURE
```

while still respecting the non-negotiable security and architecture rules.

---

# 13. MVP SUCCESS CRITERIA

The MVP is successful when this works:

```text
User signs in
      ↓
Creates bot with website URL
      ↓
Celery crawl starts
      ↓
Website pages are discovered
      ↓
Website content is extracted
      ↓
website.md is produced
      ↓
Content is chunked
      ↓
Embeddings are generated
      ↓
Vectors stored in PostgreSQL/pgvector
      ↓
Bot becomes READY
      ↓
Embed code can identify the bot
      ↓
Widget opens
      ↓
User asks question
      ↓
Only that bot's knowledge is retrieved
      ↓
LLM produces grounded answer
```

Then verify:

```text
Bot A knowledge ≠ Bot B knowledge
```

using an automated isolation test.

---

# 14. ADVANCED FEATURES CAN WAIT

If time becomes limited, defer:

* advanced analytics
* scheduled recrawling
* advanced hybrid search
* reranking
* advanced multimodal retrieval
* sophisticated screenshot processing
* integrations
* production deployment
* extensive dashboard polish
* unnecessary infrastructure complexity

Do not sacrifice the core RAG flow for these features.

---

# 15. CODE QUALITY REQUIREMENTS

When implementing:

* use type hints
* use clear names
* keep functions focused
* keep services separate
* use Pydantic schemas for API boundaries
* use SQLAlchemy models for persistence
* keep configuration centralized
* never hardcode secrets
* handle errors explicitly
* add tests for important behavior
* avoid duplicated business logic

Do not over-engineer.

---

# 16. VERIFICATION REQUIREMENT

Do not say a feature is complete merely because the code was written.

For every major milestone:

```text
Implement
   ↓
Run
   ↓
Verify
   ↓
Fix failures
   ↓
Record status
```

Examples:

```text
Database model
→ migration/table verification

API
→ endpoint test

Celery
→ task execution test

Crawler
→ actual test URL

Embeddings
→ vector insertion/retrieval test

RAG
→ actual question/answer test

Isolation
→ Bot A/B cross-retrieval test
```

---

# 17. STATUS CHECKPOINTS

After meaningful milestones, update:

```text
CURRENT_STATUS.md
```

The status file should describe what is actually verified, not what is merely planned.

Include:

* completed milestone
* files created/changed
* verification performed
* current next priority
* known issues

---

# 18. FIRST ACTION

Do NOT immediately start writing code.

First:

1. Read `PROJECT_SPEC.md`.
2. Read `CURRENT_STATUS.md`.
3. Inspect the existing repository tree.
4. Inspect the existing backend files.
5. Confirm the existing database connection code.
6. Determine the smallest clean implementation path for the database models and application layer.
7. Produce a concise implementation plan.
8. Then begin implementing the first milestone.

Do not ask the user to manually recreate infrastructure that already exists.

---

# 19. IMPORTANT FINAL RULE

The project should become understandable to another developer.

Someone opening the repository should be able to understand:

```text
Where is authentication?
Where are bots?
Where are database models?
Where is crawling?
Where is extraction?
Where is chunking?
Where are embeddings?
Where is retrieval?
Where is chat?
Where are Celery tasks?
Where is the widget?
Where are tests?
```

Maintain that clarity throughout the implementation.
