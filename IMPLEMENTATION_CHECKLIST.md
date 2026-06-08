# Implementation Checklist & File Summary

## Complete Implementation List

### ✅ Phase 1: Database Models & Migration

| File | Status | Changes |
|------|--------|---------|
| `app/models/user.py` | ✅ DONE | Added: `timezone`, `last_email_sync_at`, Gmail fields |
| `app/models/document.py` | ✅ DONE | **NEW** - Email/document storage model |
| `app/models/gmail_message.py` | ✅ DONE | **NEW** - Deduplication table with unique constraint |
| `alembic/versions/add_gmail_scheduler_fields.py` | ✅ DONE | **NEW** - Migration for all schema changes |

### ✅ Phase 2: Service Layer

| File | Status | Changes |
|------|--------|---------|
| `app/services/gmail_sync_service.py` | ✅ DONE | **NEW** - Incremental sync, dedup, body extraction |
| `app/services/gmail_token_service.py` | ✅ DONE | **NEW** - Token refresh, expiry checking |
| `app/services/user_service.py` | ✅ EXISTING | No changes needed (uses repositories) |

### ✅ Phase 3: Repositories

| File | Status | Changes |
|------|--------|---------|
| `app/repositories/user_repository.py` | ✅ UPDATED | Added: `get_users_with_gmail_connected()` |
| `app/repositories/document_repository.py` | ✅ DONE | **NEW** - Document CRUD operations |
| `app/repositories/gmail_message_repository.py` | ✅ DONE | **NEW** - Gmail message dedup queries |
| `app/repositories/token_repository.py` | ✅ EXISTING | No changes needed |

### ✅ Phase 4: Celery & Scheduler

| File | Status | Changes |
|------|--------|---------|
| `app/core/celery_app.py` | ✅ DONE | **NEW** - Celery config + Beat schedule (every 5 min) |
| `app/tasks/gmail_scheduler_task.py` | ✅ DONE | **NEW** - `schedule_gmail_sync()` + `sync_user_emails()` |
| `app/tasks/document_tasks.py` | ✅ EXISTING | No changes (future enhancement) |

### ✅ Phase 5: API & Configuration

| File | Status | Changes |
|------|--------|---------|
| `app/core/config.py` | ✅ UPDATED | Added: `REDIS_URL` |
| `app/schemas/user_schema.py` | ✅ UPDATED | Added: `timezone` field + validation |
| `app/main.py` | ✅ EXISTING | No changes needed (startup already in place) |
| `app/routers/auth.py` | ✅ EXISTING | No changes (existing OAuth flow works) |
| `app/routers/user_router.py` | ✅ EXISTING | No changes (PATCH /me auto-supports timezone) |

### ✅ Phase 6: Dependencies & Documentation

| File | Status | Changes |
|------|--------|---------|
| `pyproject.toml` | ✅ UPDATED | Added: `celery[redis]`, `redis`, `pytz`, `alembic` |
| `README.md` | ✅ BACKUP AS | → Backed up as `README_NEW.md` (comprehensive update) |
| `ARCHITECTURE.md` | ✅ DONE | **NEW** - 13-section implementation guide |

---

## Pre-Deployment Checklist

### Database Setup
- [ ] PostgreSQL running and accessible
- [ ] Database created: `sales_agent`
- [ ] Migration applied: `alembic upgrade head`
- [ ] Verify tables: `users`, `documents`, `gmail_messages` exist
- [ ] Verify columns: `users.timezone`, `users.last_email_sync_at` present

### Redis Setup
- [ ] Redis running on `localhost:6379` (or configured `REDIS_URL`)
- [ ] Test connection: `redis-cli ping` → `PONG`

### Environment Variables
- [ ] `.env` file created with all required vars
- [ ] `DATABASE_URI` valid PostgreSQL connection
- [ ] `REDIS_URL` valid Redis connection
- [ ] `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` from Google Cloud Console
- [ ] `GOOGLE_REDIRECT_URI` matches OAuth config
- [ ] `SECRET_KEY` set to random string

### Dependencies
- [ ] Python 3.13+ installed
- [ ] Virtual environment created and activated
- [ ] `pip install -e .` executed successfully
- [ ] Verify: `python -c "import celery; import pytz; print('OK')"`

### Service Startup
- [ ] FastAPI server starts: `uvicorn app.main:app --reload` (no errors)
- [ ] Celery worker starts: `celery -A app.core.celery_app worker --loglevel=info`
- [ ] Celery Beat starts: `celery -A app.core.celery_app beat --loglevel=info`
- [ ] All services running in separate terminals

### Integration Tests
- [ ] User registration works: `POST /auth/register`
- [ ] Google OAuth flow completes: `GET /auth/google/callback?code=...`
- [ ] User can update timezone: `PATCH /users/me {"timezone": "Asia/Karachi"}`
- [ ] User profile shows timezone: `GET /users/me`
- [ ] Scheduler task created: `celery -A app.core.celery_app inspect active`
- [ ] At least 1 scheduler task queued

### Monitoring
- [ ] Beat scheduler runs every 5 minutes (check logs)
- [ ] Workers process tasks (check active tasks)
- [ ] No errors in Celery logs
- [ ] Database records update: `SELECT last_email_sync_at FROM users WHERE gmail_access_token IS NOT NULL;`

---

## File Modification Summary

### Created (12 new files)

1. **app/models/document.py** (42 lines)
   - `Document` ORM model for email/file storage

2. **app/models/gmail_message.py** (35 lines)
   - `GmailMessage` ORM model for deduplication

3. **app/services/gmail_sync_service.py** (280 lines)
   - `GmailSyncService` class with sync logic
   - Incremental fetch via `history.list()`
   - MIME body extraction

4. **app/services/gmail_token_service.py** (50 lines)
   - `ensure_token_fresh()` function
   - Token refresh + expiry checking

5. **app/repositories/document_repository.py** (45 lines)
   - Document CRUD operations

6. **app/repositories/gmail_message_repository.py** (45 lines)
   - Gmail message dedup queries

7. **app/core/celery_app.py** (35 lines)
   - Celery app configuration
   - Beat scheduler setup (every 5 min)

8. **app/tasks/gmail_scheduler_task.py** (150 lines)
   - `schedule_gmail_sync` scheduled task
   - `sync_user_emails` worker task

9. **alembic/versions/add_gmail_scheduler_fields.py** (70 lines)
   - Migration for schema changes

10. **README_NEW.md** (400 lines)
    - Comprehensive updated README

11. **ARCHITECTURE.md** (750 lines)
    - Detailed implementation guide

12. **IMPLEMENTATION_CHECKLIST.md** (this file)

### Modified (5 existing files)

1. **app/models/user.py** (+10 lines)
   - Added: `timezone`, `last_email_sync_at`, Gmail fields

2. **app/core/config.py** (+1 line)
   - Added: `REDIS_URL` setting

3. **app/repositories/user_repository.py** (+12 lines)
   - Added: `get_users_with_gmail_connected()` method

4. **app/schemas/user_schema.py** (+15 lines)
   - Added: `timezone` field to `UserUpdate` and `UserResponse`
   - Added: Timezone validation using `pytz`

5. **pyproject.toml** (+8 lines)
   - Added: `celery[redis]`, `redis`, `pytz`, `alembic` + other packages

---

## Execution Steps

### Step 1: Apply Database Migration (5 min)

```bash
# From project root
alembic upgrade head

# Verify
psql -c "\d users" | grep timezone
psql -c "\d documents"
psql -c "\d gmail_messages"
```

### Step 2: Start Services (2 min)

```bash
# Terminal 1: FastAPI
uvicorn app.main:app --reload

# Terminal 2: Celery worker
celery -A app.core.celery_app worker --loglevel=info

# Terminal 3: Celery Beat
celery -A app.core.celery_app beat --loglevel=info
```

### Step 3: Verify Integration (5 min)

```bash
# Test OAuth
curl "http://localhost:8000/auth/google/login"

# Trigger scheduler manually (optional)
python -c "
from app.tasks.gmail_scheduler_task import schedule_gmail_sync
result = schedule_gmail_sync()
print(f'Scheduler result: {result}')
"

# Check active tasks
celery -A app.core.celery_app inspect active
```

### Step 4: Monitor (Ongoing)

```bash
# Watch Celery tasks
celery -A app.core.celery_app events

# Check database
SELECT email, timezone, last_email_sync_at, gmail_history_id
FROM users
WHERE gmail_access_token IS NOT NULL;

# Check documents
SELECT COUNT(*) FROM documents WHERE status = 'pending';

# Check dedup
SELECT COUNT(*) FROM gmail_messages;
```

---

## Key Files for Reference

### Core Scheduler Logic
- `app/tasks/gmail_scheduler_task.py` - Entry point for all scheduling
- `app/services/gmail_sync_service.py` - Gmail API integration

### Database Schema
- `alembic/versions/add_gmail_scheduler_fields.py` - Migration
- `app/models/user.py` - User with timezone
- `app/models/document.py` - Email storage
- `app/models/gmail_message.py` - Deduplication

### Configuration
- `app/core/celery_app.py` - Beat schedule (every 5 min)
- `app/core/config.py` - Redis URL setting

### API Contracts
- `app/schemas/user_schema.py` - Timezone in user responses
- `app/routers/user_router.py` - PATCH /users/me endpoint

---

## Performance Tuning

### Worker Concurrency

```bash
# Default (1 worker process)
celery -A app.core.celery_app worker --loglevel=info

# Multiple processes (faster)
celery -A app.core.celery_app worker --concurrency=4 --loglevel=info

# Gevent pool (lightweight)
celery -A app.core.celery_app worker --pool=gevent --concurrency=100
```

### Monitoring Tools

```bash
# Flower (web UI)
pip install flower
celery -A app.core.celery_app flower  # http://localhost:5555

# Redis monitoring
redis-cli monitor

# Database monitoring
psql -c "SELECT * FROM pg_stat_activity;"
```

---

## Common Issues & Fixes

| Issue | Solution |
|-------|----------|
| "No module named 'pytz'" | `pip install pytz` |
| "Redis connection refused" | Start Redis: `redis-server` or `docker run redis:7` |
| "Timezone validation error" | Check IANA format (e.g., "Asia/Karachi" not "PKT") |
| "Beat not running tasks" | Verify `REDIS_URL` is correct; restart Beat daemon |
| "Gmail API quota exceeded" | Reduce sync frequency or add rate limiting |
| "Duplicate emails created" | Check `gmail_messages` unique constraint; verify dedup logic |

---

## Next Steps (Post-Deployment)

1. **Verify Sync**: Create test user, connect Gmail, wait for scheduler run (max 5 min)
2. **Monitor Metrics**: Track email volume, sync success rate, API quota usage
3. **Gradual Rollout**: Start with subset of users; monitor for 24 hours
4. **Optimize**: Adjust worker concurrency, tune database indexes
5. **Scale**: Add more workers as user base grows
6. **Analytics**: Set up dashboards to track sync performance

---

## Documentation References

- **ARCHITECTURE.md** - Complete technical design (13 sections)
- **README_NEW.md** - User-facing documentation and quick start
- **This file** - Implementation checklist and file manifest

---

**Status**: ✅ **READY FOR DEPLOYMENT**

**Last Updated**: June 1, 2026  
**Version**: 1.0
