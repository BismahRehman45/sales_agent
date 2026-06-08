# Sales Agent API

A production-ready FastAPI backend for an AI sales-agent product. Provides JWT authentication (with Google OAuth), user profile management, document ingestion (uploads + Gmail sync), background processing via Celery, LLM-based summarization, and a **project clustering** layer that groups related emails into projects using pgvector embeddings.

---

## Key Features

- **JWT Authentication** — email/password + Google OAuth login, access/refresh token rotation, server-side token blacklist
- **Google OAuth + Gmail Integration** — one-click Gmail readonly scope, automatic token refresh, incremental email sync via `history.list()`
- **Timezone-Aware Scheduler** — Celery Beat dispatches sync tasks only during each user's working hours (9 AM–6 PM local time)
- **Document Processing** — upload `.txt`, `.pdf`, `.docx` files or ingest Gmail emails; automatic text extraction and LLM summarization
- **Project Clustering** — pgvector + sentence-transformers (`all-MiniLM-L6-v2`, 384-dim) groups related emails into projects by cosine similarity
- **BANT Analysis** — LLM-powered Budget, Authority, Need, Timeline qualification for sales opportunities
- **Async Throughout** — SQLAlchemy async session, httpx for external calls, Celery for background work

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI (async) |
| Database | PostgreSQL + asyncpg + SQLAlchemy 2.0 |
| Vector Search | pgvector (384-dim embeddings) |
| Migrations | Alembic (async) |
| Auth | python-jose (JWT), bcrypt, Google OAuth 2.0 |
| Background Jobs | Celery + Redis (broker, backend, beat) |
| LLM | OpenAI-compatible API (configurable endpoint) |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 (local, free) |
| Document Parsing | pdfplumber, python-docx |
| Package Manager | uv |

---

## Project Structure

```
app/
├── main.py                       # FastAPI entry point, CORS, router registration
├── core/
│   ├── config.py                 # Pydantic Settings (env vars)
│   ├── database.py               # Async SQLAlchemy engine + session
│   └── celery_app.py             # Celery app + beat schedule (30s Gmail sync)
├── models/
│   ├── user.py                   # users table
│   ├── token_blacklist.py        # token_blacklist table
│   ├── document.py               # documents table (uploads + gmail)
│   ├── gmail_message.py          # gmail_messages (dedup + sync tracking)
│   ├── project.py                # projects (pgvector embeddings, RAG)
│   ├── project_document.py       # project_documents (junction)
│   └── project_bant.py           # project_bant (BANT analysis)
├── routers/
│   ├── auth.py                   # /auth/* endpoints
│   ├── user_router.py            # /users/me endpoints
│   ├── document_router.py        # /documents endpoints
│   └── project_router.py         # /projects endpoints + BANT
├── schemas/
│   ├── auth.py                   # UserCreate, LoginRequest, TokenResponse
│   ├── user_schema.py            # UserUpdate, UserResponse
│   ├── document_schema.py        # DocumentResponse, DocumentUploadResponse
│   └── project_schema.py         # ProjectResponse, BantResponse
├── services/
│   ├── user_service.py           # User CRUD, password hashing, auth
│   ├── jwt_service.py            # JWT encode/decode/verify
│   ├── google_oauth_service.py   # Google OAuth + userinfo
│   ├── gmail_token_service.py    # Gmail access-token refresh
│   ├── gmail_sync_service.py     # Incremental Gmail sync pipeline
│   ├── document_service.py       # Upload validation + file persistence
│   ├── llm_service.py            # Summarization, classification, BANT, naming
│   ├── embedding_service.py      # sentence-transformers MiniLM-L6-v2
│   └── project_service.py        # RAG pipeline, project CRUD
├── repositories/
│   ├── user_repository.py
│   ├── token_repository.py
│   ├── document_repository.py
│   ├── gmail_message_repository.py
│   └── project_repository.py
├── tasks/
│   ├── gmail_scheduler_task.py   # Beat-driven scheduler + per-user sync
│   ├── document_processing_task.py # Upload extract + summarize
│   ├── project_matching_task.py  # Embed doc → pgvector search → create/update project
│   ├── project_classification_task.py # LLM classifies lead vs sale_opportunity
│   └── bant_analysis_task.py     # LLM BANT analysis
└── dependencies/
    └── auth.py                   # get_current_user, oauth2_scheme
```

---

## Requirements

- Python 3.13+
- PostgreSQL 12+ (with pgvector extension)
- Redis 6+

---

## Installation

```bash
git clone <repo-url> sales_agent
cd sales_agent
```

Install with uv (recommended):

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

---

## Configuration

Create a `.env` file at the project root:

```env
# Database (async PostgreSQL)
DATABASE_URI=postgresql+asyncpg://user:password@localhost:5432/sales_agent

# Redis (Celery broker + backend)
REDIS_URL=redis://localhost:6379/0

# JWT
SECRET_KEY=your-super-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# LLM (OpenAI-compatible API)
OPENAI_API_KEY=your-api-key
OPENAI_API_URL=https://api.openai.com/v1/chat/completions
OPENAI_MODEL=gpt-4o-mini

# Embeddings (local, free)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Project Matching
PROJECT_MATCH_THRESHOLD=0.5
```

---

## Database Setup

```bash
# Apply all migrations (creates tables including pgvector)
uv run alembic upgrade head

# Generate new migration after model changes
uv run alembic revision --autogenerate -m "description"
```

---

## Running the Application

Three processes are required:

### 1. FastAPI Server

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at `http://localhost:8000/docs`.

### 2. Celery Worker

Handles document processing, project matching, classification, and BANT analysis:

```bash
uv run celery -A app.core.celery_app.celery_app worker -l info -P solo
```

### 3. Celery Beat Scheduler

Drives the Gmail sync schedule (every 30 seconds):

```bash
uv run celery -A app.core.celery_app.celery_app beat -l info
```

### 4. Redis

Required by Celery:

```bash
# Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or local
redis-server
```

---

## API Endpoints

### Authentication (`/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | No | Register with email/username/password |
| POST | `/auth/login` | No | JSON login (email/password) |
| POST | `/auth/token` | No | OAuth2 password flow (`application/x-www-form-urlencoded`) |
| POST | `/auth/refresh` | No | Exchange refresh token for new access + refresh |
| POST | `/auth/logout` | Bearer | Blacklist current access token |
| GET | `/auth/google/login` | No | Get Google OAuth authorization URL |
| GET | `/auth/google/callback` | No | Exchange code, create/update user, return JWTs |

### User Profile (`/users`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/users/me` | JWT | Get current user profile |
| PATCH | `/users/me` | JWT | Update username/email/password/timezone |
| DELETE | `/users/me` | JWT | Soft delete account + blacklist token |

### Documents (`/documents`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/documents/upload` | JWT | Upload `.txt`/`.pdf`/`.docx` with `project_id` (multipart) |
| GET | `/documents` | JWT | List user's documents |
| GET | `/documents/{id}` | JWT | Get document with extracted content |

### Projects (`/projects`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/projects` | JWT | List projects (filter: `open`, `closed`, `all`) |
| GET | `/projects/open` | JWT | List only open projects |
| GET | `/projects/{id}` | JWT | Get project details with RAG content |
| PATCH | `/projects/{id}` | JWT | Update project name or status |
| DELETE | `/projects/{id}` | JWT | Delete a project |
| POST | `/projects/{id}/close` | JWT | Close a project |
| POST | `/projects/{id}/reopen` | JWT | Reopen a project |
| GET | `/projects/{id}/bant` | JWT | Get BANT analysis for a project |

---

## Architecture

### Authentication Flow

```
Register/Login → access_token + refresh_token (JWT, python-jose)
    ↓
Authorization: Bearer <token> → get_current_user verifies signature, checks blacklist, fetches user
    ↓
Logout/Delete → JTI added to token_blacklist → future requests get 401
    ↓
Refresh → new access + refresh tokens from valid refresh token
```

### Gmail Sync Pipeline

```
[Beat, every 30s] schedule_gmail_sync
  → fetch users with gmail_access_token
  → for each user: convert UTC → user.timezone
     → if local hour ∈ [9, 18): enqueue sync_user_emails.delay(user_id)
  → return {total_users, processed, skipped}

[Worker] sync_user_emails → GmailSyncService.sync_user_emails
  → ensure_token_fresh (refresh if within 5 min of expiry)
  → history.list?startHistoryId=… (incremental) or messages.list (first-time)
  → dedup via gmail_message_repository
  → create Document(source=gmail, status=pending)
  → LLMService.summarize_text inline → set summary, status=processed
  → update user.gmail_history_id + last_email_sync_at
```

### Document Upload Pipeline

```
POST /documents/upload (with project_id)
  → validate ext (.txt/.pdf/.docx) and size (≤10 MB)
  → write to uploads/{user_id}/{doc_id}.{ext}
  → create Document(status=pending) + link to project via project_documents
  → process_uploaded_document.delay(doc_id) [Celery]

[Worker] process_uploaded_document
  → extract text (pdfplumber / python-docx / utf-8)
  → LLMService.summarize_text → save summary
  → ProjectService.update_upload_project_rag → append to project.rag, re-embed
```

### Project Clustering (pgvector)

```
New Gmail document (status=processed)
  → match_document_to_project.delay(doc.id)
  → Embed doc.summary → 384-dim vector (MiniLM-L6-v2)
  → pgvector search: ORDER BY rag_embedding <=> query_vector
     WHERE user_id=X AND sender_email=Y AND status='open'
  → Cosine similarity ≥ 0.5 → append to project.rag, re-embed
  → Cosine similarity < 0.5 → create new project (LLM-generated name)
  → Enqueue project_classification_task → LLM classifies lead vs sale_opportunity
  → If sale_opportunity → enqueue bant_analysis_task
```

### BANT Analysis

For projects classified as `sale_opportunity`, the system runs LLM-powered analysis on four components:

- **Budget** — pricing discussions, cost constraints, funding
- **Authority** — decision-makers, approval process, roles
- **Need** — pain points, requirements, business problems
- **Timeline** — deadlines, urgency, go-live expectations

---

## Database Schema

### `users`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `email` | String(255) | unique, indexed |
| `username` | String(100) | nullable |
| `hashed_password` | String(255) | nullable (Google-only users) |
| `is_active` | Boolean | default True |
| `is_verified` | Boolean | default False |
| `google_id` | String(255) | unique, nullable |
| `timezone` | String(50) | IANA format, default "Asia/Karachi" |
| `gmail_access_token` | String(1000) | nullable |
| `gmail_refresh_token` | String(1000) | nullable |
| `gmail_token_expiry` | DateTime(tz) | nullable |
| `gmail_history_id` | String(100) | nullable |
| `last_email_sync_at` | DateTime(tz) | nullable |
| `created_at` / `updated_at` / `deleted_at` | DateTime(tz) | soft delete |

### `documents`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | indexed |
| `source` | String(50) | "gmail" or "upload" |
| `title` | String(500) | email subject or filename |
| `content` | Text | extracted text |
| `summary` | Text | LLM-generated |
| `file_type` | String(50) | "email", "pdf", "docx", "txt" |
| `file_path` | String(500) | disk path for uploads |
| `status` | String(50) | pending / processing / processed / failed |
| `sender_email` | String(255) | NULL for uploads |

### `projects`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | indexed |
| `sender_email` | String(255) | not null |
| `name` | String(255) | not null |
| `rag` | Text | accumulated email content |
| `rag_embedding` | Vector(384) | pgvector |
| `type` | String(50) | "lead" or "sale_opportunity" |
| `type_confidence` | Float | 0.0–1.0 |
| `type_reasoning` | Text | LLM explanation |
| `status` | String(50) | "open" or "closed" |
| `document_count` | Integer | default 0 |
| `last_email_at` | DateTime(tz) | nullable |

### `gmail_messages` (deduplication)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID | indexed |
| `gmail_message_id` | String(255) | unique per user |
| `subject` / `sender` / `received_at` | — | metadata |
| `document_id` | UUID | FK to documents |
| `synced_at` | DateTime(tz) | indexed with user_id |

### `project_documents` (junction)

Links projects to their constituent documents.

### `project_bant`

Stores BANT analysis results per project (budget, authority, need, timeline, summary).

---

## Embedding Model

| Property | Value |
|----------|-------|
| Model | `sentence-transformers/all-MiniLM-L6-v2` |
| Dimensions | 384 |
| Max tokens | ~512 (~2000 chars) |
| Runs | Locally (no API call, free) |
| Similarity threshold | 0.5 (configurable via `PROJECT_MATCH_THRESHOLD`) |

---

## Monitoring

```bash
# Active Celery tasks
uv run celery -A app.core.celery_app.celery_app inspect active

# Worker stats
uv run celery -A app.core.celery_app.celery_app inspect stats

# Redis check
redis-cli ping
```

---

## Troubleshooting

**No emails syncing:**
1. Verify Redis is running: `redis-cli ping`
2. Check Celery Beat and worker are running
3. Confirm user has Gmail tokens: `SELECT gmail_access_token FROM users WHERE email = '...';`
4. Verify timezone is valid and local time is within 9 AM–6 PM

**Token refresh failing:**
- Tokens auto-refresh with 5-minute buffer before expiry
- Re-authenticate via OAuth flow if refresh token is invalidated

**Duplicate emails:**
- Prevented by `UNIQUE(user_id, gmail_message_id)` constraint on `gmail_messages`

---

## Production Deployment

1. Use secure secret management (AWS Secrets Manager, HashiCorp Vault) for `.env` values
2. Run multiple Celery workers for fault tolerance
3. Deploy Redis with persistence and replication
4. Enable PgBouncer for PostgreSQL connection pooling
5. Use Flower for Celery task monitoring
6. Tighten CORS from `allow_origins=["*"]` to specific domains
7. Add rate limiting and request validation

---

