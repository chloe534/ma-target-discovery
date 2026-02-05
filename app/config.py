"""Configuration settings for M&A Target Discovery Platform."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Paths
    base_dir: Path = Path(__file__).parent.parent
    data_dir: Path = base_dir / "data"
    db_path: Path = data_dir / "ma_discovery.db"

    # API Keys
    anthropic_api_key: str = ""
    opencorporates_api_key: str = ""

    # HTTP Client Settings
    user_agent: str = "MATargetBot/1.0 (+contact@example.com)"
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    rate_limit_delay: float = 1.0  # seconds between requests per domain

    # Cache Settings
    cache_duration_days: int = 30
    robots_cache_duration_hours: int = 24

    # LLM Settings
    llm_model: str = "claude-sonnet-4-20250514"
    llm_confidence_threshold: float = 0.6

    # Search Settings
    default_search_limit: int = 50
    max_pages_per_company: int = 5

    # Database URL
    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def async_database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure data directory exists
settings.data_dir.mkdir(parents=True, exist_ok=True)
