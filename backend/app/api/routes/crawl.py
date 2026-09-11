import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_bot
from app.crawler.schemas import CrawlJobResponse, CrawlTriggerRequest, PageListResponse, PageResponse
from app.db.database import get_db
from app.db.models.bot import Bot
from app.db.models.crawl import CrawlJob, Page
from app.tasks.celery_app import celery_app
from app.tasks.crawl_tasks import run_crawl_pipeline, start_crawl_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bots/{bot_id}", tags=["crawl"])


@router.post(
    "/crawl",
    response_model=CrawlJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger asynchronous website crawl for this bot",
)
def trigger_crawl(
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
    background_tasks: BackgroundTasks,
    req: Optional[CrawlTriggerRequest] = None,
):
    """
    Queue an asynchronous crawl job for the target website.
    Enforces user ownership on bot_id and preserves bot_id throughout the pipeline.
    Dispatches to Celery worker if online, or immediately falls back to FastAPI BackgroundTasks.
    """
    max_pages = req.max_pages if req else 60

    job = CrawlJob(
        bot_id=bot.id,
        status="PENDING",
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    bot.status = "CRAWLING"
    db.commit()
    db.refresh(job)

    dispatched_to_celery = False
    try:
        insp = celery_app.control.inspect(timeout=0.3)
        workers = insp.ping() if insp else None
        if workers:
            start_crawl_task.delay(bot_id=bot.id, job_id=job.id, max_pages=max_pages)
            dispatched_to_celery = True
            logger.info(f"Dispatched crawl job '{job.id}' to Celery worker: {list(workers.keys())}")
    except Exception as e:
        logger.warning(f"Celery inspection error: {e}")

    if not dispatched_to_celery:
        logger.info(f"No active Celery workers found. Running crawl job '{job.id}' in FastAPI BackgroundTasks.")
        background_tasks.add_task(run_crawl_pipeline, bot_id=bot.id, job_id=job.id, max_pages=max_pages)

    return job


@router.get(
    "/crawl/status",
    response_model=Optional[CrawlJobResponse],
    summary="Get status of latest crawl job for this bot",
)
def get_crawl_status(
    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Returns progress and status of the latest crawl job for this bot.
    """
    stmt = (
        select(CrawlJob)
        .where(CrawlJob.bot_id == bot.id)
        .order_by(CrawlJob.started_at.desc())
    )
    job = db.scalar(stmt)
    return job


@router.get(
    "/pages",
    response_model=PageListResponse,
    summary="List all crawled pages for this bot",
)
@router.get(
    "/knowledge/pages",
    response_model=PageListResponse,
    include_in_schema=False,
)
def list_pages(

    bot: Annotated[Bot, Depends(get_current_bot)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Returns list of extracted pages belonging strictly to this bot.
    """
    stmt = select(Page).where(Page.bot_id == bot.id).order_by(Page.created_at.desc())
    pages = db.scalars(stmt).all()

    response_items = []
    for p in pages:
        preview = p.content[:200] + "..." if p.content and len(p.content) > 200 else p.content
        response_items.append(
            PageResponse(
                id=p.id,
                bot_id=p.bot_id,
                url=p.url,
                title=p.title,
                content_preview=preview,
                content_hash=p.content_hash,
                crawl_status=p.crawl_status,
                created_at=p.created_at,
            )
        )

    return PageListResponse(pages=response_items, total=len(response_items))

