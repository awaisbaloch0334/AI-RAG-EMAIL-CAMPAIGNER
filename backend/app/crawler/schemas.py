from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CrawlTriggerRequest(BaseModel):
    max_pages: int = Field(60, ge=1, le=100, description="Maximum number of same-domain pages to crawl", examples=[60])


class CrawlJobResponse(BaseModel):
    id: str
    bot_id: str
    status: str
    total_pages: int
    processed_pages: int
    failed_pages: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PageResponse(BaseModel):
    id: str
    bot_id: str
    url: str
    title: Optional[str] = None
    content_preview: Optional[str] = None
    content_hash: Optional[str] = None
    crawl_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PageListResponse(BaseModel):
    pages: List[PageResponse]
    total: int

