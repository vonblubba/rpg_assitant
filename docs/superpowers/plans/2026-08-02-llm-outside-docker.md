# Move LLM Outside Docker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop running Ollama inside docker-compose and point the (still-dockerized) app service at a host-native Ollama instance instead.

**Architecture:** The `app` service keeps running in Docker via docker-compose. The `ollama` and `ollama-init` services and the `ollama_models` volume are removed. The app reaches the host-native Ollama over `host.docker.internal`, which is made resolvable on Linux via an explicit `extra_hosts: host-gateway` entry (Docker Desktop on Mac/Windows resolves it automatically). `app/config.py`'s hardcoded default for `ollama_base_url` moves from the old in-network service name to `host.docker.internal`.

**Tech Stack:** Python 3.12, FastAPI, pydantic-settings, Docker Compose.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-02-llm-outside-docker-design.md`
- The app service must stay in Docker; only Ollama moves out (per approved design).
- Use `host.docker.internal` + `extra_hosts: host-gateway` for host reachability (per approved design), not `network_mode: host`.
- Remove `ollama` + `ollama-init` services and the `ollama_models` volume entirely (per approved design) — no commented-out fallback.

---

### Task 1: Update the app's default Ollama URL

**Files:**
- Modify: `app/config.py:9`
- Test: `tests/test_config.py` (new file)

**Interfaces:**
- Produces: `Settings.ollama_base_url` default value of `"http://host.docker.internal:11434"` (was `"http://ollama:11434"`). No signature change — same field, same type (`str`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from app.config import Settings


def test_ollama_base_url_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://postgres:postgres@localhost:5432/rpg_assistant",
    )
    assert settings.ollama_base_url == "http://host.docker.internal:11434"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `assert 'http://ollama:11434' == 'http://host.docker.internal:11434'`

- [ ] **Step 3: Update the default**

In `app/config.py`, change line 9 from:

```python
    ollama_base_url: str = "http://ollama:11434"
```

to:

```python
    ollama_base_url: str = "http://host.docker.internal:11434"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "fix: default OLLAMA_BASE_URL to host.docker.internal for native Ollama"
```

---

### Task 2: Remove dockerized Ollama and wire the app to the host instance

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `Settings.ollama_base_url` default from Task 1 (only relevant if `OLLAMA_BASE_URL` env var were unset; here we set it explicitly in compose anyway).
- Produces: nothing consumed by later tasks (final task in this plan).

- [ ] **Step 1: Remove the `ollama` and `ollama-init` services and the `ollama_models` volume**

In `docker-compose.yml`, delete the `ollama` service block (lines 34–51), the `ollama-init` service block (lines 53–60), and the `ollama_models:` line from the `volumes:` section at the bottom.

- [ ] **Step 2: Update the `app` service to depend on nothing Ollama-related, add `extra_hosts`, and point at the host**

Change the `app` service in `docker-compose.yml` from:

```yaml
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
```

to:

```yaml
  app:
    build: .
    entrypoint: ["/app/entrypoint.sh"]
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:postgres@postgres:5432/rpg_assistant
      OLLAMA_BASE_URL: http://host.docker.internal:11434
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - .:/app
```

The final `docker-compose.yml` should read:

```yaml
services:
  app:
    build: .
    entrypoint: ["/app/entrypoint.sh"]
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:postgres@postgres:5432/rpg_assistant
      OLLAMA_BASE_URL: http://host.docker.internal:11434
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      postgres:
        condition: service_healthy
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

volumes:
  pgdata:
```

- [ ] **Step 3: Verify the compose file is valid and has the expected values**

Run: `docker compose config`
Expected: renders successfully (no YAML/schema errors), and the output's `app` service contains `OLLAMA_BASE_URL: http://host.docker.internal:11434` and `host.docker.internal:host-gateway` under `extra_hosts`, with no `ollama` or `ollama-init` service present.

Run: `docker compose config --services`
Expected: prints exactly:
```
app
postgres
```

- [ ] **Step 4: Update README.md**

Replace the full contents of `README.md` with:

```markdown
# TTRPG Rules Assistant

A local RAG chat tool for GMs: upload rulebook PDFs grouped by game system,
then ask rules questions in a chat UI answered from the ingested text. The
app and Postgres run in Docker; Ollama runs natively on the host.

## Running

1. Install [Ollama](https://ollama.com) on the host and start it (`ollama
   serve`), then pull the required models:
   ```
   ollama pull llama3.1:8b
   ollama pull nomic-embed-text
   ```
2. `cp .env.example .env`
3. `docker compose up --build`
4. Open http://localhost:8000

The `app` container reaches the host's Ollama at
`http://host.docker.internal:11434` (see `OLLAMA_BASE_URL` in
`docker-compose.yml`).

## Stack

FastAPI + Postgres/pgvector (containerized) + Ollama (`llama3.1:8b` for
chat, `nomic-embed-text` for embeddings), running natively on the host. PDF
parsing uses `unstructured` in hi-res mode for accurate table extraction.
```

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml README.md
git commit -m "fix: remove dockerized Ollama, reach host-native instance instead"
```
