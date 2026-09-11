from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CanonicalMarkdownResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bot_id: str = Field(..., description="ID of the bot owning this knowledge base")
    markdown_content: str = Field(..., description="Full canonical Markdown content of the website")
    content_hash: Optional[str] = Field(None, description="SHA-256 hash of the canonical Markdown content")
    source_url: Optional[str] = Field(None, description="Target website URL")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")


class ChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique ID of the chunk")
    bot_id: str = Field(..., description="ID of the bot owning this chunk")
    page_id: Optional[str] = Field(None, description="ID of the source Page if available")
    chunk_index: int = Field(..., description="Zero-based sequence index")
    content: str = Field(..., description="Text content of the chunk")
    chunk_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata dictionary (source_url, title, section, etc.)")
    created_at: datetime = Field(..., description="Timestamp when chunk was created")


class ChunkListResponse(BaseModel):
    chunks: List[ChunkResponse] = Field(default_factory=list)
    total: int = Field(0, description="Total chunks for this bot")


class IndexingRequest(BaseModel):
    embedding_provider: Optional[str] = Field(
        None,
        description="Optional embedding provider override: 'fastembed', 'mock', 'openai', 'gemini'",
    )


class IndexingResponse(BaseModel):
    status: str = Field(..., description="Status of the indexing operation ('success' or 'failed')")
    bot_id: str = Field(..., description="ID of the bot indexed")
    pages_count: int = Field(..., description="Number of crawled pages processed")
    chunks_count: int = Field(..., description="Number of semantic chunks created and indexed")
    canonical_markdown_length: int = Field(..., description="Character count of generated canonical website.md")
    message: str = Field(..., description="Human-readable result summary")

