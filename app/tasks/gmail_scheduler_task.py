"""
Celery tasks for Gmail synchronization scheduler.

Implements:
- schedule_gmail_sync: Runs every 5 minutes, filters users by timezone/working hours
- sync_user_emails: Worker task that syncs emails for a single user
"""

import logging
from datetime import datetime, timezone as dt_timezone

import pytz
from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session as AsyncSessionLocal
from app.repositories import user_repository
from app.services.gmail_sync_service import GmailSyncService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def schedule_gmail_sync(self):
    """
    Scheduled task that runs every 5 minutes.
    Fetches active users and dispatches sync_user_emails tasks for those in working hours.
    """
    import asyncio

    try:
        result = asyncio.run(_schedule_gmail_sync_impl())
        logger.info(f"Gmail scheduler completed: {result}")
        return result
    except Exception as exc:
        logger.error(f"Error in schedule_gmail_sync: {str(exc)}")
        raise self.retry(exc=exc, countdown=60)


async def _schedule_gmail_sync_impl() -> dict:
    """Implementation of schedule_gmail_sync."""
    async with AsyncSessionLocal() as db:
        try:
            # Fetch all users with Gmail connected
            users = await user_repository.get_users_with_gmail_connected(db)
            logger.info(f"Found {len(users)} users with Gmail connected")

            current_utc = datetime.now(dt_timezone.utc)
            total_users = len(users)
            processed = 0
            skipped = 0

            for user in users:
                # Convert UTC to user's timezone
                user_tz = pytz.timezone(user.timezone)
                user_local_time = current_utc.astimezone(user_tz)

                # Check if user is in working hours (9 AM - 6 PM)
                if 9 <= user_local_time.hour < 18:
                    logger.info(
                        f"User {user.id} in working hours ({user_local_time.strftime('%H:%M')} "
                        f"{user.timezone}). Dispatching sync task."
                    )
                    # Enqueue worker task
                    sync_user_emails.delay(str(user.id))
                    processed += 1
                else:
                    skipped += 1
                    logger.debug(
                        f"User {user.id} outside working hours ({user_local_time.strftime('%H:%M')} "
                        f"{user.timezone}). Skipped."
                    )

            return {
                "total_users": total_users,
                "processed": processed,
                "skipped": skipped,
                "timestamp": current_utc.isoformat(),
            }

        except Exception as e:
            logger.error(f"Error in _schedule_gmail_sync_impl: {str(e)}")
            raise


@shared_task(bind=True, max_retries=3)
def sync_user_emails(self, user_id: str):
    """
    Worker task that syncs emails for a single user.
    Runs asynchronously and can be retried on failure.
    """
    import asyncio

    try:
        result = asyncio.run(_sync_user_emails_impl(user_id))
        logger.info(f"Sync completed for user {user_id}: {result}")
        return result
    except Exception as exc:
        logger.error(f"Error syncing emails for user {user_id}: {str(exc)}")
        # Retry after 60 seconds
        raise self.retry(exc=exc, countdown=60)


async def _sync_user_emails_impl(user_id: str) -> dict:
    """Implementation of sync_user_emails."""
    async with AsyncSessionLocal() as db:
        try:
            # Fetch user
            user = await user_repository.get_user_by_id(db, user_id)
            if not user:
                logger.error(f"User {user_id} not found")
                return {"error": "User not found", "user_id": user_id}

            logger.info(f"Starting email sync for user {user.id} ({user.email})")

            # Sync emails
            result = await GmailSyncService.sync_user_emails(db, user)

            logger.info(
                f"Email sync completed for user {user.id}: "
                f"fetched={result['fetched_count']}, processed={result['processed_count']}, "
                f"errors={len(result['errors'])}"
            )

            return {
                "user_id": user_id,
                "email": user.email,
                "fetched_count": result["fetched_count"],
                "processed_count": result["processed_count"],
                "errors": result["errors"],
                "timestamp": datetime.now(dt_timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error in _sync_user_emails_impl for user {user_id}: {str(e)}")
            raise
