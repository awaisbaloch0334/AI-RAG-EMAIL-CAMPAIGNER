from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.rag.schemas import SourceCitation


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User question or input")
    session_id: Optional[str] = Field(None, max_length=128, description="Persistent session identifier for multi-turn chat continuity")
    stream: bool = Field(False, description="Whether to stream the response via Server-Sent Events (SSE)")
    provider: Optional[str] = Field(None, description="Optional LLM provider override ('gemini', 'claude', 'openai', 'mock')")


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    answer: str = Field(..., description="Grounded response from the chatbot")
    sources: List[SourceCitation] = Field(default_factory=list, description="Referenced website source citations")
    conversation_id: str = Field(..., description="Unique database ID of this conversation")
    session_id: str = Field(..., description="Session identifier for multi-turn context")


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique message ID")
    role: str = Field(..., description="Role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text content")
    created_at: datetime = Field(..., description="Message creation timestamp")


class ConversationSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Conversation ID")
    bot_id: str = Field(..., description="Bot ID")
    session_id: str = Field(..., description="Session identifier")
    message_count: int = Field(0, description="Total messages in conversation")
    created_at: datetime = Field(..., description="Conversation creation timestamp")


class ConversationDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Conversation ID")
    bot_id: str = Field(..., description="Bot ID")
    session_id: str = Field(..., description="Session identifier")
    created_at: datetime = Field(..., description="Conversation creation timestamp")
    messages: List[MessageResponse] = Field(default_factory=list, description="Chronological message turns")


class ConversationListResponse(BaseModel):
    conversations: List[ConversationSummaryResponse] = Field(default_factory=list)
    total: int = Field(0, description="Total conversations for this bot")

