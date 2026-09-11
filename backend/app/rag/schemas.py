from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


@dataclass
class RetrievedChunk:
    id: str
    bot_id: str
    content: str
    source_url: str
    page_title: str
    section: str
    chunk_index: int
    similarity_score: float
    page_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SourceCitation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str = Field(..., description="Target webpage URL for citation")
    title: str = Field(..., description="Title of the webpage")
    section: str = Field("General", description="Section heading within the webpage")
    chunk_index: int = Field(0, description="Index of the chunk in the document")

