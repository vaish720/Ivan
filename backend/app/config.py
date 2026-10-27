from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
