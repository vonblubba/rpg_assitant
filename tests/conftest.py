import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/rpg_assistant_test")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")

import pytest

from app.db import Base, engine


@pytest.fixture
def db_session():
    from app.db import SessionLocal
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
