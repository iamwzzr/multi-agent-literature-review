from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_env: str = "development"
    papers_dir: Path = PROJECT_ROOT / "data" / "papers"
    runtime_dir: Path = PROJECT_ROOT / "data" / "runtime"
    model_api_key: str = ""
    model_name: str = ""
    frontend_origin: str = "http://localhost:5173"


settings = Settings()
