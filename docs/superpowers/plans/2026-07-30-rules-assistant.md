# TTRPG Rules Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dockerized, local RAG chat app that lets a GM upload TTRPG rulebook PDFs grouped by game system, and ask rules questions answered from the ingested text.

**Architecture:** FastAPI backend (server-rendered Jinja2 + vanilla JS frontend) backed by Postgres+pgvector for storage/retrieval and a local Ollama container for embeddings and chat. PDF ingestion runs as a background task using `unstructured` (hi-res, local models) for layout-aware parsing, keeping tables intact as single chunks.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, psycopg3, pgvector, unstructured[pdf], httpx, Jinja2, pytest, respx (HTTP mocking), reportlab (test fixture PDFs), Docker Compose.

## Global Constraints

- Entire stack runs via `docker compose up` — app, Postgres, and Ollama are all containerized. (spec: Scope)
- No external/cloud API calls at runtime — all LLM/embedding inference goes through the local `ollama` service. (spec: Scope)
- Single user, no auth. (spec: Scope, Non-goals)
- Default models: `llama3.1:8b` (chat), `nomic-embed-text` (embeddings), both configurable via env vars. (spec: Architecture)
- Embedding vector dimension: 768 (matches `nomic-embed-text`). (spec: Data model)
- Chat questions are scoped to one active game system at a time; retrieval always filters by `game_system_id`. (spec: Scope, Chat/retrieval flow)
- Tables must never be split across chunks. (spec: PDF parsing / ingestion pipeline)
- No multi-turn conversational memory fed into retrieval in v1. (spec: Chat/retrieval flow)
- Deleting a `game_systems` row cascades to `documents` and `chunks`; deleting a `documents` row cascades to its `chunks`. (spec: Data model)

---

### Task 1: Project scaffolding, config, and health check

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/main.py`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Produces: `app.config.Settings` (pydantic-settings `BaseSettings`) with fields `database_url: str`, `ollama_base_url: str`, `chat_model: str = "llama3.1:8b"`, `embedding_model: str = "nomic-embed-text"`, `embedding_dim: int = 768`, read from env vars `DATABASE_URL`, `OLLAMA_BASE_URL`, `CHAT_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`.
- Produces: `app.config.get_settings() -> Settings` (cached via `functools.lru_cache`).
- Produces: `app.main.app` — the FastAPI instance, with `GET /health` returning `{"status": "ok"}`.

- [ ] **Step 1: Write `pyproject.toml` with dependencies**

```toml
[project]
name = "rpg-assistant"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0",
    "psycopg[binary]>=3.2",
    "pgvector>=0.3.6",
    "pydantic-settings>=2.6",
    "jinja2>=3.1",
    "python-multipart>=0.0.12",
    "httpx>=0.27",
    "unstructured[pdf]>=0.16",
    "markdownify>=0.13",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
    "reportlab>=4.2",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write `app/config.py`**

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    ollama_base_url: str = "http://ollama:11434"
    chat_model: str = "llama3.1:8b"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 3: Write `app/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="TTRPG Rules Assistant")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Write `tests/conftest.py` with a `DATABASE_URL` env default for tests**

```python
import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5433/rpg_assistant_test")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
```

- [ ] **Step 5: Write the failing test `tests/test_health.py`**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 6: Install dependencies and run the test to verify it fails first, then passes**

Run: `pip install -e ".[dev]"`
Run: `pytest tests/test_health.py -v`
Expected: PASS (the endpoint is trivial, so this mainly confirms the project imports and dependencies are wired correctly)

- [ ] **Step 7: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# Pre-warm the unstructured hi-res layout model at build time so ingestion
# never needs network access at runtime.
RUN python -c "from unstructured_inference.models.base import get_model; get_model('yolox')"

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 8: Write `docker-compose.yml` (app + postgres services; ollama added in Task 12)**

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:postgres@postgres:5432/rpg_assistant
      OLLAMA_BASE_URL: http://ollama:11434
    depends_on:
      - postgres
    volumes:
      - .:/app

  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: rpg_assistant
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

- [ ] **Step 9: Write `.env.example`**

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/rpg_assistant
OLLAMA_BASE_URL=http://localhost:11434
CHAT_MODEL=llama3.1:8b
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml app/__init__.py app/config.py app/main.py Dockerfile docker-compose.yml .env.example tests/__init__.py tests/conftest.py tests/test_health.py
git commit -m "feat: scaffold FastAPI app with config, Docker, and health check"
```

---

### Task 2: Database models and connection

**Files:**
- Create: `app/db.py`
- Create: `app/models.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `app.config.get_settings()` (Task 1).
- Produces: `app.db.Base` (SQLAlchemy `DeclarativeBase`), `app.db.engine`, `app.db.SessionLocal`, `app.db.get_db() -> Generator[Session, None, None]` (FastAPI dependency), `app.db.init_db() -> None` (enables `vector` extension, creates all tables).
- Produces: `app.models.GameSystem(id, name, created_at)`, `app.models.Document(id, game_system_id, filename, status, error_message, uploaded_at)`, `app.models.Chunk(id, document_id, game_system_id, content, page_number, embedding)`.
- Produces: `tests/conftest.py` fixture `db_session` (function-scoped SQLAlchemy `Session` against a real test Postgres, tables created/dropped per test).

A real Postgres+pgvector instance is required for tests from this task onward. Run one throwaway container once before running the test suite locally:

```bash
docker run -d --rm --name rpg-assistant-test-db -p 5433:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=rpg_assistant_test \
  pgvector/pgvector:pg17
```

- [ ] **Step 1: Write `app/db.py`**

```python
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 2: Write `app/models.py`**

```python
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db import Base

settings = get_settings()


class GameSystem(Base):
    __tablename__ = "game_systems"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    documents: Mapped[list["Document"]] = relationship(
        back_populates="game_system", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_system_id: Mapped[int] = mapped_column(ForeignKey("game_systems.id", ondelete="CASCADE"))
    filename: Mapped[str]
    status: Mapped[str] = mapped_column(default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    uploaded_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    game_system: Mapped["GameSystem"] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    game_system_id: Mapped[int] = mapped_column(ForeignKey("game_systems.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(default=None)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))

    document: Mapped["Document"] = relationship(back_populates="chunks")
```

- [ ] **Step 3: Add `db_session` fixture to `tests/conftest.py`**

```python
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
```

- [ ] **Step 4: Write the failing test `tests/test_models.py`**

```python
from app.models import Chunk, Document, GameSystem


def test_create_game_system_document_and_chunk(db_session):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    document = Document(game_system_id=system.id, filename="phb.pdf", status="ready")
    db_session.add(document)
    db_session.commit()

    chunk = Chunk(
        document_id=document.id,
        game_system_id=system.id,
        content="A fighter is a master of martial combat.",
        page_number=12,
        embedding=[0.0] * 768,
    )
    db_session.add(chunk)
    db_session.commit()

    fetched = db_session.get(Chunk, chunk.id)
    assert fetched.content.startswith("A fighter")
    assert fetched.page_number == 12
    assert len(fetched.embedding) == 768


def test_deleting_game_system_cascades_to_documents_and_chunks(db_session):
    system = GameSystem(name="Call of Cthulhu")
    db_session.add(system)
    db_session.commit()

    document = Document(game_system_id=system.id, filename="keeper.pdf", status="ready")
    db_session.add(document)
    db_session.commit()

    chunk = Chunk(
        document_id=document.id,
        game_system_id=system.id,
        content="Sanity loss occurs when...",
        embedding=[0.0] * 768,
    )
    db_session.add(chunk)
    db_session.commit()
    chunk_id = chunk.id

    db_session.delete(system)
    db_session.commit()

    assert db_session.get(Document, document.id) is None
    assert db_session.get(Chunk, chunk_id) is None
```

- [ ] **Step 5: Run test to verify it fails, then implement, then pass**

Run: `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/rpg_assistant_test pytest tests/test_models.py -v`
Expected first run (before Steps 1-2 exist): FAIL with `ModuleNotFoundError`.
After implementing Steps 1-2: PASS.

- [ ] **Step 6: Update `tests/conftest.py`'s default `DATABASE_URL` to point at port 5433 (the test container) as shown in Step 4 above, and commit**

```bash
git add app/db.py app/models.py tests/conftest.py tests/test_models.py
git commit -m "feat: add SQLAlchemy models and Postgres/pgvector connection"
```

---

### Task 3: Game systems CRUD API

**Files:**
- Create: `app/schemas.py`
- Create: `app/routes/__init__.py`
- Create: `app/routes/systems.py`
- Modify: `app/main.py`
- Test: `tests/test_api_systems.py`

**Interfaces:**
- Consumes: `app.db.get_db` (Task 2), `app.models.GameSystem` (Task 2).
- Produces: `app.schemas.GameSystemCreate(name: str)`, `app.schemas.GameSystemOut(id: int, name: str, created_at: datetime)` (Pydantic, `model_config = ConfigDict(from_attributes=True)`).
- Produces: `app.routes.systems.router` (`APIRouter`), mounted in `app.main.app` with prefix `/systems`, exposing `POST /systems`, `GET /systems`, `DELETE /systems/{system_id}`.

- [ ] **Step 1: Write `app/schemas.py`**

```python
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GameSystemCreate(BaseModel):
    name: str


class GameSystemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
```

- [ ] **Step 2: Write the failing test `tests/test_api_systems.py`**

```python
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


def make_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_create_and_list_game_systems(db_session):
    client = make_client(db_session)

    response = client.post("/systems", json={"name": "D&D 5e"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "D&D 5e"
    assert "id" in body

    response = client.get("/systems")
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert names == ["D&D 5e"]


def test_delete_game_system(db_session):
    client = make_client(db_session)
    created = client.post("/systems", json={"name": "Call of Cthulhu"}).json()

    response = client.delete(f"/systems/{created['id']}")
    assert response.status_code == 204

    response = client.get("/systems")
    assert response.json() == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_api_systems.py -v`
Expected: FAIL (no `app/routes/systems.py`, no route mounted).

- [ ] **Step 4: Write `app/routes/__init__.py` (empty) and `app/routes/systems.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import GameSystem
from app.schemas import GameSystemCreate, GameSystemOut

router = APIRouter(prefix="/systems", tags=["systems"])


@router.post("", response_model=GameSystemOut, status_code=201)
def create_system(payload: GameSystemCreate, db: Session = Depends(get_db)) -> GameSystem:
    system = GameSystem(name=payload.name)
    db.add(system)
    db.commit()
    db.refresh(system)
    return system


@router.get("", response_model=list[GameSystemOut])
def list_systems(db: Session = Depends(get_db)) -> list[GameSystem]:
    return db.query(GameSystem).order_by(GameSystem.created_at).all()


@router.delete("/{system_id}", status_code=204)
def delete_system(system_id: int, db: Session = Depends(get_db)) -> None:
    system = db.get(GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")
    db.delete(system)
    db.commit()
```

- [ ] **Step 5: Mount the router in `app/main.py`**

```python
from fastapi import FastAPI

from app.routes.systems import router as systems_router

app = FastAPI(title="TTRPG Rules Assistant")
app.include_router(systems_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_api_systems.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/schemas.py app/routes/__init__.py app/routes/systems.py app/main.py tests/test_api_systems.py
git commit -m "feat: add game systems CRUD API"
```

---

### Task 4: Ollama client wrapper

**Files:**
- Create: `app/ollama_client.py`
- Test: `tests/test_ollama_client.py`

**Interfaces:**
- Consumes: `app.config.get_settings()` (Task 1).
- Produces: `app.ollama_client.embed_text(text: str) -> list[float]` (async), `app.ollama_client.chat_stream(messages: list[dict]) -> AsyncIterator[str]` (async generator yielding response text chunks), `app.ollama_client.OllamaError(Exception)` raised on unreachable/non-2xx responses.

- [ ] **Step 1: Write the failing test `tests/test_ollama_client.py`**

```python
import json

import httpx
import pytest
import respx

from app.config import get_settings
from app.ollama_client import OllamaError, chat_stream, embed_text


@pytest.mark.asyncio
@respx.mock
async def test_embed_text_returns_embedding_vector():
    settings = get_settings()
    respx.post(f"{settings.ollama_base_url}/api/embeddings").mock(
        return_value=httpx.Response(200, json={"embedding": [0.1, 0.2, 0.3]})
    )

    result = await embed_text("a fighter is a master of martial combat")

    assert result == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
@respx.mock
async def test_embed_text_raises_ollama_error_on_failure():
    settings = get_settings()
    respx.post(f"{settings.ollama_base_url}/api/embeddings").mock(return_value=httpx.Response(500))

    with pytest.raises(OllamaError):
        await embed_text("anything")


@pytest.mark.asyncio
@respx.mock
async def test_chat_stream_yields_content_chunks():
    settings = get_settings()
    lines = [
        json.dumps({"message": {"content": "A "}, "done": False}),
        json.dumps({"message": {"content": "fighter."}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]
    body = "\n".join(lines) + "\n"
    respx.post(f"{settings.ollama_base_url}/api/chat").mock(
        return_value=httpx.Response(200, content=body.encode())
    )

    chunks = [chunk async for chunk in chat_stream([{"role": "user", "content": "What is a fighter?"}])]

    assert chunks == ["A ", "fighter."]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ollama_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ollama_client'`

- [ ] **Step 3: Write `app/ollama_client.py`**

```python
import json
from collections.abc import AsyncIterator

import httpx

from app.config import get_settings


class OllamaError(Exception):
    pass


async def embed_text(text: str) -> list[float]:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=60) as client:
        try:
            response = await client.post(
                "/api/embeddings",
                json={"model": settings.embedding_model, "prompt": text},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama embeddings request failed: {exc}") from exc
        return response.json()["embedding"]


async def chat_stream(messages: list[dict]) -> AsyncIterator[str]:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=None) as client:
        try:
            async with client.stream(
                "POST",
                "/api/chat",
                json={"model": settings.chat_model, "messages": messages, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama chat request failed: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ollama_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ollama_client.py tests/test_ollama_client.py
git commit -m "feat: add Ollama HTTP client for embeddings and streaming chat"
```

---

### Task 5: PDF parsing module

**Files:**
- Create: `app/ingestion/__init__.py`
- Create: `app/ingestion/parser.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_parser.py`

**Interfaces:**
- Produces: `app.ingestion.parser.ParsedElement` (dataclass: `text: str`, `category: str`, `page_number: int | None`), `app.ingestion.parser.parse_pdf(path: str) -> list[ParsedElement]`.
- Produces: `tests/conftest.py` fixtures `plain_pdf_path(tmp_path) -> str` and `table_pdf_path(tmp_path) -> str`, building real PDFs on disk with `reportlab` (no binary fixtures committed to the repo).

- [ ] **Step 1: Add PDF-building fixtures to `tests/conftest.py`**

```python
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle


@pytest.fixture
def plain_pdf_path(tmp_path):
    path = tmp_path / "plain.pdf"
    doc = SimpleDocTemplate(str(path))
    styles = getSampleStyleSheet()
    doc.build(
        [
            Paragraph(
                "A fighter is a master of martial combat, skilled with a variety "
                "of weapons and armor. Fighters learn the basics of all combat "
                "styles.",
                styles["Normal"],
            )
        ]
    )
    return str(path)


@pytest.fixture
def table_pdf_path(tmp_path):
    path = tmp_path / "table.pdf"
    doc = SimpleDocTemplate(str(path))
    data = [
        ["Weapon", "Damage", "Weight"],
        ["Longsword", "1d8", "3 lb"],
        ["Dagger", "1d4", "1 lb"],
    ]
    table = Table(data)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 1, colors.black)]))
    doc.build([table])
    return str(path)
```

- [ ] **Step 2: Write the failing test `tests/test_parser.py`**

```python
from app.ingestion.parser import parse_pdf


def test_parse_pdf_extracts_prose_text(plain_pdf_path):
    elements = parse_pdf(plain_pdf_path)

    assert len(elements) > 0
    assert any("master of martial combat" in el.text for el in elements)
    assert all(el.page_number == 1 for el in elements)


def test_parse_pdf_extracts_table_as_table_category(table_pdf_path):
    elements = parse_pdf(table_pdf_path)

    table_elements = [el for el in elements if el.category == "Table"]
    assert len(table_elements) == 1
    assert "Longsword" in table_elements[0].text
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion'`

- [ ] **Step 4: Write `app/ingestion/__init__.py` (empty) and `app/ingestion/parser.py`**

```python
from dataclasses import dataclass

from unstructured.partition.pdf import partition_pdf


@dataclass
class ParsedElement:
    text: str
    category: str
    page_number: int | None


def parse_pdf(path: str) -> list[ParsedElement]:
    elements = partition_pdf(filename=path, strategy="hi_res", infer_table_structure=True)
    parsed: list[ParsedElement] = []
    for element in elements:
        text = str(element).strip()
        if not text:
            continue
        parsed.append(
            ParsedElement(
                text=text,
                category=element.category,
                page_number=element.metadata.page_number,
            )
        )
    return parsed
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_parser.py -v`
Expected: PASS (this test invokes the real hi-res model and will take longer than the other tests — that's expected)

- [ ] **Step 6: Commit**

```bash
git add app/ingestion/__init__.py app/ingestion/parser.py tests/conftest.py tests/test_parser.py
git commit -m "feat: add unstructured-based PDF parsing module"
```

---

### Task 6: Chunker module

**Files:**
- Create: `app/ingestion/chunker.py`
- Test: `tests/test_chunker.py`

**Interfaces:**
- Consumes: `app.ingestion.parser.ParsedElement` (Task 5).
- Produces: `app.ingestion.chunker.Chunk` (dataclass: `content: str`, `page_number: int | None`, `is_table: bool`), `app.ingestion.chunker.chunk_elements(elements: list[ParsedElement], max_chars: int = 1500, overlap_chars: int = 200) -> list[Chunk]`.

This is a pure unit test — no PDF or database needed, only synthetic `ParsedElement` instances.

- [ ] **Step 1: Write the failing test `tests/test_chunker.py`**

```python
from app.ingestion.chunker import chunk_elements
from app.ingestion.parser import ParsedElement


def test_table_element_becomes_single_whole_chunk():
    elements = [
        ParsedElement(text="Intro text.", category="NarrativeText", page_number=1),
        ParsedElement(text="| Weapon | Damage |\n| Longsword | 1d8 |", category="Table", page_number=2),
        ParsedElement(text="More text.", category="NarrativeText", page_number=3),
    ]

    chunks = chunk_elements(elements, max_chars=1000, overlap_chars=50)

    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert table_chunks[0].content == elements[1].text
    assert table_chunks[0].page_number == 2


def test_large_table_is_never_split():
    huge_table_text = "| Col |\n" + "\n".join(f"| row{i} |" for i in range(500))
    elements = [ParsedElement(text=huge_table_text, category="Table", page_number=1)]

    chunks = chunk_elements(elements, max_chars=100, overlap_chars=20)

    assert len(chunks) == 1
    assert chunks[0].content == huge_table_text


def test_prose_splits_when_exceeding_max_chars_with_overlap():
    elements = [
        ParsedElement(text="A" * 60, category="NarrativeText", page_number=1),
        ParsedElement(text="B" * 60, category="NarrativeText", page_number=1),
        ParsedElement(text="C" * 60, category="NarrativeText", page_number=2),
    ]

    chunks = chunk_elements(elements, max_chars=100, overlap_chars=20)

    assert len(chunks) >= 2
    assert all(not c.is_table for c in chunks)
    assert chunks[0].content[-20:] in chunks[1].content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_chunker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion.chunker'`

- [ ] **Step 3: Write `app/ingestion/chunker.py`**

```python
from dataclasses import dataclass

from app.ingestion.parser import ParsedElement


@dataclass
class Chunk:
    content: str
    page_number: int | None
    is_table: bool


def chunk_elements(
    elements: list[ParsedElement], max_chars: int = 1500, overlap_chars: int = 200
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer_texts: list[str] = []
    buffer_page: int | None = None
    buffer_len = 0

    def flush() -> None:
        nonlocal buffer_texts, buffer_page, buffer_len
        if not buffer_texts:
            return
        chunks.append(Chunk(content="\n\n".join(buffer_texts), page_number=buffer_page, is_table=False))
        buffer_texts = []
        buffer_page = None
        buffer_len = 0

    for element in elements:
        if element.category == "Table":
            flush()
            chunks.append(Chunk(content=element.text, page_number=element.page_number, is_table=True))
            continue

        if buffer_len + len(element.text) > max_chars and buffer_texts:
            previous_content = "\n\n".join(buffer_texts)
            flush()
            overlap_text = previous_content[-overlap_chars:]
            buffer_texts.append(overlap_text)
            buffer_page = element.page_number
            buffer_len = len(overlap_text)

        if buffer_page is None:
            buffer_page = element.page_number
        buffer_texts.append(element.text)
        buffer_len += len(element.text)

    flush()
    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chunker.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ingestion/chunker.py tests/test_chunker.py
git commit -m "feat: add chunker that keeps tables whole and overlaps prose splits"
```

---

### Task 7: Ingestion pipeline orchestrator

**Files:**
- Create: `app/ingestion/pipeline.py`
- Test: `tests/test_ingestion_pipeline.py`

**Interfaces:**
- Consumes: `app.db.SessionLocal` (Task 2), `app.models.Document`, `app.models.Chunk` (Task 2), `app.ingestion.parser.parse_pdf` (Task 5), `app.ingestion.chunker.chunk_elements`, `app.ingestion.chunker.Chunk` (Task 6), `app.ollama_client.embed_text` (Task 4).
- Produces: `app.ingestion.pipeline.ingest_document(document_id: int, file_path: str) -> None` (async) — sets `Document.status` to `processing` → `ready`/`failed`, populates `Chunk` rows, cleans up partial chunks on failure.

- [ ] **Step 1: Write the failing test `tests/test_ingestion_pipeline.py`**

```python
import pytest

from app.ingestion.chunker import Chunk
from app.ingestion.pipeline import ingest_document
from app.models import Chunk as ChunkModel
from app.models import Document, GameSystem


@pytest.mark.asyncio
async def test_ingest_document_success_stores_chunks_and_marks_ready(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()
    document = Document(game_system_id=system.id, filename="phb.pdf", status="pending")
    db_session.add(document)
    db_session.commit()

    monkeypatch.setattr("app.ingestion.pipeline.parse_pdf", lambda path: [])
    monkeypatch.setattr(
        "app.ingestion.pipeline.chunk_elements",
        lambda elements: [Chunk(content="A fighter is skilled in combat.", page_number=1, is_table=False)],
    )

    async def fake_embed_text(text):
        return [0.1] * 768

    monkeypatch.setattr("app.ingestion.pipeline.embed_text", fake_embed_text)

    await ingest_document(document.id, "fake/path.pdf")

    db_session.expire_all()
    refreshed = db_session.get(Document, document.id)
    assert refreshed.status == "ready"
    stored_chunks = db_session.query(ChunkModel).filter_by(document_id=document.id).all()
    assert len(stored_chunks) == 1
    assert stored_chunks[0].content == "A fighter is skilled in combat."
    assert stored_chunks[0].game_system_id == system.id


@pytest.mark.asyncio
async def test_ingest_document_failure_marks_failed_and_cleans_up(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()
    document = Document(game_system_id=system.id, filename="broken.pdf", status="pending")
    db_session.add(document)
    db_session.commit()

    def raise_corrupt(path):
        raise ValueError("corrupt PDF")

    monkeypatch.setattr("app.ingestion.pipeline.parse_pdf", raise_corrupt)

    await ingest_document(document.id, "fake/path.pdf")

    db_session.expire_all()
    refreshed = db_session.get(Document, document.id)
    assert refreshed.status == "failed"
    assert "corrupt PDF" in refreshed.error_message
    stored_chunks = db_session.query(ChunkModel).filter_by(document_id=document.id).all()
    assert stored_chunks == []


@pytest.mark.asyncio
async def test_ingest_document_marks_failed_when_no_content_extracted(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()
    document = Document(game_system_id=system.id, filename="empty.pdf", status="pending")
    db_session.add(document)
    db_session.commit()

    monkeypatch.setattr("app.ingestion.pipeline.parse_pdf", lambda path: [])
    monkeypatch.setattr("app.ingestion.pipeline.chunk_elements", lambda elements: [])

    await ingest_document(document.id, "fake/path.pdf")

    db_session.expire_all()
    refreshed = db_session.get(Document, document.id)
    assert refreshed.status == "failed"
    assert "No content" in refreshed.error_message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ingestion_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion.pipeline'`

- [ ] **Step 3: Write `app/ingestion/pipeline.py`**

```python
from app.db import SessionLocal
from app.ingestion.chunker import chunk_elements
from app.ingestion.parser import parse_pdf
from app.models import Chunk, Document
from app.ollama_client import embed_text


async def ingest_document(document_id: int, file_path: str) -> None:
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None:
            return

        document.status = "processing"
        db.commit()

        try:
            elements = parse_pdf(file_path)
            chunks = chunk_elements(elements)
            if not chunks:
                raise ValueError("No content could be extracted from this PDF")

            for chunk in chunks:
                embedding = await embed_text(chunk.content)
                db.add(
                    Chunk(
                        document_id=document.id,
                        game_system_id=document.game_system_id,
                        content=chunk.content,
                        page_number=chunk.page_number,
                        embedding=embedding,
                    )
                )
            document.status = "ready"
            db.commit()
        except Exception as exc:
            db.rollback()
            db.query(Chunk).filter(Chunk.document_id == document.id).delete()
            document.status = "failed"
            document.error_message = str(exc)
            db.commit()
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ingestion_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/ingestion/pipeline.py tests/test_ingestion_pipeline.py
git commit -m "feat: add ingestion pipeline orchestrator with failure cleanup"
```

---

### Task 8: Documents API (upload, list, delete)

**Files:**
- Modify: `app/schemas.py`
- Create: `app/routes/documents.py`
- Modify: `app/main.py`
- Test: `tests/test_api_documents.py`

**Interfaces:**
- Consumes: `app.db.get_db` (Task 2), `app.models.Document`, `app.models.GameSystem` (Task 2), `app.ingestion.pipeline.ingest_document` (Task 7).
- Produces: `app.schemas.DocumentOut(id, game_system_id, filename, status, error_message, uploaded_at)`. `app.routes.documents.router` mounted at prefix `/systems/{system_id}/documents`, exposing `POST`, `GET`, `DELETE /{document_id}`.

- [ ] **Step 1: Add `DocumentOut` to `app/schemas.py`**

```python
class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_system_id: int
    filename: str
    status: str
    error_message: str | None
    uploaded_at: datetime
```

- [ ] **Step 2: Write the failing test `tests/test_api_documents.py`**

```python
import io
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import GameSystem


def make_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_upload_document_creates_pending_row_and_schedules_ingestion(db_session, monkeypatch):
    fake_ingest = AsyncMock()
    monkeypatch.setattr("app.routes.documents.ingest_document", fake_ingest)

    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    response = client.post(
        f"/systems/{system.id}/documents",
        files={"file": ("phb.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "phb.pdf"
    assert body["status"] == "pending"
    fake_ingest.assert_called_once()
    assert fake_ingest.call_args.args[0] == body["id"]


def test_upload_document_for_missing_system_returns_404(db_session):
    client = make_client(db_session)
    response = client.post(
        "/systems/999/documents",
        files={"file": ("phb.pdf", io.BytesIO(b"content"), "application/pdf")},
    )
    assert response.status_code == 404


def test_list_and_delete_documents(db_session, monkeypatch):
    monkeypatch.setattr("app.routes.documents.ingest_document", AsyncMock())
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    upload_response = client.post(
        f"/systems/{system.id}/documents",
        files={"file": ("phb.pdf", io.BytesIO(b"content"), "application/pdf")},
    )
    document_id = upload_response.json()["id"]

    list_response = client.get(f"/systems/{system.id}/documents")
    assert len(list_response.json()) == 1

    delete_response = client.delete(f"/systems/{system.id}/documents/{document_id}")
    assert delete_response.status_code == 204

    list_response = client.get(f"/systems/{system.id}/documents")
    assert list_response.json() == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_api_documents.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routes.documents'`

- [ ] **Step 4: Write `app/routes/documents.py`**

```python
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingestion.pipeline import ingest_document
from app.models import Document, GameSystem
from app.schemas import DocumentOut

router = APIRouter(prefix="/systems/{system_id}/documents", tags=["documents"])

UPLOAD_DIR = Path(tempfile.gettempdir()) / "rpg-assistant-uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("", response_model=DocumentOut, status_code=201)
def upload_document(
    system_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> Document:
    system = db.get(GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")

    document = Document(game_system_id=system_id, filename=file.filename, status="pending")
    db.add(document)
    db.commit()
    db.refresh(document)

    dest_path = UPLOAD_DIR / f"{document.id}_{file.filename}"
    with dest_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    background_tasks.add_task(ingest_document, document.id, str(dest_path))

    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(system_id: int, db: Session = Depends(get_db)) -> list[Document]:
    return (
        db.query(Document)
        .filter(Document.game_system_id == system_id)
        .order_by(Document.uploaded_at)
        .all()
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(system_id: int, document_id: int, db: Session = Depends(get_db)) -> None:
    document = db.get(Document, document_id)
    if document is None or document.game_system_id != system_id:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(document)
    db.commit()
```

- [ ] **Step 5: Mount the router in `app/main.py`**

```python
from fastapi import FastAPI

from app.routes.documents import router as documents_router
from app.routes.systems import router as systems_router

app = FastAPI(title="TTRPG Rules Assistant")
app.include_router(systems_router)
app.include_router(documents_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_api_documents.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/schemas.py app/routes/documents.py app/main.py tests/test_api_documents.py
git commit -m "feat: add document upload/list/delete API with background ingestion"
```

---

### Task 9: Retrieval module

**Files:**
- Create: `app/retrieval.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: `app.models.Chunk` (Task 2), `app.ollama_client.embed_text` (Task 4).
- Produces: `app.retrieval.retrieve_chunks(db: Session, game_system_id: int, query: str, k: int = 8) -> list[Chunk]` (async), ordered nearest-first by cosine distance, filtered to the given game system.

- [ ] **Step 1: Write the failing test `tests/test_retrieval.py`**

```python
import pytest

from app.models import Chunk, Document, GameSystem
from app.retrieval import retrieve_chunks


@pytest.mark.asyncio
async def test_retrieve_chunks_filters_by_game_system_and_orders_by_similarity(db_session, monkeypatch):
    system_a = GameSystem(name="D&D 5e")
    system_b = GameSystem(name="Call of Cthulhu")
    db_session.add_all([system_a, system_b])
    db_session.commit()

    doc_a = Document(game_system_id=system_a.id, filename="phb.pdf", status="ready")
    doc_b = Document(game_system_id=system_b.id, filename="keeper.pdf", status="ready")
    db_session.add_all([doc_a, doc_b])
    db_session.commit()

    query_vector = [1.0] + [0.0] * 767

    closest = Chunk(
        document_id=doc_a.id,
        game_system_id=system_a.id,
        content="Closest match",
        embedding=query_vector,
    )
    farther = Chunk(
        document_id=doc_a.id,
        game_system_id=system_a.id,
        content="Farther match",
        embedding=[0.0] * 768,
    )
    other_system = Chunk(
        document_id=doc_b.id,
        game_system_id=system_b.id,
        content="Wrong system, should never be returned",
        embedding=query_vector,
    )
    db_session.add_all([closest, farther, other_system])
    db_session.commit()

    async def fake_embed_text(text):
        return query_vector

    monkeypatch.setattr("app.retrieval.embed_text", fake_embed_text)

    results = await retrieve_chunks(db_session, system_a.id, "What is the closest match?", k=5)

    assert [c.content for c in results] == ["Closest match", "Farther match"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_retrieval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.retrieval'`

- [ ] **Step 3: Write `app/retrieval.py`**

```python
from sqlalchemy.orm import Session

from app.models import Chunk
from app.ollama_client import embed_text


async def retrieve_chunks(db: Session, game_system_id: int, query: str, k: int = 8) -> list[Chunk]:
    query_embedding = await embed_text(query)
    return (
        db.query(Chunk)
        .filter(Chunk.game_system_id == game_system_id)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(k)
        .all()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retrieval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/retrieval.py tests/test_retrieval.py
git commit -m "feat: add pgvector-backed retrieval filtered by game system"
```

---

### Task 10: Chat API with SSE streaming

**Files:**
- Create: `app/routes/chat.py`
- Modify: `app/main.py`
- Test: `tests/test_api_chat.py`

**Interfaces:**
- Consumes: `app.retrieval.retrieve_chunks` (Task 9), `app.ollama_client.chat_stream`, `app.ollama_client.OllamaError` (Task 4), `app.models.GameSystem` (Task 2).
- Produces: `app.routes.chat.router` mounted at `/systems/{system_id}/chat`, exposing `POST` returning a `text/event-stream` `StreamingResponse`. Each streamed line is either `data: {"content": "<text chunk>"}\n\n`, `data: {"error": "<message>"}\n\n`, or the terminal `event: done\ndata: {}\n\n`.

- [ ] **Step 1: Write the failing test `tests/test_api_chat.py`**

```python
import json

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import Chunk, Document, GameSystem


def make_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_chat_streams_answer_grounded_in_retrieved_chunks(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()
    document = Document(game_system_id=system.id, filename="phb.pdf", status="ready")
    db_session.add(document)
    db_session.commit()
    db_session.add(
        Chunk(
            document_id=document.id,
            game_system_id=system.id,
            content="A fighter is a master of martial combat.",
            embedding=[0.1] * 768,
        )
    )
    db_session.commit()

    async def fake_retrieve_chunks(db, game_system_id, query, k=8):
        return db.query(Chunk).filter(Chunk.game_system_id == game_system_id).all()

    async def fake_chat_stream(messages):
        assert "master of martial combat" in messages[0]["content"]
        for piece in ["A ", "fighter."]:
            yield piece

    monkeypatch.setattr("app.routes.chat.retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr("app.routes.chat.chat_stream", fake_chat_stream)

    client = make_client(db_session)
    response = client.post(f"/systems/{system.id}/chat", json={"question": "What is a fighter?"})

    assert response.status_code == 200
    events = [line for line in response.text.splitlines() if line.startswith("data: ")]
    payloads = [json.loads(line.removeprefix("data: ")) for line in events]
    assert [p["content"] for p in payloads if "content" in p] == ["A ", "fighter."]


def test_chat_with_no_retrieved_chunks_says_so_explicitly(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    async def fake_retrieve_chunks(db, game_system_id, query, k=8):
        return []

    monkeypatch.setattr("app.routes.chat.retrieve_chunks", fake_retrieve_chunks)

    client = make_client(db_session)
    response = client.post(f"/systems/{system.id}/chat", json={"question": "What is a fighter?"})

    assert response.status_code == 200
    assert "couldn't find anything" in response.text


def test_chat_for_missing_system_returns_404(db_session):
    client = make_client(db_session)
    response = client.post("/systems/999/chat", json={"question": "anything"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_chat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routes.chat'`

- [ ] **Step 3: Write `app/routes/chat.py`**

```python
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import GameSystem
from app.ollama_client import OllamaError, chat_stream
from app.retrieval import retrieve_chunks

router = APIRouter(prefix="/systems/{system_id}/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are a rules assistant for tabletop RPGs. Answer the user's question using "
    "ONLY the rules context provided below. If the context does not contain enough "
    "information to answer, say so explicitly instead of guessing or using outside "
    "knowledge.\n\nContext:\n{context}"
)


class ChatRequest(BaseModel):
    question: str


@router.post("")
async def chat(system_id: int, payload: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    system = db.get(GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")

    chunks = await retrieve_chunks(db, system_id, payload.question)

    async def event_stream() -> AsyncIterator[str]:
        if not chunks:
            message = (
                "I couldn't find anything about that in the ingested rulebooks "
                "for this game system."
            )
            yield f"data: {json.dumps({'content': message})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        context = "\n\n---\n\n".join(chunk.content for chunk in chunks)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(context=context)},
            {"role": "user", "content": payload.question},
        ]
        try:
            async for piece in chat_stream(messages):
                yield f"data: {json.dumps({'content': piece})}\n\n"
        except OllamaError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

- [ ] **Step 4: Mount the router in `app/main.py`**

```python
from fastapi import FastAPI

from app.routes.chat import router as chat_router
from app.routes.documents import router as documents_router
from app.routes.systems import router as systems_router

app = FastAPI(title="TTRPG Rules Assistant")
app.include_router(systems_router)
app.include_router(documents_router)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_api_chat.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/routes/chat.py app/main.py tests/test_api_chat.py
git commit -m "feat: add SSE-streamed chat endpoint grounded in retrieved chunks"
```

---

### Task 11: Frontend pages (systems list, system detail, chat)

**Files:**
- Create: `app/templates/base.html`
- Create: `app/templates/systems.html`
- Create: `app/templates/system_detail.html`
- Create: `app/templates/chat.html`
- Create: `app/static/style.css`
- Create: `app/static/app.js`
- Create: `app/routes/pages.py`
- Modify: `app/main.py`
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: `app.db.get_db`, `app.models.GameSystem` (Task 2). Calls the JSON APIs from Tasks 3, 8, 10 client-side via `fetch`.
- Produces: `app.routes.pages.router` exposing `GET /`, `GET /systems/{system_id}`, `GET /systems/{system_id}/chat` (HTML pages, distinct from the JSON API routes which use `POST`/`DELETE` on overlapping paths).

- [ ] **Step 1: Write the failing test `tests/test_pages.py`**

```python
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import GameSystem


def make_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_systems_page_lists_created_systems(db_session):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    response = client.get("/")

    assert response.status_code == 200
    assert "D&D 5e" in response.text
    assert 'id="create-system-form"' in response.text


def test_system_detail_page_renders_upload_form(db_session):
    system = GameSystem(name="Call of Cthulhu")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    response = client.get(f"/systems/{system.id}")

    assert response.status_code == 200
    assert "Call of Cthulhu" in response.text
    assert 'id="upload-form"' in response.text


def test_system_detail_page_404s_for_missing_system(db_session):
    client = make_client(db_session)
    response = client.get("/systems/999")
    assert response.status_code == 404


def test_chat_page_renders_chat_form(db_session):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    response = client.get(f"/systems/{system.id}/chat")

    assert response.status_code == 200
    assert 'id="chat-form"' in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pages.py -v`
Expected: FAIL with 404s (no page routes mounted yet)

- [ ] **Step 3: Write `app/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>TTRPG Rules Assistant</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header><a href="/">TTRPG Rules Assistant</a></header>
    <main>
        {% block content %}{% endblock %}
    </main>
    <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Write `app/templates/systems.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>Game Systems</h1>
<form id="create-system-form">
    <input type="text" name="name" placeholder="e.g. D&amp;D 5e" required>
    <button type="submit">Create</button>
</form>
<ul id="systems-list">
    {% for system in systems %}
    <li>
        <a href="/systems/{{ system.id }}">{{ system.name }}</a>
        &mdash;
        <a href="/systems/{{ system.id }}/chat">Chat</a>
        <button class="delete-system" data-system-id="{{ system.id }}">Delete</button>
    </li>
    {% endfor %}
</ul>
{% endblock %}
```

- [ ] **Step 5: Write `app/templates/system_detail.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>{{ system.name }}</h1>
<p><a href="/systems/{{ system.id }}/chat">Go to chat</a></p>

<h2>Upload sourcebook</h2>
<form id="upload-form" data-system-id="{{ system.id }}">
    <input type="file" name="file" accept="application/pdf" required>
    <button type="submit">Upload</button>
</form>

<h2>Documents</h2>
<ul id="documents-list" data-system-id="{{ system.id }}"></ul>
{% endblock %}
```

- [ ] **Step 6: Write `app/templates/chat.html`**

```html
{% extends "base.html" %}
{% block content %}
<h1>Chat &mdash; {{ system.name }}</h1>
<div id="chat-log"></div>
<form id="chat-form" data-system-id="{{ system.id }}">
    <input type="text" name="question" placeholder="Ask a rules question..." required autocomplete="off">
    <button type="submit">Ask</button>
</form>
{% endblock %}
```

- [ ] **Step 7: Write `app/static/style.css`**

```css
body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
header a { text-decoration: none; font-weight: bold; }
ul { list-style: none; padding: 0; }
li { margin: 0.5rem 0; }
#chat-log { border: 1px solid #ccc; border-radius: 4px; padding: 1rem; min-height: 200px; margin-bottom: 1rem; }
#chat-form { display: flex; gap: 0.5rem; }
#chat-form input { flex: 1; }
```

- [ ] **Step 8: Write `app/static/app.js`**

```javascript
document.addEventListener("DOMContentLoaded", () => {
  const createForm = document.getElementById("create-system-form");
  if (createForm) {
    createForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const name = new FormData(createForm).get("name");
      await fetch("/systems", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      window.location.reload();
    });
  }

  document.querySelectorAll(".delete-system").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetch(`/systems/${button.dataset.systemId}`, { method: "DELETE" });
      window.location.reload();
    });
  });

  const uploadForm = document.getElementById("upload-form");
  if (uploadForm) {
    uploadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const systemId = uploadForm.dataset.systemId;
      const formData = new FormData(uploadForm);
      await fetch(`/systems/${systemId}/documents`, { method: "POST", body: formData });
      uploadForm.reset();
      refreshDocuments(systemId);
    });
  }

  const documentsList = document.getElementById("documents-list");
  if (documentsList) {
    const systemId = documentsList.dataset.systemId;
    refreshDocuments(systemId);
    setInterval(() => refreshDocuments(systemId), 2500);
  }

  const chatForm = document.getElementById("chat-form");
  if (chatForm) {
    chatForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const systemId = chatForm.dataset.systemId;
      const question = new FormData(chatForm).get("question");
      appendChatEntry("You", question);
      chatForm.reset();
      await streamChatResponse(systemId, question);
    });
  }
});

async function refreshDocuments(systemId) {
  const documentsList = document.getElementById("documents-list");
  const response = await fetch(`/systems/${systemId}/documents`);
  const documents = await response.json();
  documentsList.innerHTML = documents
    .map(
      (doc) =>
        `<li>${doc.filename} — <strong>${doc.status}</strong>` +
        `${doc.error_message ? ` (${doc.error_message})` : ""}</li>`
    )
    .join("");
}

async function streamChatResponse(systemId, question) {
  const response = await fetch(`/systems/${systemId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const entry = appendChatEntry("Assistant", "");
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = JSON.parse(line.slice(6));
      if (payload.content) entry.textContent += payload.content;
      if (payload.error) entry.textContent += `[error: ${payload.error}]`;
    }
  }
}

function appendChatEntry(speaker, text) {
  const log = document.getElementById("chat-log");
  const entry = document.createElement("p");
  entry.innerHTML = `<strong>${speaker}:</strong> `;
  const span = document.createElement("span");
  span.textContent = text;
  entry.appendChild(span);
  log.appendChild(entry);
  return span;
}
```

- [ ] **Step 9: Write `app/routes/pages.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import GameSystem

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def systems_page(request: Request, db: Session = Depends(get_db)):
    systems = db.query(GameSystem).order_by(GameSystem.created_at).all()
    return templates.TemplateResponse(request, "systems.html", {"systems": systems})


@router.get("/systems/{system_id}")
def system_detail_page(system_id: int, request: Request, db: Session = Depends(get_db)):
    system = db.get(GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")
    return templates.TemplateResponse(request, "system_detail.html", {"system": system})


@router.get("/systems/{system_id}/chat")
def chat_page(system_id: int, request: Request, db: Session = Depends(get_db)):
    system = db.get(GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")
    return templates.TemplateResponse(request, "chat.html", {"system": system})
```

- [ ] **Step 10: Wire everything into `app/main.py`**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.chat import router as chat_router
from app.routes.documents import router as documents_router
from app.routes.pages import router as pages_router
from app.routes.systems import router as systems_router

app = FastAPI(title="TTRPG Rules Assistant")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(systems_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(pages_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 11: Run tests to verify they pass**

Run: `pytest tests/test_pages.py -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add app/templates app/static app/routes/pages.py app/main.py tests/test_pages.py
git commit -m "feat: add server-rendered frontend for systems, uploads, and chat"
```

---

### Task 12: Full docker-compose wiring with Ollama and startup migrations

**Files:**
- Create: `entrypoint.sh`
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Create: `README.md` (overwrite existing placeholder)

**Interfaces:**
- Consumes: `app.db.init_db` (Task 2), `app.main.app` (Task 1).
- Produces: a working `docker compose up --build` that serves the app at `http://localhost:8000` with Postgres/pgvector and Ollama (with `llama1.1:8b`/`nomic-embed-text` pre-pulled) fully containerized.

- [ ] **Step 1: Write `entrypoint.sh`**

```bash
#!/bin/sh
set -e
python -c "from app.db import init_db; init_db()"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Modify `Dockerfile` to copy and make `entrypoint.sh` executable**

Add this line immediately after the existing `COPY . .` line (before the `CMD` line):

```dockerfile
RUN chmod +x entrypoint.sh
```

- [ ] **Step 3: Rewrite `docker-compose.yml` with all three services**

```yaml
services:
  app:
    build: .
    entrypoint: ["/app/entrypoint.sh"]
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:postgres@postgres:5432/rpg_assistant
      OLLAMA_BASE_URL: http://ollama:11434
    depends_on:
      postgres:
        condition: service_healthy
      ollama-init:
        condition: service_completed_successfully
    volumes:
      - .:/app

  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: rpg_assistant
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 3s
      timeout: 3s
      retries: 20

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 5s
      timeout: 5s
      retries: 20

  ollama-init:
    image: ollama/ollama:latest
    depends_on:
      ollama:
        condition: service_healthy
    entrypoint: ["sh", "-c"]
    command:
      - "OLLAMA_HOST=ollama:11434 ollama pull llama3.1:8b && OLLAMA_HOST=ollama:11434 ollama pull nomic-embed-text"

volumes:
  pgdata:
  ollama_models:
```

- [ ] **Step 4: Write `README.md`**

```markdown
# TTRPG Rules Assistant

A local, dockerized RAG chat tool for GMs: upload rulebook PDFs grouped by
game system, then ask rules questions in a chat UI answered from the
ingested text.

## Running

1. `cp .env.example .env`
2. `docker compose up --build`
3. Wait for the `ollama-init` service to finish pulling models (check with
   `docker compose logs -f ollama-init`).
4. Open http://localhost:8000

## Stack

FastAPI + Postgres/pgvector + Ollama (`llama3.1:8b` for chat,
`nomic-embed-text` for embeddings), all containerized. PDF parsing uses
`unstructured` in hi-res mode for accurate table extraction.
```

- [ ] **Step 5: Verify end-to-end manually**

Run: `docker compose up --build`
Expected: all four services start; `ollama-init` logs show both models pulled and the container exits 0; `app` logs show uvicorn running on port 8000.

Run: `curl http://localhost:8000/health`
Expected: `{"status":"ok"}`

Run:
```bash
curl -X POST http://localhost:8000/systems -H "Content-Type: application/json" -d '{"name": "D&D 5e"}'
```
Expected: JSON body with `id` and `"name": "D&D 5e"`.

Run (replace `1` with the returned id and `/path/to/a.pdf` with a real rulebook PDF):
```bash
curl -X POST http://localhost:8000/systems/1/documents -F "file=@/path/to/a.pdf"
```
Expected: JSON body with `"status": "pending"`.

Run repeatedly until status changes:
```bash
curl http://localhost:8000/systems/1/documents
```
Expected: eventually `"status": "ready"`.

Run:
```bash
curl -N -X POST http://localhost:8000/systems/1/chat -H "Content-Type: application/json" -d '{"question": "How does initiative work?"}'
```
Expected: a stream of `data: {"content": "..."}` lines forming a coherent answer, followed by `event: done`.

- [ ] **Step 6: Commit**

```bash
git add entrypoint.sh Dockerfile docker-compose.yml README.md
git commit -m "feat: wire full docker-compose stack with Ollama model pulling and DB migrations"
```

---

## Self-Review Notes

- **Spec coverage:** every spec section maps to a task — architecture/containers (1, 12), data model (2), PDF parsing/table handling (5), ingestion pipeline incl. failure cleanup (7), chunking incl. table-never-split rule (6), chat/retrieval flow incl. SSE and no-context handling (9, 10), API surface (3, 8, 10), frontend (11), error handling (7, 10), Docker (1, 12). No spec requirement was left without a task.
- **Placeholder scan:** no TBD/TODO; every step has complete, runnable code or exact commands.
- **Type consistency:** `ParsedElement` (Task 5) → `chunk_elements` (Task 6) → `Chunk` (Task 6, consumed by Task 7) → `Chunk` ORM model (Task 2, distinct name collision noted: `app.ingestion.chunker.Chunk` vs `app.models.Chunk` — Task 7 imports both and aliases the ORM one as `Chunk` from `app.models` while using `chunk_elements`'s return type positionally, matching the import style shown in Task 7's code). `retrieve_chunks` (Task 9) returns `app.models.Chunk` rows, consumed correctly by Task 10's `chat` route.
