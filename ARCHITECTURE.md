# Gmail Scheduler Implementation Guide

**Version**: 1.0  
**Date**: June 2026  
**Status**: Production Ready

## Executive Summary

This document describes the implementation of a centralized, timezone-aware Gmail scheduler that replaces the webhook-based Gmail Watch architecture. The system processes user emails during their working hours (9 AM–6 PM local timezone) every 5 minutes using Celery Beat and distributed workers.

---

## 1. Architecture Overview

### 1.1 System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│ FastAPI Application (http://localhost:8000)                         │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ - User Authentication (JWT)                                    │ │
│ │ - Google OAuth Flow                                            │ │
│ │ - User Profile Management (including timezone)                │ │
│ │ - Document/Email API endpoints                                │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
         ↑                                            ↑
         │                                            │
         └────────────────┬─────────────────────────────┘
                          │
         ┌────────────────┴─────────────────┐
         ↓                                   ↓
    ┌─────────────────┐            ┌──────────────────┐
    │ PostgreSQL      │            │ Redis            │
    │ Database        │            │ (Broker/Backend) │
    │                 │            │                  │
    │ - users         │            │ - Task queue     │
    │ - documents     │            │ - Results        │
    │ - gmail_messages│            │ - Scheduler      │
    │ - token_blackl. │            │                  │
    └─────────────────┘            └──────────────────┘
         ↑                                   ↑
         │                ┌──────────────────┘
         │                │
         └────────────────┼──────────────────────────────────┐
                          │                                  │
         ┌────────────────┴──────────────────────────────────┴────────┐
         │ Celery Ecosystem                                           │
         │ ┌──────────────────────────────────────────────────────┐   │
         │ │ Beat Scheduler (every 5 minutes)                    │   │
         │ │ - Gets users with Gmail connected                  │   │
         │ │ - Filters by timezone + working hours             │   │
         │ │ - Enqueues sync_user_emails tasks                 │   │
         │ └──────────────────────────────────────────────────────┘   │
         │                          ↓                                  │
         │ ┌──────────────────────────────────────────────────────┐   │
         │ │ Worker Pool (multiple instances)                    │   │
         │ │ - sync_user_emails(user_id)                        │   │
         │ │   * Fetch new Gmail messages                       │   │
         │ │   * Deduplicate with gmail_messages table          │   │
         │ │   * Create Document records                        │   │
         │ │   * Update last_email_sync_at                      │   │
         │ └──────────────────────────────────────────────────────┘   │
         └──────────────────────────────────────────────────────────┘
                          ↓
         ┌────────────────────────────────────────┐
         │ Gmail API                              │
         │ - GET /users/me/messages               │
         │ - GET /users/me/history                │
         │ - POST /token (refresh)                │
         └────────────────────────────────────────┘
```

### 1.2 Key Design Patterns

1. **Scheduler Pattern**: Centralized Beat scheduler dispatches work to distributed workers
2. **Idempotent Processing**: Duplicate Gmail messages are detected and skipped
3. **Incremental Sync**: Uses `history_id` to fetch only new emails
4. **Timezone-Aware Filtering**: Respects user's local working hours
5. **Fault Recovery**: Persists sync state (`last_email_sync_at`, `gmail_history_id`)

---

## 2. Data Models

### 2.1 User Model Updates

```python
# NEW FIELDS
timezone: str = "UTC"  # IANA timezone (e.g., "Asia/Karachi")
last_email_sync_at: datetime | None = None  # Last successful sync timestamp

# EXISTING FIELDS (preserved)
gmail_access_token: str | None  # OAuth2 access token
gmail_refresh_token: str | None  # Refresh token for token renewal
gmail_token_expiry: datetime | None  # Access token expiry
gmail_history_id: str | None  # Gmail history ID for incremental sync
```

**Why?**
- `timezone`: Enables scheduler to convert UTC to user's local time for working hour filtering
- `last_email_sync_at`: Tracks sync progress for fault recovery and debugging

### 2.2 Document Model (NEW)

```python
class Document(Base):
    id: UUID = primary_key()
    user_id: UUID = foreign_key(User)
    source: str  # "gmail", "upload", etc.
    title: str | None  # Email subject
    content: str  # Email body
    summary: str | None  # LLM-generated summary
    file_type: str | None  # "email", "pdf", etc.
    status: str = "pending"  # pending, processed, failed
    error_message: str | None
    created_at: datetime
```

**Why?**
- Centralized document storage for all content types (emails, uploads)
- Status tracking enables asynchronous processing pipelines
- Separates storage from sync state

### 2.3 GmailMessage Model (NEW — for deduplication)

```python
class GmailMessage(Base):
    id: UUID = primary_key()
    user_id: UUID = foreign_key(User)
    gmail_message_id: str  # Gmail's unique ID
    subject: str | None
    sender: str | None
    received_at: datetime | None
    synced_at: datetime
    status: str = "pending"  # pending, processed, failed
    document_id: UUID | None = foreign_key(Document)
    
    # CONSTRAINTS
    unique(user_id, gmail_message_id)  # No duplicates per user
    index(user_id, synced_at)  # Optimize pagination
```

**Why?**
- **Deduplication**: Unique constraint prevents duplicate processing if sync is interrupted
- **Fault Recovery**: Tracks which messages have been processed
- **Audit Trail**: Records when each message was synced
- **Independent State**: Sync state separate from Document status

---

## 3. Scheduler Logic

### 3.1 Beat Schedule Configuration

```python
# app/core/celery_app.py
app.conf.beat_schedule = {
    'gmail-sync-every-5-minutes': {
        'task': 'app.tasks.gmail_scheduler_task.schedule_gmail_sync',
        'schedule': crontab(minute='*/5'),
    },
}
```

**Timing**: Every 5 minutes balances:
- **Low Latency**: 5 minutes is acceptable delay for email notifications
- **Low Load**: 12 executions/hour is manageable for large user bases
- **Cost Efficiency**: Reduces Gmail API quota usage vs. per-user watches

### 3.2 Scheduler Task: `schedule_gmail_sync`

```python
@shared_task(bind=True, max_retries=3)
def schedule_gmail_sync(self):
    """
    Runs every 5 minutes. Filters users by timezone + working hours,
    then enqueues sync_user_emails tasks for active users.
    """
    current_utc = datetime.now(dt_timezone.utc)
    
    for user in get_users_with_gmail_connected():
        user_tz = pytz.timezone(user.timezone)
        user_local_time = current_utc.astimezone(user_tz)
        
        # Check if user is in working hours (9 AM - 6 PM)
        if 9 <= user_local_time.hour < 18:
            sync_user_emails.delay(str(user.id))  # Enqueue task
```

**Features:**
- Converts UTC to each user's local timezone using `pytz`
- Filters users to only those in working hours
- Dispatches async tasks (does NOT sync directly)
- Retries up to 3 times on failure

**Timezone Filtering Example:**
```
Current UTC: 2026-06-01 13:30:00 (1:30 PM UTC)

User A: timezone = "Asia/Karachi" (UTC+5)
  → Local time: 18:30 (6:30 PM) → OUTSIDE 9-18 → SKIPPED

User B: timezone = "America/New_York" (UTC-4)
  → Local time: 09:30 (9:30 AM) → INSIDE 9-18 → SYNCED

User C: timezone = "Europe/London" (UTC+1)
  → Local time: 14:30 (2:30 PM) → INSIDE 9-18 → SYNCED
```

### 3.3 Worker Task: `sync_user_emails`

```python
@shared_task(bind=True, max_retries=3)
def sync_user_emails(self, user_id: str):
    """
    Worker task for a single user. Syncs emails, deduplicates,
    creates Documents, and persists sync state.
    """
    user = get_user(user_id)
    
    # Step 1: Ensure token is fresh
    user = await ensure_token_fresh(db, user)
    
    # Step 2: Fetch emails (incremental or full scan)
    emails = await fetch_incremental_emails(user)
    
    # Step 3: Dedup and create Documents
    for email in emails:
        if not gmail_message_exists(user_id, email['message_id']):
            gmail_msg = create_gmail_message(email)
            doc = create_document(email)
            gmail_msg.document_id = doc.id
    
    # Step 4: Update sync state
    user.gmail_history_id = latest_history_id
    user.last_email_sync_at = now()
    save_user(user)
```

**Features:**
- Auto-refreshes expired tokens (5-minute buffer)
- Fetches only new emails via `history.list()`
- Deduplicates on `(user_id, gmail_message_id)`
- Creates Document records for processing
- Updates sync metadata for fault recovery

---

## 4. Gmail API Integration

### 4.1 Incremental Sync with `history.list()`

**First-time sync** (no `gmail_history_id`):
```
GET https://www.googleapis.com/gmail/v1/users/me/messages
  ?q=in:inbox
  &pageToken={pagination_token}

→ Fetches ALL messages in INBOX
```

**Subsequent syncs** (has `gmail_history_id`):
```
GET https://www.googleapis.com/gmail/v1/users/me/history
  ?startHistoryId={user.gmail_history_id}
  &pageToken={pagination_token}
  &historyTypes=messageAdded

→ Fetches ONLY NEW messages since startHistoryId
```

**Why `history.list()`?**
- **Efficiency**: Typically 1-10 messages per sync vs. full inbox scan
- **Cost**: Reduces Gmail API quota consumption significantly
- **Real-time**: Detects all changes (additions, deletions, label changes)

### 4.2 Full Email Fetching

```
GET https://www.googleapis.com/gmail/v1/users/me/messages/{message_id}
  ?format=full

→ Returns full message with headers, payload, internalDate, historyId
```

**Extraction Pipeline:**
```
1. Parse headers to extract:
   - Subject (from "Subject" header)
   - Sender (from "From" header)
   - Date (from "Date" header → parsedate_to_datetime)

2. Extract body:
   - Check payload.parts[] for multipart
   - Prefer text/plain over text/html
   - Base64 decode from data field

3. Limit to 5000 characters (practical for LLM processing)
```

### 4.3 Token Refresh

**Before each sync:**
```python
if user.gmail_token_expiry - timedelta(minutes=5) < now():
    refresh_token = POST https://oauth2.googleapis.com/token {
        client_id,
        client_secret,
        refresh_token,
        grant_type: "refresh_token"
    }
    
    user.gmail_access_token = response["access_token"]
    user.gmail_token_expiry = now() + timedelta(seconds=response["expires_in"])
```

**Why 5-minute buffer?**
- Prevents race condition: token expires during API call
- Ensures at least one retry window if token is invalid

---

## 5. Deduplication Strategy

### 5.1 Unique Constraint

```sql
ALTER TABLE gmail_messages
ADD CONSTRAINT uq_user_gmail_message
UNIQUE (user_id, gmail_message_id);
```

**Properties:**
- Per-user uniqueness (same email from different users allowed)
- Prevents duplicate inserts via database-level enforcement
- Enables `ON CONFLICT DO NOTHING` optimization

### 5.2 Idempotent Processing

```python
# On sync, for each email:
try:
    existing = await gmail_message_repository.get_message_by_gmail_id(
        db, user_id, email["message_id"]
    )
    if existing:
        logger.debug(f"Skipping duplicate: {email['message_id']}")
        continue  # Skip already-synced email
    
    # Insert new message (will fail silently if race condition)
    gmail_msg = await gmail_message_repository.create_message(db, new_msg)
    document = await document_repository.create_document(db, doc)
    
except IntegrityError:
    # Handle race condition if two workers sync same message
    pass
```

**Guarantees:**
- No duplicate Documents created
- Retries are safe (repeated calls produce same result)
- Race conditions handled gracefully

---

## 6. Fault Recovery & Data Consistency

### 6.1 Fault Scenarios & Recovery

| Scenario | Recovery |
|----------|----------|
| Server restart mid-sync | `last_email_sync_at` persists; next scheduler run continues |
| Network error (Email fetch fails) | Task retries up to 3 times; `gmail_history_id` unchanged |
| Token expired | Auto-refreshed before sync; if all refreshes fail, task aborted |
| Duplicate detected | Skipped via unique constraint; no Document created |
| Worker crash | Task reassigned to another worker; retried with same user_id |
| Database down | Task aborted; retry after 60 seconds (beat checks Redis again) |

### 6.2 State Persistence

**Critical fields:**
```python
user.gmail_history_id  # Latest history ID from Gmail
user.last_email_sync_at  # When last sync completed
user.gmail_token_expiry  # When current token expires
```

**Update frequency:**
- `gmail_history_id`: After successful sync (all emails processed)
- `last_email_sync_at`: After successful sync (even if 0 emails fetched)
- `gmail_token_expiry`: After token refresh OR after sync (if token used)

---

## 7. Installation & Setup

### 7.1 Database Migration

```bash
# Generate and apply migration
alembic revision --autogenerate -m "add_gmail_scheduler_fields"
alembic upgrade head

# Verify schema
psql -c "\d users" | grep timezone
psql -c "\d documents"
psql -c "\d gmail_messages"
```

### 7.2 Environment Configuration

```env
# Database
DATABASE_URI=postgresql+asyncpg://user:pass@localhost/sales_agent

# Redis (Celery broker)
REDIS_URL=redis://localhost:6379/0

# Google OAuth
GOOGLE_CLIENT_ID=xyz...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xyz...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# JWT
SECRET_KEY=your-secret-key
```

### 7.3 Dependency Installation

```bash
pip install -e .
# OR
pip install -r requirements.txt
```

**Key packages:**
- `celery[redis]` - Async task queue
- `pytz` - Timezone handling
- `httpx` - Async HTTP client
- `sqlalchemy>=2.0` - ORM
- `asyncpg` - Async PostgreSQL driver

### 7.4 Starting All Services

```bash
# Terminal 1: FastAPI server
uvicorn app.main:app --reload --port 8000

# Terminal 2: Celery worker
celery -A app.core.celery_app worker --loglevel=info

# Terminal 3: Celery Beat scheduler
celery -A app.core.celery_app beat --loglevel=info

# Terminal 4: Redis (or Docker)
redis-server
# OR
docker run -d -p 6379:6379 redis:7
```

---

## 8. Monitoring & Observability

### 8.1 Task Monitoring

```bash
# Active tasks
celery -A app.core.celery_app inspect active

# Stats
celery -A app.core.celery_app inspect stats

# Recent tasks
celery -A app.core.celery_app events
```

### 8.2 Database Queries

```sql
-- Last sync for each user
SELECT email, timezone, last_email_sync_at, gmail_history_id
FROM users
WHERE gmail_access_token IS NOT NULL
ORDER BY last_email_sync_at DESC;

-- Pending documents
SELECT user_id, COUNT(*) as count
FROM documents
WHERE status = 'pending'
GROUP BY user_id;

-- Dedup check
SELECT user_id, gmail_message_id, COUNT(*)
FROM gmail_messages
GROUP BY user_id, gmail_message_id
HAVING COUNT(*) > 1;

-- Recent syncs
SELECT user_id, synced_at, COUNT(*) as count
FROM gmail_messages
WHERE synced_at > NOW() - INTERVAL '1 hour'
GROUP BY user_id, synced_at;
```

### 8.3 Logging

Enable detailed logging:
```python
# In config
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In services
logger.info(f"User {user.id}: Fetched {len(emails)} emails")
logger.error(f"User {user.id}: Token refresh failed - {error}")
```

---

## 9. Performance Considerations

### 9.1 Scalability

| Metric | Value | Rationale |
|--------|-------|-----------|
| Scheduler interval | 5 minutes | 12 executions/hour; low overhead |
| Worker batch size | 1 user/task | Isolated failures; easy retry |
| Gmail API quota | ~100K msgs/user/day | Incremental sync minimizes usage |
| Email body limit | 5000 chars | Practical for LLM processing |
| Task retry limit | 3 times | Balances resilience vs. resource use |
| Token buffer | 5 minutes | Prevents expiry race conditions |

### 9.2 Database Optimization

```sql
-- Indexes created by migration
CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_gmail_messages_user_id ON gmail_messages(user_id);
CREATE UNIQUE INDEX uq_user_gmail_message ON gmail_messages(user_id, gmail_message_id);
CREATE INDEX idx_user_synced ON gmail_messages(user_id, synced_at);
```

### 9.3 Redis Configuration

```
maxmemory: 256MB (adjust per deployment)
maxmemory-policy: allkeys-lru (evict least recently used)
appendonly: yes (persistence)
```

---

## 10. Production Deployment

### 10.1 High Availability Setup

```
┌──────────────────┐
│ Nginx / LB       │
└────────┬─────────┘
         │
    ┌────┴────┐
    ↓         ↓
┌────────┐ ┌────────┐
│FastAPI │ │FastAPI │  (Multiple instances, stateless)
│(8000)  │ │(8000)  │
└────────┘ └────────┘

┌──────────────┐
│PostgreSQL    │  (With replication)
│(Primary)     │
└──────────────┘

┌──────────────┐
│Redis Cluster │  (With persistence)
└──────────────┘

┌──────────────┐  ┌──────────────┐
│Beat          │  │Workers (x3)  │  (Multiple workers, autoscaled)
│Scheduler     │  │              │
└──────────────┘  └──────────────┘
```

### 10.2 Configuration Management

```python
# Use environment-specific configs
import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production":
    WORKER_PREFETCH = 1
    TASK_SOFT_LIMIT = 300
    TASK_TIME_LIMIT = 600
    CELERY_ACKS_LATE = True
    # Production overrides...
```

### 10.3 Monitoring Stack

- **Application Monitoring**: Sentry, New Relic, DataDog
- **Task Monitoring**: Flower (Celery task UI)
- **Database**: CloudWatch, Datadog RDS monitoring
- **Logs**: CloudWatch Logs, ELK Stack, Splunk

---

## 11. Troubleshooting

### 11.1 No emails synced

```
Checklist:
□ Redis running? (redis-cli ping)
□ Beat scheduler running? (celery inspect active_queues)
□ Worker running? (celery inspect active)
□ User has Gmail tokens? (SELECT gmail_access_token FROM users;)
□ Timezone valid? (SELECT timezone FROM users;)
□ Local time in working hours? (9-18 in user's timezone)
□ Gmail API quota available? (Check Google Cloud Console)
```

### 11.2 Token refresh failing

```
Solution:
1. Manually re-authenticate: DELETE tokens, re-run OAuth
2. Check credentials: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET valid?
3. Verify OAuth redirect URI matches config
4. Check token expiry: SELECT * FROM users WHERE gmail_token_expiry < NOW();
```

### 11.3 Duplicate emails

```
Recovery:
-- Dedup gmail_messages
DELETE FROM gmail_messages g1
WHERE g1.id NOT IN (
    SELECT MAX(id) FROM gmail_messages g2
    WHERE g2.user_id = g1.user_id
    AND g2.gmail_message_id = g1.gmail_message_id
    GROUP BY user_id, gmail_message_id
);

-- Dedup documents (if documents created before dedup)
-- Manual case-by-case review recommended
```

---

## 12. Future Enhancements

### 12.1 Phase 2: User Preferences

```python
class UserPreferences:
    working_hours_start = 9  # Configurable
    working_hours_end = 18
    sync_frequency = 5  # minutes
    email_filters = ["label:important", ...]
    auto_archive = False
    auto_summarize = True
```

### 12.2 Phase 3: Advanced Scheduling

- Per-user cron expressions
- Pause/resume sync per user
- Bulk import historical emails
- Multi-account support

### 12.3 Phase 4: Analytics & Insights

- Email volume trends
- Sync performance metrics
- Cost analysis (Gmail API usage)
- Document processing statistics

---

## 13. Appendix: Code Snippets

### 13.1 Testing the Scheduler

```python
# Manual test
from app.tasks.gmail_scheduler_task import schedule_gmail_sync

# Trigger immediately (outside scheduler window)
result = schedule_gmail_sync()
print(result)  # {total_users: 5, processed: 2, skipped: 3}
```

### 13.2 Database Setup Script

```sql
-- Verify migration applied
\d users
-- Should see: timezone, last_email_sync_at

\d documents
-- Should show: all columns

\d gmail_messages
-- Should show: unique constraint on (user_id, gmail_message_id)
```

### 13.3 Celery CLI Commands

```bash
# Monitor tasks in real-time
celery -A app.core.celery_app events

# Purge queue
celery -A app.core.celery_app purge

# Get task result
celery -A app.core.celery_app result <task_id>

# Revoke running task
celery -A app.core.celery_app revoke <task_id>
```

---

**End of Document**
