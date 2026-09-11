from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class BotCreateRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Friendly display name of the bot",
        examples=["My Support Bot"],
    )
    website_url: HttpUrl = Field(
        ...,
        description="Target website URL to crawl and index",
        examples=["https://example.com"],
    )


class BotUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255, examples=["Updated Bot Name"])
    website_url: Optional[HttpUrl] = Field(None, examples=["https://example.com/updated"])


class BotResponse(BaseModel):
    id: str
    user_id: str
    name: str
    website_url: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BotListResponse(BaseModel):
    bots: List[BotResponse]
    total: int


class BrandingUpdateRequest(BaseModel):
    company_name: Optional[str] = Field(None, max_length=255)
    logo_url: Optional[str] = Field(None, max_length=2048)
    favicon_url: Optional[str] = Field(None, max_length=2048)
    primary_color: Optional[str] = Field(None, max_length=32, description="Primary theme/accent color, e.g. #D6A84F or #10B981")
    secondary_color: Optional[str] = Field(None, max_length=32)
    background_color: Optional[str] = Field(None, max_length=32, description="Chat surface background color, e.g. #FFFFFF or #080A0D")
    text_color: Optional[str] = Field(None, max_length=32, description="Chat body text color, e.g. #111827 or #F5F5F3")
    font_family: Optional[str] = Field(None, max_length=64)
    position: Optional[str] = Field(None, max_length=32, description="'bottom-right' or 'bottom-left'")


class BrandingResponse(BaseModel):
    bot_id: str
    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: str = "#D6A84F"
    secondary_color: Optional[str] = "#F0C76A"
    background_color: str = "#FFFFFF"
    text_color: str = "#111827"
    font_family: str = "Inter, system-ui, sans-serif"
    position: str = "bottom-right"

    model_config = ConfigDict(from_attributes=True)
