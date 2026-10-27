from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]  # backend/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    llm_provider: Literal["groq", "ollama"] = "groq"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3:4b"

    calendar_backend: Literal["fake", "graph"] = "fake"
    rep_name: str = "Vaishnavi Soni"
    rep_email: str = "vaishnavi@contoso.example"

    entra_client_id: str = ""
    entra_tenant_id: str = ""

    data_dir: Path = Path("data")

    @field_validator("data_dir")
    @classmethod
    def _relative_to_backend(cls, value: Path) -> Path:
        return value if value.is_absolute() else BACKEND_DIR / value


@lru_cache
def get_settings() -> Settings:
    return Settings()
