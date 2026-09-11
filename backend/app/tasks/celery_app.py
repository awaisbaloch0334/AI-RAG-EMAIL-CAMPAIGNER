from celery import Celery

from app.config import settings

redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/0"

celery_app = Celery(
    "rag_chatbot",
    broker=redis_url,
    backend=redis_url,
    include=["app.tasks.crawl_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)

