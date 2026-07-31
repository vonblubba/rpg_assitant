import json
from collections.abc import AsyncIterator

import httpx

from app.config import get_settings


class OllamaError(Exception):
    pass


# nomic-embed-text's actual context length is 2048 tokens (its GGUF metadata),
# regardless of the num_ctx=8192 the Ollama model card advertises — passing a
# larger num_ctx does not raise the real limit. A single unsplit table chunk
# can exceed this, so truncate conservatively before sending.
EMBEDDING_MAX_CHARS = 6000


async def embed_text(text: str) -> list[float]:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=60) as client:
        try:
            response = await client.post(
                "/api/embeddings",
                json={"model": settings.embedding_model, "prompt": text[:EMBEDDING_MAX_CHARS]},
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
