import asyncio
import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import GameSystem
from app.ollama_client import OllamaError, chat_stream
from app.retrieval import build_search_query, retrieve_chunks

router = APIRouter(prefix="/systems/{system_id}/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are a rules assistant for tabletop RPGs. Answer the user's question using "
    "ONLY the rules context provided below. If the context does not contain enough "
    "information to answer, say so explicitly instead of guessing or using outside "
    "knowledge.\n\nContext:\n{context}"
)

# Caps how much prior conversation gets replayed to the LLM each turn, so a
# long session doesn't grow the prompt without bound.
MAX_HISTORY_MESSAGES = 10


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = Field(default_factory=list)


@router.post("")
async def chat(system_id: int, payload: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    system = await asyncio.to_thread(db.get, GameSystem, system_id)
    if system is None:
        raise HTTPException(status_code=404, detail="Game system not found")

    async def event_stream() -> AsyncIterator[str]:
        recent_turns = [message.content for message in payload.history]
        search_query = build_search_query(payload.question, recent_turns)
        try:
            chunks = await retrieve_chunks(db, system_id, search_query)
        except OllamaError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

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
            *(
                {"role": message.role, "content": message.content}
                for message in payload.history[-MAX_HISTORY_MESSAGES:]
            ),
            {"role": "user", "content": payload.question},
        ]
        try:
            async for piece in chat_stream(messages):
                yield f"data: {json.dumps({'content': piece})}\n\n"
        except OllamaError as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
