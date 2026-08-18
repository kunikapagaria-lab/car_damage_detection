"""Celery application factory.

Broker and result backend: Redis (same URL as the main application cache).
Workers handle: PDF generation, webhook delivery, damage-diff computation.
"""

from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "car_damage_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=86_400,  # 24 hours
    worker_max_tasks_per_child=200,
    task_routes={
        "tasks.tasks.generate_pdf_task": {"queue": "pdf"},
        "tasks.tasks.deliver_webhook_task": {"queue": "webhooks"},
        "tasks.tasks.compute_damage_diff_task": {"queue": "default"},
    },
)
