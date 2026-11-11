from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )
    app_env: str = "development"
    workspace_root: Path = PROJECT_ROOT
    allowed_roots: list[Path] = Field(default_factory=lambda: [PROJECT_ROOT])
    papers_dir: Path = PROJECT_ROOT / "data" / "papers"
    runtime_dir: Path = PROJECT_ROOT / "data" / "runtime"
    model_api_key: SecretStr = SecretStr("")
    model_name: str = ""
    model_base_url: str = "https://api.openai.com/v1"
    model_json_mode: bool = True
    model_reasoning_effort: str = ""
    model_token_parameter: Literal['max_completion_tokens', 'max_tokens'] = 'max_completion_tokens'
    model_timeout_seconds: float = Field(default=90, ge=1, le=300)
    model_max_tokens: int = Field(default=4000, ge=256, le=16000)
    max_model_calls: int = Field(default=24, ge=4, le=80)
    max_revision_rounds: int = Field(default=2, ge=0, le=3)
    max_concurrent_reviews: int = Field(default=2, ge=1, le=8)
    max_request_bytes: int = Field(default=2_000_000, ge=1024)
    max_pdf_bytes: int = Field(default=30_000_000, ge=1024)
    max_papers: int = Field(default=40, ge=1, le=200)
    max_pages_per_pdf: int = Field(default=300, ge=1, le=2000)
    max_total_pages: int = Field(default=1500, ge=1, le=10000)
    pdf_timeout_seconds: float = Field(default=45, ge=1, le=180)
    max_prompt_chars: int = Field(default=65000, ge=8000, le=200000)
    frontend_origin: str = "http://localhost:5173"
    cors_origins: list[str] = Field(default_factory=lambda: [
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ])


settings = Settings()
