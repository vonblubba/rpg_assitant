# TTRPG Rules Assistant

A local RAG chat tool for GMs: upload rulebook PDFs grouped by game system,
then ask rules questions in a chat UI answered from the ingested text. The
app and Postgres run in Docker; Ollama runs natively on the host.

## Running

> **Upgrading from the old dockerized-Ollama setup?** Run
> `docker compose down --remove-orphans` to remove the stale `ollama` /
> `ollama-init` containers, then find and remove the orphaned model
> volume: `docker volume ls | grep ollama_models`, then
> `docker volume rm <name>`.

1. Install [Ollama](https://ollama.com) on the host and start it, bound to
   all interfaces so the `app` container can reach it (Ollama's default
   bind, `127.0.0.1:11434`, is loopback-only and `host.docker.internal`
   resolves to the Docker bridge gateway, not loopback).

   - Via systemd: `sudo systemctl edit ollama`, add:
     ```
     [Service]
     Environment="OLLAMA_HOST=0.0.0.0"
     ```
     then `sudo systemctl restart ollama`.
   - Manual/foreground: `OLLAMA_HOST=0.0.0.0 ollama serve`.

   (If you run a host firewall like ufw/firewalld, make sure it allows the
   Docker bridge subnet to reach port 11434.)

   Then pull the required models:
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
chat, `nomic-embed-text` for embeddings), running natively on the host —
this also means any available GPU is picked up automatically, with no
container toolkit needed. PDF parsing uses `unstructured` in hi-res mode
for accurate table extraction.
