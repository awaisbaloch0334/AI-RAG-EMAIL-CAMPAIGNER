from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    postgres_db: str
    postgres_user: str
    postgres_password: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    redis_host: str = "localhost"
    redis_port: int = 6379

    jwt_secret_key: str = "rag-chatbot-dev-secret-key-32-chars-min-change-prod"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24

    # Embeddings Configuration
    embedding_provider: str = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""

    # Generative LLM Configuration (Groq, Gemini, Claude, OpenAI, Mock)
    llm_provider: str = "groq"
    llm_model: str = "openai/gpt-oss-120b"

    # SMTP Email Configuration for Real OTP Delivery
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_use_tls: bool = True

    # Real HubSpot CRM Configuration (Server-side Private App Token & OAuth 2.0)
    hubspot_access_token: str = ""
    hubspot_api_base_url: str = "https://api.hubapi.com"
    hubspot_auth_base_url: str = "https://app-na2.hubspot.com"
    hubspot_client_id: str = ""
    hubspot_client_secret: str = ""
    hubspot_redirect_uri: str = "http://localhost:8000/api/auth/hubspot/callback"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()