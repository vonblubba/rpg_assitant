# Move LLM outside Docker

## Problem

`docker-compose.yml` currently runs Ollama itself (`ollama` + `ollama-init` services) as
part of the stack. The LLM is moving to run natively on the host instead (already the
case for local, non-Docker runs). The `app` service, which stays in Docker, needs to be
able to reach that host-native Ollama instance.

## Design

- **docker-compose.yml**
  - Remove the `ollama` and `ollama-init` services and the `ollama_models` volume.
  - Remove the `app` service's `depends_on: ollama-init`.
  - Add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `app` service so it
    can resolve the Docker host on Linux (this mapping is automatic on Docker
    Desktop for Mac/Windows, but requires this explicit entry on Linux).
  - Change the `app` service's `OLLAMA_BASE_URL` env var to
    `http://host.docker.internal:11434`.

- **app/config.py**
  - No code change required — `ollama_base_url` is already a configurable `Settings`
    field sourced from env vars / `.env`. Update its hardcoded default from
    `http://ollama:11434` to `http://host.docker.internal:11434` so the default matches
    the new topology when no env var is set.

- **.env / .env.example**
  - No change — these already target `http://localhost:11434` for running the app
    itself outside Docker.

- **README.md**
  - Add a note that Ollama must already be running natively on the host (`ollama
    serve`) with the required models pulled (`llama3.1:8b`, `nomic-embed-text`) before
    `docker compose up`, since docker-compose no longer provisions it.

## Out of scope

- Moving the `app` service itself out of Docker.
- Automating model pulls on the host.
