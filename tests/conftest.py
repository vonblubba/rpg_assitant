import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/rpg_assistant_test")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
