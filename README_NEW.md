# Sales Agent API

A production-ready FastAPI backend for user authentication, Google OAuth/Gmail integration with scheduled email sync, document uploads, and asynchronous processing.

## Key Features

- JWT authentication with email/password and Google OAuth login
- Access token refresh and logout with token blacklist support
- User profile management (`GET /users/me`, `PATCH /users/me`, `DELETE /users/me`)
- **Centralized Gmail scheduler** — Automatic email sync every 5 minutes for users in working hours (9 AM–6 PM local timezone)
- Timezone-aware scheduling with IANA timezone support
- Incremental email synchronization using Gmail API `history.list()`
- Duplicate prevention with unique Gmail message ID constraints
- Document storage with automatic processing via Celery
- PostgreSQL database with SQLAlchemy ORM and Alembic migrations

## Architecture — Scheduler-Based Gmail Sync

Instead of using Gmail Watch Pub/Sub, the system uses a centralized scheduler:

```
┌─────────────────────────────────────────────────────────────────┐
│ Celery Beat Scheduler (runs every 5 minutes)                    │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ 1. Get all users with Gmail connected                    │   │
│ │ 2. For each user:                                         │   │
│ │    - Convert UTC to user's timezone                      │   │
│ │    - If local time 09:00–18:00, dispatch task           │   │
│ └───────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┴─────────────┐
              ↓                          ↓
    ┌─────────────────────┐  ┌──────────────────────┐
    │ Worker Task 1       │  │ Worker Task 2        │
    │ (User 1 sync)       │  │ (User 2 sync)        │
    │                     │  │                      │
    │ - Fetch emails      │  │ - Fetch emails       │
    │ - Deduplicate       │  │ - Deduplicate        │
    │ - Store Documents   │  │ - Store Documents    │
    └─────────────────────┘  └──────────────────────┘
              │                          │
              └────────────┬─────────────┘
                           ↓
        ┌──────────────────────────────┐
        │ Document Processing Queue    │
        │ (Async LLM summarization)    │
        └──────────────────────────────┘
```

## Project Structure

- `app/main.py` — FastAPI application entry point
- `app/core/`
  - `config.py` — Configuration via environment variables
  - `database.py` — Async PostgreSQL setup
  - `celery_app.py` — Celery and Beat scheduler configuration
- `app/dependencies/` — Request dependencies and auth guard
- `app/models/` — SQLAlchemy ORM models (User, Document, GmailMessage)
- `app/repositories/` — Data access layer
- `app/routers/` — API endpoint definitions
- `app/schemas/` — Pydantic request/response models
- `app/services/` — Gmail sync, token refresh, user management
- `app/tasks/` — Celery tasks for scheduler and document processing

## Requirements

- Python 3.13+
- PostgreSQL 12+
- Redis 6+

## Installation

1. Clone the repository:

```bash
git clone <repo-url> sales_agent
cd sales_agent
```

2. Create and activate a Python environment:

```bash
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -e .
```

4. Create a `.env` file at the project root with required environment variables.

## Environment Variables

Create a `.env` file with:

```env
# Database
DATABASE_URI=postgresql+asyncpg://user:password@localhost:5432/sales_agent

# JWT
SECRET_KEY=your-super-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Google OAuth
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# Redis
REDIS_URL=redis://localhost:6379/0
```

## Database Migrations

Initialize the database with Alembic:

```bash
# Generate migrations (if needed)
alembic revision --autogenerate -m "describe change"

# Apply migrations
alembic upgrade head

# View migration status
alembic current
```

## Running the Application

### FastAPI Server

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or with standard pip:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Celery Worker

In a separate terminal:

```bash
celery -A app.core.celery_app worker --loglevel=info
```

### Celery Beat Scheduler

In another terminal (starts the 5-minute scheduler):

```bash
celery -A app.core.celery_app beat --loglevel=info
```

### Redis Server

Ensure Redis is running (required by Celery):

```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or locally (if installed)
redis-server
```

## API Endpoints

### Authentication

- `POST /auth/register` — Register a new user
- `POST /auth/token` — OAuth2 password flow token endpoint
- `POST /auth/login` — Login with email/password
- `GET /auth/google/login` — Get Google OAuth authorization URL
- `GET /auth/google/callback` — Exchange Google auth code for JWT tokens
- `POST /auth/refresh` — Refresh access token using refresh token
- `POST /auth/logout` — Revoke current access token

### User Profile

- `GET /users/me` — Get current user profile (includes timezone)
- `PATCH /users/me` — Update profile fields (email, username, password, timezone)
- `DELETE /users/me` — Soft delete user account and revoke token

### Documents

- `GET /documents/` — List documents for current user
- `GET /documents/{document_id}` — Get specific document

## Gmail Integration Flow

1. **User Connects Gmail** (`GET /auth/google/login` + callback)
   - User is prompted to authorize
   - Tokens stored: `gmail_access_token`, `gmail_refresh_token`, `gmail_token_expiry`
   - Default timezone set to "UTC" (can be updated via `PATCH /users/me`)

2. **Scheduler Runs Every 5 Minutes**
   - Gets all users with connected Gmail
   - Checks user's local time (based on `timezone` field)
   - If 09:00–18:00 local time: dispatches `sync_user_emails` task

3. **Worker Syncs Emails**
   - Refreshes access token if needed
   - Uses `history.list()` for incremental sync (only new emails)
   - Deduplicates using `gmail_messages` table
   - Creates `Document` records for new emails
   - Updates `last_email_sync_at` timestamp

4. **Document Processing** (future)
   - Documents with status="pending" are picked up by processing workers
   - LLM summarization and other transformations applied

## Database Schema

### users table

- `id` (UUID, PK)
- `email` (unique, indexed)
- `username` (nullable)
- `hashed_password` (nullable)
- `is_active`, `is_verified`
- `google_id` (nullable)
- **NEW:** `timezone` (IANA format, default "UTC")
- **NEW:** `last_email_sync_at` (nullable datetime)
- Gmail fields: `gmail_access_token`, `gmail_refresh_token`, `gmail_token_expiry`, `gmail_history_id`
- Audit: `created_at`, `updated_at`, `deleted_at`

### documents table

- `id` (UUID, PK)
- `user_id` (FK to users)
- `source` (e.g., "gmail", "upload")
- `title`, `content`, `summary`, `file_type`
- `status` ("pending", "processed", "failed")
- `error_message`, `created_at`

### gmail_messages table (deduplication)

- `id` (UUID, PK)
- `user_id`, `gmail_message_id` (unique together)
- `subject`, `sender`, `received_at`
- `status` ("pending", "processed", "failed")
- `document_id` (FK to documents)
- `synced_at`

## Monitoring & Logging

Check Celery task status:

```bash
celery -A app.core.celery_app inspect active
celery -A app.core.celery_app inspect stats
```

View recent tasks:

```bash
redis-cli
> KEYS "*celery*"
> HGETALL celery-task-meta-*
```

## Architecture Decisions

### Centralized Scheduler vs. Per-User Watches

- **Why scheduler?** Scales to millions of users without N webhook subscriptions
- Gmail Watch has reliability/quota issues; polling is more predictable
- Every 5 minutes is a good balance between latency and load

### History ID for Incremental Sync

- Gmail API's `history.list()` is efficient; only fetches changed messages
- Fallback to full `messages.list()` on first sync if no history ID
- Prevents redundant API calls and reduces costs

### Deduplication with gmail_messages Table

- Separate table prevents Document duplicates if sync is interrupted
- Unique constraint on `(user_id, gmail_message_id)` prevents retries
- Tracks sync state independently from processed Documents

### Timezone in User Model

- IANA format (e.g., "Asia/Karachi") is standard and unambiguous
- Stored in User model for simplicity; can extend to user_preferences later
- Allows per-user working hour filtering

### Celery for Async Processing

- Integrates seamlessly with existing stack
- Redis for both broker and result backend
- Beat scheduler runs reliably with cron-like scheduling

## Fault Recovery & Data Consistency

- **Idempotent Processing:** Dedup via `gmail_message_id` ensures no duplicates
- **Resume on Restart:** `gmail_history_id` retained; scheduler picks up from last sync
- **Last Sync Timestamp:** `last_email_sync_at` tracks sync progress for debugging
- **Retry Logic:** Failed tasks retry up to 3 times with 60-second delays
- **Token Refresh:** Access tokens auto-refreshed before expiry (5-minute buffer)

## Troubleshooting

### No emails are being synced

1. Check user has Gmail tokens: `SELECT gmail_access_token FROM users WHERE email = 'user@example.com';`
2. Verify Celery Beat is running: `celery -A app.core.celery_app inspect active`
3. Check Redis connection: `redis-cli ping` (should return `PONG`)
4. Verify timezone is valid: `SELECT timezone FROM users WHERE email = 'user@example.com';`

### Gmail token expired error

- Token refresh happens automatically before each sync
- If still failing, manually trigger: `SELECT * FROM users WHERE gmail_token_expiry < NOW();`
- Re-authenticate by going through OAuth flow again

### Duplicate emails in documents

- Should not happen (unique constraint on `gmail_messages.gmail_message_id`)
- If corrupted, run: `DELETE FROM gmail_messages WHERE id NOT IN (SELECT MAX(id) FROM gmail_messages GROUP BY gmail_message_id);`

## Production Deployment

1. **Environment Variables:** Use secure secret management (AWS Secrets Manager, HashiCorp Vault)
2. **Celery Worker:** Run multiple worker processes for fault tolerance
3. **Beat Scheduler:** Run on dedicated machine or use `django-celery-beat` for database-backed scheduling
4. **Database:** Enable PostgreSQL connection pooling (PgBouncer)
5. **Redis:** Deploy with persistence and replication
6. **Monitoring:** Use tools like Flower, Sentry, or New Relic to track tasks and errors
7. **Logging:** Centralize logs (ELK Stack, Datadog, CloudWatch)

## Notes

- Emails are synced only during working hours (9 AM–6 PM in user's local timezone)
- Full email body is stored (up to 5000 chars) for LLM summarization
- Gmail API rate limit is ~100K messages/user/day; monitor quota if needed
- Token expiry includes 5-minute buffer for safety

## Contact

For questions or improvements, refer to the architecture documentation or open an issue.
