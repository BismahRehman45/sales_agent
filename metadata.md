# Sales Agent API — Metadata

## Project Overview

A production-ready FastAPI backend for an **AI sales-agent** product that processes emails and documents, automatically clustering them into projects using embeddings and RAG (Retrieval-Augmented Generation).

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Framework** | FastAPI (async) |
| **Database** | PostgreSQL + asyncpg + SQLAlchemy 2.0 |
| **Migrations** | Alembic |
| **Auth** | JWT (python-jose) + Google OAuth |
| **Background Jobs** | Celery + Redis |
| **LLM** | OpenAI-compatible API (Groq) |
| **Embeddings** | sentence-transformers/all-MiniLM-L6-v2 (local, free) |
| **Vector Search** | pgvector (PostgreSQL extension) |

---

## Features Implemented

### 1. Authentication System

| Feature | Description |
|---------|-------------|
| JWT Tokens | Access + refresh token authentication |
| Google OAuth | Login with Google, Gmail readonly scope |
| Token Blacklist | Server-side token revocation |
| Soft Delete | Users are never removed from DB |

**Endpoints:**
```
POST /auth/register      → Register with email/password
POST /auth/login         → JSON login
POST /auth/token         → OAuth2 password flow
POST /auth/refresh       → Refresh access token
POST /auth/logout        → Blacklist current token
GET  /auth/google/login  → Get Google OAuth URL
GET  /auth/google/callback → OAuth callback
```

---

### 2. User Profile Management

| Feature | Description |
|---------|-------------|
| Profile CRUD | Get, update, delete user profile |
| Timezone Support | Per-user timezone for scheduler |
| Gmail Integration | Store Gmail OAuth tokens |

**Endpoints:**
```
GET    /users/me    → Get current user
PATCH  /users/me    → Update profile
DELETE /users/me    → Soft delete account
```

---

### 3. Document Management

| Feature | Description |
|---------|-------------|
| File Upload | Support `.txt`, `.pdf`, `.docx` (≤10 MB) |
| Text Extraction | PDF (pdfplumber), DOCX (python-docx), TXT |
| LLM Summarization | Auto-generate summaries |
| Project Linking | Documents linked to projects via junction table |
| Status Tracking | `pending` → `processing` → `processed`/`failed` |

**Endpoints:**
```
POST /documents/upload    → Upload file with project_id
GET  /documents           → List user documents
GET  /documents/{id}      → Get document details
```

**Processing Pipeline:**
```
Upload → Validate → Save to disk → Create Document (pending)
  → Celery Task: Extract text → Summarize (LLM) → Update Project RAG
```

---

### 4. Gmail Sync

| Feature | Description |
|---------|-------------|
| Incremental Sync | Uses `history.list()` API for efficiency |
| Timezone-Aware | Only sync during working hours (9 AM - 6 PM) |
| Deduplication | Prevents duplicate email processing |
| Token Refresh | Auto-refresh expired tokens |

**Scheduler:**
```
Celery Beat (every 30 seconds)
  → Filter users by timezone + working hours
  → Enqueue sync_user_emails task
```

**Sync Flow:**
```
Fetch emails → Dedup (gmail_messages table)
  → Create Document → LLM Summarize → Link to GmailMessage
  → Enqueue Project Matching task
```

---

### 5. Project Clustering (RAG)

| Feature | Description |
|---------|-------------|
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 (384-dim) |
| Vector Search | pgvector cosine similarity |
| Auto-Clustering | Group related emails by sender + topic |
| Threshold | 50% similarity to match existing project |

**How It Works:**
```
New email arrives
  → Embed summary → 384-dim vector
  → pgvector search: same user + sender
  → Similarity ≥ 50% → Add to existing project
  → Similarity < 50% → Create new project (LLM generates name)
```

**Endpoints:**
```
GET    /projects              → List projects (filter: open/closed/all)
GET    /projects/open         → List only open projects
GET    /projects/{id}         → Get project details with RAG
PATCH  /projects/{id}         → Update project
DELETE /projects/{id}         → Delete project
POST   /projects/{id}/close   → Close project
POST   /projects/{id}/reopen  → Reopen project
```

---

### 6. Project Classification

| Feature | Description |
|---------|-------------|
| LLM Classification | Classify as `lead` or `sale_opportunity` |
| Confidence Score | 0.0 - 1.0 confidence rating |
| Reasoning | Text explanation of classification |
| Auto-Trigger | Runs after project creation/update |

**Classification Criteria:**
- **lead**: Initial inquiry, cold outreach, no buying signals
- **sale_opportunity**: Active deal, pricing discussions, contract negotiations

---

### 7. BANT Analysis (NEW)

| Feature | Description |
|---------|-------------|
| Full Text Analysis | Detailed text for each BANT component |
| Separate Prompts | Dedicated LLM prompt for Budget, Authority, Need, Timeline |
| Auto-Trigger | Runs after classification as `sale_opportunity` |
| Re-Analysis | Re-runs when new emails are added to project |
| Overall Summary | LLM-generated summary of BANT qualification |

**BANT Components:**

| Component | Analysis Focus |
|-----------|----------------|
| **Budget** | Budget mentions, allocations, pricing discussions, cost sensitivity |
| **Authority** | Decision-makers, org hierarchy, approval process |
| **Need** | Pain points, requirements, use cases, urgency |
| **Timeline** | Deadlines, implementation schedule, go-live dates |

**Database Table:**
```sql
CREATE TABLE project_bant (
    id UUID PRIMARY KEY,
    project_id UUID UNIQUE REFERENCES projects(id),
    budget TEXT,
    authority TEXT,
    need TEXT,
    timeline TEXT,
    summary TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);
```

**Celery Task Flow:**
```
classify_project_type()
  → if type == "sale_opportunity"
    → enqueue analyze_project_bant
      → LLM analyzes Budget (separate call)
      → LLM analyzes Authority (separate call)
      → LLM analyzes Need (separate call)
      → LLM analyzes Timeline (separate call)
      → LLM generates overall summary
      → Save to project_bant table
```

**Re-Analysis Triggers:**
1. After classification as `sale_opportunity`
2. When new emails are added to project (`_update_project_rag`)
3. When uploaded documents are added (`update_upload_project_rag`)

**Endpoint:**
```
GET /projects/{id}/bant    → Get BANT analysis for a project
```

**Response Format:**
```json
{
  "project_id": "uuid",
  "budget": "Client has $50K allocated for Q3...",
  "authority": "Contact is VP with buying power...",
  "need": "Pain point: manual process wastes 10hrs/week...",
  "timeline": "Target implementation Q3 2026...",
  "summary": "Strong sale opportunity...",
  "created_at": "2026-06-04T10:00:00Z",
  "updated_at": "2026-06-04T10:00:00Z"
}
```

---

## Database Schema

### Tables

| Table | Purpose |
|-------|---------|
| `users` | User profiles with Gmail tokens, timezone |
| `documents` | Processed emails/uploads with summaries |
| `gmail_messages` | Deduplication tracking for Gmail sync |
| `projects` | Clustered conversations with pgvector embeddings |
| `project_documents` | Junction table linking projects to documents |
| `project_bant` | BANT analysis for sale opportunities |
| `token_blacklist` | JWT revocation |

### Migrations

| Migration | Description |
|-----------|-------------|
| `add_user_models` | Create users table |
| `create_token_blacklist` | Create token_blacklist table |
| `add_gmail_scheduler_fields` | Add timezone, last_email_sync_at to users |
| `add_document_file_path` | Add file_path to documents |
| `add_sender_email_to_documents` | Add sender_email to documents |
| `add_projects_table` | Create projects table with pgvector |
| `add_project_documents_table` | Create project_documents junction table |
| `add_project_bant_table` | Create project_bant table |

---

## API Endpoints Summary

### Authentication (`/auth`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | No | Register with email/password |
| POST | `/auth/login` | No | JSON login |
| POST | `/auth/token` | No | OAuth2 password flow |
| POST | `/auth/refresh` | No | Refresh access token |
| POST | `/auth/logout` | Bearer | Blacklist current token |
| GET | `/auth/google/login` | No | Get Google OAuth URL |
| GET | `/auth/google/callback` | No | OAuth callback |

### Users (`/users`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/users/me` | JWT | Get current user |
| PATCH | `/users/me` | JWT | Update profile |
| DELETE | `/users/me` | JWT | Soft delete account |

### Documents (`/documents`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/documents/upload` | JWT | Upload file with project_id |
| GET | `/documents` | JWT | List user documents |
| GET | `/documents/{id}` | JWT | Get document details |

### Projects (`/projects`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/projects` | JWT | List projects (filter: open/closed/all) |
| GET | `/projects/open` | JWT | List only open projects |
| GET | `/projects/{id}` | JWT | Get project details with RAG |
| PATCH | `/projects/{id}` | JWT | Update project |
| DELETE | `/projects/{id}` | JWT | Delete project |
| POST | `/projects/{id}/close` | JWT | Close project |
| POST | `/projects/{id}/reopen` | JWT | Reopen project |
| GET | `/projects/{id}/bant` | JWT | Get BANT analysis |

---

## Celery Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `schedule_gmail_sync` | Every 30 seconds | Filter users, enqueue sync |
| `sync_user_emails` | On-demand | Fetch Gmail emails, create documents |
| `process_uploaded_document` | On-demand | Extract text from uploaded files |
| `match_document_to_project` | On-demand | Embed document, find/create project |
| `classify_project_type` | On-demand | LLM classifies project type |
| `analyze_project_bant` | On-demand | LLM analyzes BANT components |

---

## Configuration (.env)

| Variable | Description |
|----------|-------------|
| `DATABASE_URI` | PostgreSQL async DSN |
| `REDIS_URL` | Celery broker/backend |
| `SECRET_KEY` | JWT signing secret |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL |
| `OPENAI_API_KEY` | LLM API key |
| `OPENAI_API_URL` | LLM API endpoint |
| `OPENAI_MODEL` | LLM model name |
| `EMBEDDING_MODEL` | Embedding model name |
| `PROJECT_MATCH_THRESHOLD` | Similarity threshold (0.5) |

---

## Running the Project

### 1. Install Dependencies
```bash
uv sync
```

### 2. Run Migrations
```bash
uv run alembic upgrade head
```

### 3. Start API Server
```bash
uv run uvicorn app.main:app --reload --port 8000
```

### 4. Start Celery Worker
```bash
uv run celery -A app.core.celery_app worker -l info -P solo
```

### 5. Start Celery Beat (Scheduler)
```bash
uv run celery -A app.core.celery_app beat -l info
```

---

## File Structure

```
app/
├── core/
│   ├── config.py           # Pydantic Settings
│   ├── database.py         # Async SQLAlchemy engine
│   └── celery_app.py       # Celery configuration
├── models/
│   ├── user.py             # User model
│   ├── document.py         # Document model
│   ├── project.py          # Project model (pgvector)
│   ├── project_bant.py     # BANT analysis model
│   ├── project_document.py # Junction table
│   ├── gmail_message.py    # Gmail dedup model
│   └── token_blacklist.py  # JWT blacklist
├── routers/
│   ├── auth.py             # Authentication endpoints
│   ├── user_router.py      # User profile endpoints
│   ├── document_router.py  # Document endpoints
│   └── project_router.py   # Project + BANT endpoints
├── services/
│   ├── user_service.py     # User CRUD logic
│   ├── jwt_service.py      # JWT encode/decode
│   ├── google_oauth_service.py # Google OAuth
│   ├── gmail_token_service.py  # Gmail token refresh
│   ├── gmail_sync_service.py   # Gmail sync logic
│   ├── document_service.py     # Document upload logic
│   ├── llm_service.py          # LLM calls (summarize, classify, BANT)
│   ├── embedding_service.py    # MiniLM embeddings
│   └── project_service.py      # Project matching + RAG
├── repositories/
│   ├── user_repository.py
│   ├── token_repository.py
│   ├── document_repository.py
│   ├── gmail_message_repository.py
│   └── project_repository.py  # Includes BANT CRUD
├── schemas/
│   ├── auth.py
│   ├── user_schema.py
│   ├── document_schema.py
│   └── project_schema.py  # Includes BantResponse
├── tasks/
│   ├── gmail_scheduler_task.py
│   ├── document_processing_task.py
│   ├── project_matching_task.py
│   ├── project_classification_task.py
│   └── bant_analysis_task.py    # NEW: BANT analysis
├── dependencies/
│   └── auth.py
└── main.py
```

---

## Recent Changes (This Session)

### Added: BANT Analysis Feature

| File | Change |
|------|--------|
| `app/models/project_bant.py` | NEW: BANT database model |
| `app/tasks/bant_analysis_task.py` | NEW: BANT Celery task |
| `alembic/versions/add_project_bant_table.py` | NEW: BANT table migration |
| `app/services/llm_service.py` | Added `analyze_bant()` and `analyze_bant_component()` |
| `app/repositories/project_repository.py` | Added BANT CRUD functions |
| `app/schemas/project_schema.py` | Added `BantResponse` schema |
| `app/routers/project_router.py` | Added `GET /projects/{id}/bant` endpoint |
| `app/tasks/project_classification_task.py` | Added BANT trigger after sale_opportunity |
| `app/services/project_service.py` | Added BANT re-analysis on project update |
| `app/core/celery_app.py` | Registered `bant_analysis_task` |

### Added: Open Projects Endpoint

| File | Change |
|------|--------|
| `app/routers/project_router.py` | Added `GET /projects/open` endpoint |

---

## Known Issues / Notes

- CORS is wide open (`allow_origins=["*"]`) — tighten for production
- No automated tests exist
- `.env` and `credential.json` are committed — should be gitignored
- Several `__pycache__` files reference removed routers
