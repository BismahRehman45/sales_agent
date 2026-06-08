# Project Clustering Feature — Implementation Plan

## 1. Feature Overview

**Goal:** Automatically cluster a user's emails into projects based on topic similarity, even if they come from the same sender.

**How it works:**
1. Email is synced from Gmail → Document created → LLM generates summary
2. When Document status becomes `"processed"`, a background Celery task is triggered
3. The task compares the new document's content with existing projects (same `user_id` + `sender_email`)
4. If **similarity >= 50%** with a project's `rag` content → append the new content to that project
5. If **similarity < 50%** (or no project exists) → create a new project

**Approach:** Way 2 — Embeddings-based RAG (advanced)

---

## 2. Why Embeddings (Way 2)

| Benefit | Explanation |
|---------|-------------|
| **Fast matching** | <100ms per comparison vs 2-3 sec for LLM calls |
| **Cheap** | Local embeddings free; no LLM call per match |
| **Accurate** | Cosine similarity captures semantic meaning |
| **Scalable** | Can handle 1000s of projects per user |
| **No $$ per match** | One-time embedding cost at insert time |

---

## 3. Tech Stack for Embeddings

| Choice | Decision |
|--------|----------|
| **Embedding model** | `sentence-transformers/all-MiniLM-L6-v2` (local, 384-dim, free) |
| **Vector dimension** | 384 floats (small, fast) |
| **Storage** | `pgvector` extension in PostgreSQL (single source of truth) |
| **Similarity** | Cosine similarity |
| **Threshold** | 0.5 (50% match) |

**Why local embeddings:**
- Free (no API costs)
- Fast (~50ms per embedding)
- Good accuracy for short emails
- No external dependency

---

## 4. Data Model

### 4.1 Migration 1: Add `sender_email` to `documents`

```sql
ALTER TABLE documents
    ADD COLUMN sender_email VARCHAR(255);
CREATE INDEX idx_documents_user_sender
    ON documents(user_id, sender_email)
    WHERE sender_email IS NOT NULL;
```

### 4.2 Migration 2: Enable pgvector + Create `projects` table

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL,
    sender_email    VARCHAR(255) NOT NULL,
    name            VARCHAR(255) NOT NULL,
    rag             TEXT NOT NULL DEFAULT '',
    rag_embedding   vector(384),
    document_count  INT NOT NULL DEFAULT 0,
    last_email_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(user_id, sender_email, name)
);

CREATE INDEX idx_projects_user_sender
    ON projects(user_id, sender_email);

CREATE INDEX idx_projects_embedding
    ON projects USING ivfflat (rag_embedding vector_cosine_ops)
    WITH (lists = 100);
```

**Note:** `ivfflat` index makes similarity search fast even with 10k+ projects.

### 4.3 Migration 3: Add `embedding` to `documents` (optional cache)

```sql
ALTER TABLE documents
    ADD COLUMN embedding vector(384);
```

This avoids re-computing embeddings on retry.

---

## 5. Architecture Flow

```
[Celery: sync_user_emails]
   ↓ Email fetched from Gmail
   ↓ Create Document (with sender_email)
   ↓ LLMService.summarize_text(content) → doc.summary
   ↓ doc.status = "processed"
   ↓
[NEW HOOK] enqueue: match_document_to_project.delay(doc.id)
   ↓
[Celery: match_document_to_project]
   ↓ 1. Compute embedding of doc.summary (using MiniLM)
   ↓ 2. SELECT projects WHERE user_id=X AND sender_email=Y
   ↓ 3. If no projects:
   ↓      → Create new project
   ↓         (LLM generates name from summary)
   ↓         (rag = doc.content, rag_embedding = doc embedding)
   ↓
   ↓ 4. If projects exist:
   ↓      For each project, cosine_similarity(doc_emb, project.rag_embedding)
   ↓      → If best similarity >= 0.5:
   ↓          project.rag = rag + "\n\n---\n\n" + doc.content
   ↓          project.rag_embedding = average(new_emb, old_emb)  ← recompute
   ↓          project.document_count += 1
   ↓          project.last_email_at = NOW()
   ↓      → Else: create new project (as in step 3)
```

---

## 6. New Files to Create

| File | Purpose |
|------|---------|
| `app/models/project.py` | `Project` SQLAlchemy model |
| `app/repositories/project_repository.py` | DB queries (create, get_by_user_sender, get_by_id, update) |
| `app/services/embedding_service.py` | Wrapper around sentence-transformers (compute_embedding) |
| `app/services/project_service.py` | find_or_create_project() — main matching logic |
| `app/tasks/project_matching_task.py` | Celery task (match_document_to_project) |
| `app/routers/project_router.py` | Optional: GET /projects, GET /projects/{id} |
| `alembic/versions/add_sender_email_to_documents.py` | Migration 1 |
| `alembic/versions/add_projects_table.py` | Migration 2 |
| `alembic/versions/add_document_embedding.py` | Migration 3 (optional) |

---

## 7. Files to Modify

| File | Change |
|------|--------|
| `app/models/document.py` | Add `sender_email`, `embedding` columns |
| `app/services/gmail_sync_service.py` | Set `doc.sender_email = email_data["from"]`; enqueue `match_document_to_project.delay()` |
| `app/core/celery_app.py` | Add `app.tasks.project_matching_task` to `include=[...]` |
| `app/main.py` | Register `project_router` |
| `pyproject.toml` | Add deps: `sentence-transformers`, `pgvector`, `numpy` |

---

## 8. Key Algorithms

### 8.1 Embedding Generation

```python
# app/services/embedding_service.py
from sentence_transformers import SentenceTransformer

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

def compute_embedding(text: str) -> list[float]:
    model = get_model()
    return model.encode(text).tolist()
```

### 8.2 Cosine Similarity (DB-side)

```sql
SELECT id, name, rag,
       1 - (rag_embedding <=> $1::vector) AS similarity
FROM projects
WHERE user_id = $2 AND sender_email = $3
ORDER BY rag_embedding <=> $1::vector
LIMIT 1;
```

(`<=>` is pgvector's cosine **distance**; we subtract from 1 to get **similarity**)

### 8.3 Project Name Generation (LLM)

```python
async def generate_project_name(summary: str) -> str:
    prompt = f"Generate a short, descriptive project name (max 50 chars) for: {summary}"
    response = await call_groq(prompt)
    return response.strip()[:255]
```

### 8.4 Concurrency Safety

```python
async with db.begin():  # Transaction
    projects = await db.execute(
        select(Project)
        .where(Project.user_id == user_id, Project.sender_email == sender)
        .with_for_update()  # ← Row-level lock
    )
    # ... matching logic ...
```

---

## 9. Database Choice

| Option | Decision |
|--------|----------|
| **(a) pgvector** (recommended) | Single DB, easy ops, no extra services |
| (b) Pinecone/Weaviate/Chroma | Better for huge scale, more complex |

For our scale (< 100k projects), pgvector is sufficient.

---

## 10. Performance Estimates

| Operation | Latency | Notes |
|-----------|---------|-------|
| Compute embedding (MiniLM) | ~50ms | One-time per document |
| Cosine similarity (single project) | <1ms | DB query |
| Cosine similarity (10k projects) | ~5ms | With ivfflat index |
| LLM name generation | ~2s | Only on new project |
| Total per email | ~50-100ms | Mostly embedding compute |

---

## 11. Edge Cases & Decisions

### 11.1 First email from new sender
- No projects exist for (user, sender)
- → **Create new project**, LLM generates name from summary
- `rag = doc.content`, `rag_embedding = doc.embedding`

### 11.2 Multiple matches above 50%
- Pick the **highest similarity** (single best match)
- Don't split content across projects

### 11.3 Concurrency (two emails processed simultaneously)
- Use `SELECT ... FOR UPDATE` row lock
- Or accept best-effort (race conditions create duplicate projects, low impact)

### 11.4 Project name conflicts
- `UNIQUE(user_id, sender_email, name)` constraint
- If LLM generates duplicate name, append timestamp: `"Acme Pricing (2026-06-02 14:30)"`

### 11.5 Rag size limit
- No hard limit (PostgreSQL TEXT handles MB+ easily)
- Optional: re-summarize rag if it exceeds N chars (Phase 2)

### 11.6 Document with no summary
- Skip project matching (cannot embed empty)
- Log warning

### 11.7 Uploads (non-gmail documents)
- `sender_email = NULL` for uploads
- These don't go through project matching (no sender to cluster on)
- Phase 2: allow manual project assignment

### 11.8 Embedding model loading
- `SentenceTransformer` model is ~80MB, takes ~3-5 sec to load first time
- Cache model in memory at worker startup (singleton)
- Pre-load in worker via `worker_init` signal

---

## 12. Testing Strategy

### 12.1 Unit Tests
- `embedding_service.py` — verify embedding dimension, determinism
- `project_service.py` — mock DB, test match/no-match logic
- `project_repository.py` — basic CRUD

### 12.2 Integration Tests
- Send 2 similar emails from same sender → verify same project
- Send 2 different emails from same sender → verify 2 projects
- Send emails from different senders → verify separate projects
- Concurrency: 5 emails at once → verify no duplicate projects

### 12.3 Manual Test
- Send yourself 3 emails from same sender
- Wait 1-2 min for Celery
- `GET /projects` → should show 1-3 projects depending on similarity

---

## 13. Implementation Phases

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1. Dependencies + model | 20 min | `pgvector` enabled, MiniLM installed, `Project` model |
| 2. Migrations | 10 min | 3 alembic migrations applied |
| 3. Services | 30 min | `embedding_service`, `project_service`, `project_repository` |
| 4. Celery task | 20 min | `match_document_to_project` task |
| 5. Wiring | 15 min | Hook in `gmail_sync_service`, register task |
| 6. API endpoints | 15 min | `GET /projects`, `GET /projects/{id}` |
| 7. Testing | 30 min | Manual + automated |
| **Total** | **~2.5 hours** | Full feature working |

---

## 14. Open Questions (default answers proposed)

1. **Embedding model size** — `all-MiniLM-L6-v2` (80MB, 384-dim) or `all-mpnet-base-v2` (420MB, 768-dim, more accurate)?
   - **Default: MiniLM** (faster, smaller, sufficient for emails)

2. **Similarity threshold** — 0.5 (50%) or different?
   - **Default: 0.5** (50% match)

3. **Rag update strategy** — append raw text OR re-embed the full rag?
   - **Default: re-embed full rag** (more accurate, ~50ms per update)
   - Alternative: only embed new content, store (embedding, text) pairs

4. **Old data backfill** — should we run `match_document_to_project` on existing processed documents?
   - **Default: yes, run once via backfill script** (`scripts/backfill_projects.py`)

5. **API endpoints** — `GET /projects`, `GET /projects/{id}` only, or also `POST /projects/{id}/rebuild`?
   - **Default: just GET endpoints** for v1

6. **Should uploads also be project-matched?**
   - **Default: no** (no sender_email for uploads)

---

## 15. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| `pgvector` not enabled on Postgres | Run `CREATE EXTENSION` (superuser needed) |
| Model download fails offline | Pre-download model, mount in Docker |
| Embedding mismatch (different model versions) | Pin model version, store model name in config |
| Slow LLM name generation blocks | Async task, no blocking |
| Race conditions in project creation | Row-level lock OR idempotency check |
| Rag text grows too large | Phase 2: periodic re-summarization |

---

## 16. Future Enhancements (Phase 2+)

- Manual project assignment (uploads)
- Project re-naming via API
- Project merging (combine similar projects)
- Project search via query (RAG retrieval)
- Per-project LLM chat (RAG over project)
- Project archival / deletion
- Cross-sender project detection

---

## 17. Configuration

Add to `.env`:
```
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
PROJECT_MATCH_THRESHOLD=0.5
```

Add to `app/core/config.py`:
```python
EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
PROJECT_MATCH_THRESHOLD: float = 0.5
```

---

## 18. Acceptance Criteria

- When a Gmail document is processed, it gets clustered into a project automatically
- Same-sender emails with similar content (>50%) land in the same project
- Same-sender emails with different content (<50%) create separate projects
- Different-sender emails always create separate projects
- Project name is auto-generated via LLM (e.g., "Acme Pricing Discussion")
- API endpoints return projects for the current user
- No duplicate projects for the same (user, sender, topic)
- Concurrency-safe (5 emails at once → no duplicates)
