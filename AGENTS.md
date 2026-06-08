# Sales Agent API — Project Overview

## Description
A production-ready FastAPI backend for an **AI sales-agent** product. Provides JWT auth (with Google OAuth), user profile management, document ingestion (uploads + Gmail sync), background processing via Celery, LLM-based summarization, and a **project clustering** layer that groups related emails into projects using pgvector embeddings.

## Tech Stack
- **Framework**: FastAPI (async)
- **Database**: PostgreSQL via asyncpg + SQLAlchemy 2.0 (async), `pgvector` for vector similarity search
- **Migrations**: Alembic (async)
- **Auth**: JWT (python-jose) with access/refresh tokens + DB-backed token blacklist
- **Password Hashing**: bcrypt
- **OAuth**: Google OAuth 2.0 (httpx) — login + Gmail `readonly` scope
- **Background Jobs**: Celery + Redis (broker, backend, beat)
- **LLM**: OpenAI-compatible API via httpx (Groq `llama-3.3-70b-versatile`)
- **Embeddings**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim, local, free)
- **Document Parsing**: `pdfplumber`, `python-docx`
- **File Storage**: Local disk under `uploads/{user_id}/`
- **Config**: Pydantic Settings with `.env`
- **Package Manager**: uv

## Architecture — Clean Layered Pattern

```
app/
├── routers/                      # HTTP layer — request parsing, response formatting
│   ├── auth.py                   # /auth/* (register, login, token, refresh, logout, google/*)
│   ├── user_router.py            # /users/me (GET, PATCH, DELETE)
│   ├── document_router.py        # /documents (upload, list, get)
│   └── project_router.py         # /projects (list, get, update, delete, close, reopen)
│
├── services/                     # Business logic — validation, hashing, orchestration
│   ├── user_service.py           # User CRUD, password hashing, auth, token blacklisting
│   ├── jwt_service.py            # JWT encode/decode/verify, JTI generation
│   ├── google_oauth_service.py   # Google OAuth + userinfo exchange
│   ├── gmail_token_service.py    # Gmail access-token refresh
│   ├── gmail_sync_service.py     # Incremental Gmail → Document pipeline
│   ├── document_service.py       # Upload validation + file persistence + Celery enqueue
│   ├── llm_service.py            # OpenAI summarization, project classification, name generation
│   ├── embedding_service.py      # sentence-transformers MiniLM-L6-v2 (384-dim)
│   └── project_service.py        # RAG pipeline: embedding → pgvector search → create/update project
│
├── repositories/                 # Data access layer — SQLAlchemy queries only
│   ├── user_repository.py
│   ├── token_repository.py
│   ├── document_repository.py
│   ├── gmail_message_repository.py
│   └── project_repository.py
│
├── schemas/                      # Pydantic request/response models
│   ├── auth.py                   # UserCreate, LoginRequest, TokenResponse, RefreshTokenRequest
│   ├── user_schema.py            # UserUpdate, UserResponse, DeleteResponse
│   ├── document_schema.py        # DocumentResponse, DocumentDetailResponse, DocumentUploadResponse
│   └── project_schema.py         # ProjectResponse, ProjectDetailResponse, ProjectUpdateRequest
│
├── models/                       # SQLAlchemy ORM models
│   ├── user.py                   # users
│   ├── token_blacklist.py        # token_blacklist
│   ├── document.py               # documents (uploaded + gmail)
│   ├── gmail_message.py          # gmail_messages (dedup + sync tracking)
│   ├── project.py                # projects (pgvector embeddings, RAG)
│   └── project_document.py       # project_documents (junction table)
│
├── tasks/                        # Celery tasks
│   ├── gmail_scheduler_task.py   # Beat-driven scheduler + per-user sync
│   ├── document_processing_task.py # Uploaded-file extract + summarize
│   ├── project_matching_task.py  # Embed doc → pgvector search → update/create project
│   └── project_classification_task.py # LLM classifies project as lead/sale_opportunity
│
├── dependencies/                 # FastAPI dependency injection
│   └── auth.py                   # get_current_user, oauth2_scheme, http_bearer
│
├── core/                         # Core configuration & infra
│   ├── config.py                 # Pydantic Settings (env vars)
│   ├── database.py               # Async engine (NullPool), session, get_db
│   └── celery_app.py             # Celery app + beat schedule
│
└── main.py                       # App entry point, CORS, router registration
```

### Layer Responsibilities

| Layer | Responsibility | Must NOT |
|-------|---------------|----------|
| **Router** | Parse HTTP requests, call services, return responses | Contain business logic or DB queries |
| **Service** | Business rules, validation, password hashing, orchestration, external API calls | Contain raw SQLAlchemy queries |
| **Repository** | Raw SQLAlchemy CRUD operations only | Contain business logic or validation |
| **Task** | Celery `@shared_task` entrypoint that calls services | Be invoked directly from routers |

## API Endpoints

### Authentication (`/auth`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | No | Register with email/username/password (+ optional timezone) |
| POST | `/auth/login` | No | JSON login (email/password) |
| POST | `/auth/token` | No | OAuth2 password flow (`application/x-www-form-urlencoded`) |
| POST | `/auth/refresh` | No | Exchange refresh token for new access + refresh |
| POST | `/auth/logout` | Bearer | Blacklist current access token |
| GET | `/auth/google/login` | No | Get Google OAuth authorization URL (includes `gmail.readonly` scope, `prompt=consent`) |
| GET | `/auth/google/callback` | No | Exchange code, fetch userinfo, persist Gmail tokens, return JWTs |

### User Profile (`/users`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/users/me` | JWT | Get current user |
| PATCH | `/users/me` | JWT | Partial update (username/email/password/timezone) |
| DELETE | `/users/me` | JWT | Soft delete account + blacklist current token |

### Documents (`/documents`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/documents/upload` | JWT (multipart) | Upload `.txt`/`.pdf`/`.docx` (≤10 MB) with `project_id` → queued for Celery processing |
| GET | `/documents` | JWT | List current user's documents (limit 100) |
| GET | `/documents/{id}` | JWT | Get single document incl. extracted `content` (ownership-checked) |

### Projects (`/projects`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/projects` | JWT | List projects (filter by status: open/closed/all) |
| GET | `/projects/{id}` | JWT | Get project details with RAG content |
| PATCH | `/projects/{id}` | JWT | Update project (name or status) |
| DELETE | `/projects/{id}` | JWT | Delete a project |
| POST | `/projects/{id}/close` | JWT | Close a project (set status to closed) |
| POST | `/projects/{id}/reopen` | JWT | Reopen a project (set status to open) |

## Database Models

### `users`
- `id` (UUID, PK)
- `email` (String, unique, indexed)
- `username` (String, nullable)
- `hashed_password` (String, nullable)
- `is_active` (Boolean, default True)
- `is_verified` (Boolean, default False)
- `google_id` (String, unique, nullable)
- `created_at`, `updated_at` (DateTime tz)
- `deleted_at` (DateTime tz, nullable — soft delete)
- **Gmail integration**: `gmail_access_token`, `gmail_refresh_token`, `gmail_token_expiry`, `gmail_history_id`
- **Scheduler**: `timezone` (default `UTC`), `last_email_sync_at`

### `token_blacklist`
- `id` (UUID, PK)
- `token_jti` (String, unique, indexed)
- `token_type` (String — `access` / `refresh`)
- `reason` (String, nullable — `logout` / `account_deleted`)
- `expires_at` (DateTime tz)
- `created_at` (DateTime tz)
- `user_id` (UUID, indexed)

### `documents`
- `id` (UUID, PK)
- `user_id` (UUID, indexed)
- `source` (String — `upload` / `gmail`)
- `title` (String, nullable)
- `content` (Text — extracted text or email body, truncated to 5000 chars for gmail)
- `summary` (Text, nullable — LLM-generated)
- `file_type` (String — `email` / `pdf` / `docx` / `txt`)
- `file_path` (String, nullable — disk path for uploads)
- `status` (String — `pending` / `processing` / `processed` / `failed`)
- `error_message` (Text, nullable)
- `created_at` (DateTime tz)

### `gmail_messages`
- `id` (UUID, PK)
- `user_id` (UUID, indexed)
- `gmail_message_id` (String)
- `subject`, `sender`, `received_at`, `synced_at`
- `status` (`pending` / `processed` / `failed`)
- `document_id` (UUID, nullable — FK to created Document)
- **Unique**(`user_id`, `gmail_message_id`) — dedup
- **Index**(`user_id`, `synced_at`) — pagination

### `projects`
- `id` (UUID, PK)
- `user_id` (UUID, indexed)
- `sender_email` (String, not null)
- `name` (String, not null)
- `rag` (Text — accumulated email content)
- `rag_embedding` (Vector 384 — pgvector)
- `type` (String — `lead` / `sale_opportunity`, default `lead`)
- `type_confidence` (Float, default 0.0)
- `type_reasoning` (Text, nullable)
- `status` (String — `open` / `closed`, default `open`)
- `document_count` (Integer, default 0)
- `last_email_at` (DateTime tz, nullable)
- `created_at`, `updated_at` (DateTime tz)
- **Unique**(`user_id`, `sender_email`, `name`)

### `project_documents`
- `project_id` (UUID, FK → projects)
- `document_id` (UUID, FK → documents)
- Junction table linking projects to documents

## Authentication Flow

1. **Registration/Login** → `access_token` + `refresh_token` (JWT, jose)
2. **Access Token** → `Authorization: Bearer <token>` (both `OAuth2PasswordBearer` and `HTTPBearer` accepted by `get_current_user`)
3. **Token Validation** → verify signature, check `type=access`, lookup JTI in `token_blacklist`, fetch user, reject if `deleted_at` is set
4. **Logout/Delete** → JTI added to `token_blacklist`; future requests get 401
5. **Refresh** → new access + refresh tokens from a valid refresh token
6. **Soft Delete** → `deleted_at` set + `is_active=False` + current token blacklisted

## Document Pipeline

### Upload (with Project Link)
```
POST /documents/upload (with project_id)
  → document_service.save_uploaded_file
     → validate ext (.txt/.pdf/.docx) and size (≤10 MB)
     → write to uploads/{user_id}/{doc_id}.{ext} (aiofiles)
     → document_repository.create_document (status=pending)
     → validate project exists and belongs to user
     → create record in project_documents: (project_id, document_id)
     → process_uploaded_document.delay(doc_id)
  → 201 DocumentUploadResponse
```
`process_uploaded_document` (Celery, fresh engine per task):
1. Load doc → set `status=processing`
2. `_extract_text` — `pdfplumber` (PDF), `python-docx` (DOCX), or `utf-8` read (TXT)
3. Save `content` → `LLMService.summarize_text(content)` (OpenAI) → save `summary`, `status=processed`
4. If `source == "upload"`: call `ProjectService.update_upload_project_rag(db, doc)`
   - Query `project_documents` → get `project_id`
   - Append document content to `project.rag`
   - Re-embed `project.rag` → store in `project.rag_embedding`
   - Update `project.document_count += 1`
   - Do NOT update `project.last_email_at`
5. On error: `status=failed`, `error_message=str(e)[:1000]`

### Gmail sync (Celery Beat → worker)
```
[Beat, every 30s] schedule_gmail_sync
  → fetch users with gmail_access_token
  → for each user: convert UTC to user.timezone (pytz)
     → if local hour ∈ [9, 18): enqueue sync_user_emails.delay(user_id)
  → return {total_users, processed, skipped}
[Worker] sync_user_emails → GmailSyncService.sync_user_emails
  → ensure_token_fresh (refresh if within 5 min of expiry)
  → _fetch_incremental_emails:
     - if gmail_history_id: history.list?startHistoryId=…&historyTypes=messageAdded
       (paginated via nextPageToken)
     - on HTTP 404 (history expired): fall back to full INBOX sync, clear history_id
     - first-time sync: full INBOX
  → for each message:
     - dedup via gmail_message_repository.get_message_by_gmail_id
     - create GmailMessage(status=pending)
     - create Document(source=gmail, content=body, status=pending)  [body ≤5000 chars]
     - LLMService.summarize_text inline → set summary, status=processed/failed
     - link GmailMessage.document_id
  → update user.gmail_history_id to latest historyId, last_email_sync_at=now
```

> Gmail path processes summarization **inline** (synchronous within the worker) — no separate Celery task is enqueued. Upload path uses Celery. See `Known Issues`.

## Configuration (`.env`)

| Variable | Description |
|----------|-------------|
| `DATABASE_URI` | PostgreSQL async DSN (`postgresql+asyncpg://…`) |
| `REDIS_URL` | Redis broker/backend (default `redis://localhost:6379/0`) |
| `SECRET_KEY` | JWT signing secret |
| `ALGORITHM` | JWT algorithm (default `HS256`) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL (default 30) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL (default 7) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | OAuth app credentials |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL |
| `GOOGLE_USERINFO_URL` / `GOOGLE_AUTH_URL` / `GOOGLE_TOKEN_URL` | Defaults provided |
| `OPENAI_API_KEY` | Required for any LLM summarization (uploads + gmail) |
| `OPENAI_API_URL` | Default `https://api.openai.com/v1/chat/completions` |
| `OPENAI_MODEL` | Default `gpt-4o-mini` |
| `EMBEDDING_MODEL` | Default `sentence-transformers/all-MiniLM-L6-v2` |
| `PROJECT_MATCH_THRESHOLD` | Default `0.5` (50% cosine similarity) |

## Key Design Decisions

- **Soft delete only** — `users.deleted_at` is set; rows are never removed.
- **Token blacklist** — DB-backed JTI store enables server-side revocation.
- **Partial updates** — `PATCH /users/me` uses `model_dump(exclude_unset=True)`.
- **Uniqueness checks** — Email/username re-validated on every write, excluding the current user.
- **Password never returned** — `UserResponse` schema excludes `hashed_password` and Gmail tokens.
- **Async throughout** — SQLAlchemy async session; httpx for all external calls.
- **NullPool for SQLAlchemy** — avoids "attached to a different loop" errors when Celery workers (which create a fresh loop per task) share the engine with FastAPI.
- **Fresh engine per Celery task** — `document_processing_task` creates + disposes its own engine to isolate loop state.
- **History-id based incremental Gmail sync** — falls back to full INBOX on 404 (expired history).
- **Body truncated to 5000 chars** for Gmail — prevents huge documents.
- **`prompt=consent` forced** in Google OAuth — guarantees a `refresh_token` is returned on every login.
- **Per-user working-hours gate** — Gmail sync only runs 09:00–18:00 in the user's `timezone` (9 ≤ hour < 18).
- **Deduplication** — `UNIQUE(user_id, gmail_message_id)` + pre-insert lookup in the sync service.
- **No hardcoded secrets** — all sensitive config loaded from `.env`.

## Project Clustering (Implemented)

The project clustering layer is now fully implemented. It uses **pgvector** + **sentence-transformers/all-MiniLM-L6-v2** (384-dim, cosine similarity, 0.5 threshold) to automatically group related emails into projects.

Pipeline:
```
Gmail doc.status = "processed"
  → enqueue match_document_to_project.delay(doc.id)
  → compute embedding of doc.summary
  → SELECT best project WHERE user_id=X AND sender_email=Y
       ORDER BY rag_embedding <=> $1::vector LIMIT 1
  → if similarity ≥ 0.5: append content to project.rag, re-embed
  → else: create new project (LLM-generated name)
```

New files: `project.py`, `embedding_service.py`, `project_service.py`, `project_repository.py`, `project_matching_task.py`, `project_router.py`, `project_classification_task.py`, `project_document.py`

Migrations applied: `add_sender_email_to_documents`, `add_projects_table` (with pgvector), `add_project_documents_table`

## Embedding & RAG (Retrieval-Augmented Generation)

### Model

| Property | Value |
|----------|-------|
| Model | `sentence-transformers/all-MiniLM-L6-v2` |
| Type | Sentence Transformer (BERT-based) |
| Output | 384 dimensions (Vector 384) |
| Max tokens | 512 tokens (~2000 characters) |
| Runs | **Locally** (no API call, free) |
| Speed | Fast (~100ms per text) |
| Singleton | Yes — loaded once, reused via `get_model()` |

### How It Works

```
Text Input: "We need AI CRM solution for sales"
        ↓
EmbeddingService.compute_embedding(text)
        ↓
sentence-transformers/all-MiniLM-L6-v2
        ↓
Output: [0.12, -0.34, 0.56, ...] (384 numbers)
        ↓
Stored in: projects.rag_embedding (VECTOR type in PostgreSQL)
```

### Code Locations

| What | File | Line | Description |
|------|------|------|-------------|
| Model loading | `embedding_service.py:16-24` | `SentenceTransformer("all-MiniLM-L6-v2")` | Singleton pattern |
| Compute embedding | `embedding_service.py:31-47` | `model.encode(text)` | Text → 384-dim vector |
| Store in DB | `project_service.py:234-235` | `project.rag_embedding = EmbeddingService.compute_embedding(project.rag)` | Embed entire RAG |
| Search similar | `project_service.py:127-141` | `ORDER BY rag_embedding <=> vector` | pgvector cosine similarity |
| Similarity threshold | `config.py:29` | `PROJECT_MATCH_THRESHOLD = 0.5` | 50% minimum similarity |

### Two Uses

**A. Email Matching (find/create project)**
```
New email arrives
  → Embed email summary → 384-dim vector
  → pgvector search: ORDER BY rag_embedding <=> query_vector
  → Cosine similarity ≥ 0.5 → Add to existing project
  → Cosine similarity < 0.5 → Create new project
```

**B. Upload Documents (update project RAG)**
```
Upload document processed
  → Append content to project.rag (one big text)
  → Re-embed entire project.rag → NEW 384-dim vector
  → Store in project.rag_embedding
```

### Database Storage

```
projects table:
  rag           TEXT          → "Hello... pricing... contract..."
  rag_embedding VECTOR(384)   → [0.12, -0.34, 0.56, ...]

pgvector extension in PostgreSQL stores and searches these vectors efficiently.
```

### Current Approach: Whole Content (No Chunks)

```python
# project_service.py line 232-235
project.rag = project.rag + separator + new_content  # Append to full text
project.rag_embedding = EmbeddingService.compute_embedding(project.rag)  # Embed ENTIRE RAG
```

**The whole `project.rag` is embedded as ONE vector.** No chunking.

> **Note:** MiniLM model has max ~512 tokens. Long RAG content gets truncated. For better results with long documents, consider implementing chunking (split into ~500 char chunks, embed each separately).

### Comparison: Embedding Approaches

| Feature | Current (Whole Content) | Chunking | OpenAI ada-002 |
|---------|------------------------|----------|----------------|
| **Approach** | Embed entire RAG as one vector | Split into chunks, embed each | API-based embedding |
| **Model** | MiniLM-L6-v2 (local) | MiniLM-L6-v2 (local) | text-embedding-ada-002 |
| **Dimensions** | 384 | 384 | 1536 |
| **Max tokens** | 512 (~2000 chars) | 512 per chunk | 8191 |
| **Cost** | Free | Free | $0.0001/1K tokens |
| **Speed** | Fast (~100ms) | Fast (~100ms per chunk) | Slower (API call) |
| **Accuracy** | Good for short texts | Best for long documents | Best overall |
| **DB storage** | 1 vector per project | Multiple vectors per project | 1 vector per project |
| **Search** | Simple cosine similarity | Search all chunks, take best | Simple cosine similarity |
| **Implementation** | ✅ Implemented | ❌ Not implemented | ❌ Not implemented |

### Comparison: Models

| Model | Dimensions | Max Tokens | Speed | Cost | Use Case |
|-------|-----------|------------|-------|------|----------|
| `all-MiniLM-L6-v2` | 384 | 512 | Fast | Free | Current - good balance |
| `all-mpnet-base-v2` | 768 | 512 | Medium | Free | Better accuracy, slower |
| `text-embedding-ada-002` | 1536 | 8191 | Slow | Paid | Best accuracy, long texts |
| `text-embedding-3-small` | 1536 | 8191 | Slow | Paid | OpenAI latest, cheaper |
| `text-embedding-3-large` | 3072 | 8191 | Slow | Paid | Best accuracy overall |

## Running the Project

### 1. API
```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Celery worker (required for uploads + gmail sync)
```bash
uv run celery -A app.core.celery_app.celery_app worker -l info -P solo
# or on Linux/macOS:
uv run celery -A app.core.celery_app.celery_app worker -l info
```

### 3. Celery beat (required for the 30-second Gmail scheduler)
```bash
uv run celery -A app.core.celery_app.celery_app beat -l info
```

> All three processes (API, worker, beat) need `REDIS_URL` reachable. The Beat schedule entry is `gmail-sync-every-30-seconds` defined in `app/core/celery_app.py`.

## Migrations
```bash
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

## Known Issues / Notes

- `init_db()` on startup only calls `create_all` for `User` and `TokenBlacklist`. `documents` and `gmail_messages` require `alembic upgrade head` — fresh deployments will 500 without it.
- `gmail_sync_service.sync_user_emails` runs LLM summarization **inline** in the worker. A failed OpenAI call fails the whole batch (no per-message retry). The project plan implies this should be moved to a separate Celery task.
- CORS is wide open (`allow_origins=["*"]` with `allow_credentials=True`) — fine for dev, tighten for prod.
- `google-genai` and `fastapi-sso` are installed but unused.
- Stale `celerybeat-schedule*` files are tracked in the repo — should be gitignored.
- `.env` and `credential.json` (looks like a Google service-account key) are committed; should be gitignored.
- Several `__pycache__` files reference `gmail_router.py`, `webhook_router.py`, `debug_router.py`, and a `gemini_service.py` — the source files are not present and they are not registered in `main.py`.
- `app/tasks/document_processing_task.py` creates a fresh `create_async_engine` per task — do not refactor to use the shared `engine` from `app.core.database` without addressing the loop-isolation rationale.
- No automated tests exist. `project.md` outlines unit/integration coverage targets for the upcoming project-clustering feature.
