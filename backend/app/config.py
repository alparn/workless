from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/buchhaltung"
    database_url_sync: str = "postgresql://postgres:postgres@postgres:5432/buchhaltung"

    anthropic_api_key: str = ""
    mistral_api_key: str = ""
    tavily_api_key: str = ""

    langsmith_api_key: str = ""
    langsmith_project: str = "ai-buchhaltung"
    langchain_tracing_v2: bool = False

    upload_dir: Path = Path("/app/uploads")
    export_dir: Path = Path("/app/exports")

    openai_api_key: str = ""
    llm_key_encryption_secret: str = ""

    thinking_budget_tokens: int = 8000
    thinking_confidence_threshold: float = 0.7

    supervisor_enabled: bool = True
    supervisor_interval_seconds: int = 120
    supervisor_max_ocr_retries: int = 3


settings = Settings()
