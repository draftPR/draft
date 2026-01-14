"""Celery application configuration for Smart Kanban."""

import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

# Redis connection settings
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "smart_kanban",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.worker"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Celery Beat schedule for periodic tasks
    beat_schedule={
        "job-watchdog": {
            "task": "job_watchdog",
            "schedule": 15.0,  # Run every 15 seconds for fast recovery
        },
        "planner-tick": {
            "task": "planner_tick",
            "schedule": 2.0,  # Run every 2 seconds for instant developer feedback
        },
        "poll-pr-statuses": {
            "task": "poll_pr_statuses",
            "schedule": 300.0,  # Run every 5 minutes
        },
    },
)
