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
