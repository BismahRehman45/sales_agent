"""
Celery configuration with Redis broker and Beat scheduler.
"""

from datetime import timedelta

from celery import Celery

from app.core.config import settings

# Create Celery app
app = Celery(
    "sales_agent",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.gmail_scheduler_task",
        "app.tasks.document_processing_task",
        "app.tasks.project_matching_task",
        "app.tasks.project_classification_task",
        "app.tasks.bant_analysis_task",
    ],
)

# Configure Celery
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,
    task_time_limit=600,
    broker_connection_retry_on_startup=True,
)

# Configure Beat schedule (every 30 seconds)
app.conf.beat_schedule = {
    "gmail-sync-every-30-seconds": {
        "task": "app.tasks.gmail_scheduler_task.schedule_gmail_sync",
        "schedule": timedelta(seconds=30),
    },
}


