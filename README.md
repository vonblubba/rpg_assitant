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
