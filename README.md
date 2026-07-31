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

## GPU acceleration

The `ollama` service is configured to use an NVIDIA GPU, which requires
[`nvidia-container-toolkit`](https://github.com/NVIDIA/nvidia-container-toolkit)
installed on the host. If you don't have an NVIDIA GPU, remove the `deploy:`
block from the `ollama` service in `docker-compose.yml` — Ollama will then
run on CPU.
