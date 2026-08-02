from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    ollama_base_url: str = "http://host.docker.internal:11434"
    chat_model: str = "llama3.1:8b"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768


@lru_cache
def get_settings() -> Settings:
    return Settings()
