# TTRPG Rules Assistant — Design

## Purpose

A personal, local tool for a GM to ingest TTRPG rulebook PDFs and ask natural-language
rules questions in a chat interface, with answers grounded in the ingested rules text
via retrieval-augmented generation (RAG).

## Scope

- Single user (the GM running it locally), no auth/multi-tenancy.
- Fully local/self-hosted: no external API calls, no cloud LLM providers.
- Entire stack runs via `docker compose up` — app, database, and LLM serving are all
  containerized.
- PDFs are grouped under **game systems** (e.g. "D&D 5e", "Call of Cthulhu"). Each game
  system can have multiple sourcebook PDFs. Chat questions are asked against one active
  game system at a time, retrieving across all of that system's sourcebooks.
- Source citations (book/page) are a "nice to have," not a hard requirement — page
  numbers are stored when available but the UI doesn't need to prominently surface them
  in v1.
- No conversation memory across turns for v1 — each question triggers an independent
  retrieval + answer.

## Non-goals (v1)

- Multi-user accounts, auth, or per-user data isolation.
- Hosting for other people / remote access.
- Cloud LLM or embedding providers.
- Persisted chat history across sessions.
- Guaranteed precise page-level citations in every answer.

## Architecture

Three containers via `docker-compose.yml`, all local:

- **`app`** — FastAPI backend + server-rendered frontend (Jinja2 templates + vanilla
  JS). Hosts the ingestion pipeline and chat/retrieval logic. No separate frontend
  build step.
- **`postgres`** — Postgres with the `pgvector` extension. Stores game systems,
  documents, and chunks with embeddings.
- **`ollama`** — Serves both the chat model and the embedding model over its HTTP API.
  Model weights are cached in a named volume so they aren't re-pulled on every rebuild.

Default models: `llama3.1:8b` for chat, `nomic-embed-text` for embeddings. Configurable
via environment variables.

On `app` startup: run DB migrations and ensure required Ollama models are pulled
(`ollama pull`) before serving traffic, so `docker compose up` is the only setup step
needed.

## Data model (Postgres)

- **`game_systems`**: `id`, `name`, `created_at`
- **`documents`**: `id`, `game_system_id` (FK), `filename`, `status`
  (`pending`/`processing`/`ready`/`failed`), `error_message` (nullable), `uploaded_at`
- **`chunks`**: `id`, `document_id` (FK), `game_system_id` (denormalized for fast
  filtered retrieval), `content` (Markdown text, incl. rendered tables), `page_number`
  (nullable, best-effort from parser metadata), `embedding` (`vector(768)`, matching
  `nomic-embed-text` dimensions)

Indexes: an `ivfflat`/`hnsw` index on `chunks.embedding`, and a plain index on
`chunks.game_system_id` (every retrieval query filters by the active system).

Deleting a `game_systems` row cascades to its `documents` and `chunks`. Deleting a
`documents` row cascades to its `chunks`.

## PDF parsing / ingestion pipeline

Uses `unstructured` (hi-res mode, local layout-detection models — no cloud calls) to
handle table-heavy rulebooks accurately.

Triggered on PDF upload, per game system:

1. UI uploads a PDF → API creates a `documents` row (`status=pending`), saves the file,
   schedules a FastAPI `BackgroundTask`, and returns immediately (upload request does
   not block on parsing).
2. Background task sets `status=processing`, runs `unstructured` to partition the PDF
   into elements (text, tables, titles) with page-number metadata.
3. Elements are grouped into chunks:
   - Tables are kept whole as single chunks (never split mid-table) and rendered as
     Markdown.
   - Prose is chunked by section/heading with a max token size and modest overlap
     between adjacent chunks.
4. Each chunk's text is embedded via Ollama's embedding endpoint (`nomic-embed-text`);
   chunk + embedding + `page_number` + `document_id` + `game_system_id` are written to
   `chunks`.
5. On success: `status=ready`. On failure (corrupt PDF, parser exception, Ollama
   unreachable, or zero usable elements extracted): `status=failed` with
   `error_message` set, and any partial chunks from that document are deleted so a
   retry starts clean.

The UI polls document status (e.g. every 2–3s while any document for the active system
is `pending`/`processing`) so large sourcebooks don't block the page.

## Chat / retrieval flow

1. GM selects an active game system, then asks a question.
2. Backend embeds the question with the same Ollama embedding model, runs a pgvector
   cosine-similarity top-K query filtered to the active `game_system_id` (K default:
   ~8, configurable).
3. Retrieved chunks are assembled into a context block and sent to the chat model with
   a system prompt instructing it to answer only from the provided rules context, and
   to say so explicitly when the context doesn't cover the question (rather than
   answering from general/base-model knowledge).
4. The response is streamed to the browser via Server-Sent Events.
5. No multi-turn conversational memory is fed into retrieval for v1 — each question is
   answered independently.

## API surface

- `POST /systems` — create a game system (`name`)
- `GET /systems` — list game systems
- `DELETE /systems/{id}` — delete a system (cascades to documents/chunks)
- `POST /systems/{id}/documents` — upload a PDF (multipart); returns document row with
  `status=pending`
- `GET /systems/{id}/documents` — list documents + statuses (polled by UI)
- `DELETE /systems/{id}/documents/{doc_id}` — delete a document and its chunks
- `POST /systems/{id}/chat` — ask a question; SSE-streamed answer

## Frontend

Server-rendered HTML (Jinja2) + vanilla JS for interactive bits (status polling,
upload, SSE consumption). Three views:

- **Systems list** — create/select/delete game systems
- **System detail** — upload PDFs, see documents with live status badges
- **Chat** — for the selected system, a chat box with streaming responses

## Error handling

- **Ingestion failures** (corrupt PDF, parser exception, Ollama unreachable, zero
  extracted elements): document marked `failed` with a human-readable
  `error_message` shown in the UI; partial chunks cleaned up; GM can delete and
  re-upload.
- **Chat-time failures**: if retrieval returns no chunks, the assistant says so
  explicitly instead of answering from general knowledge; if Ollama is unreachable,
  the API returns a clear error surfaced in the chat UI instead of hanging silently.

## Testing

- **Unit tests**: chunking logic (tables stay whole; prose splits respect
  size/overlap), retrieval query construction (correct filtering by
  `game_system_id`), prompt assembly.
- **Integration tests**: ingestion pipeline against fixture PDFs (including at least
  one with a table) run against a real test Postgres+pgvector; Ollama calls mocked at
  the HTTP layer for speed/determinism; one slower end-to-end smoke test may hit a
  real local Ollama if available.
- **API tests**: FastAPI `TestClient` covering CRUD endpoints and the chat endpoint's
  SSE streaming contract (mocked Ollama).
