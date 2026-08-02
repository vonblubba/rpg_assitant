from app.config import Settings


def test_ollama_base_url_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/rpg_assistant",
    )
    assert settings.ollama_base_url == "http://host.docker.internal:11434"
