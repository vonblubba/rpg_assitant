import asyncio

from sqlalchemy.orm import Session

from app.models import Chunk
from app.ollama_client import embed_text


async def retrieve_chunks(db: Session, game_system_id: int, query: str, k: int = 8) -> list[Chunk]:
    query_embedding = await embed_text(query)
    return await asyncio.to_thread(
        lambda: db.query(Chunk)
        .filter(Chunk.game_system_id == game_system_id)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(k)
        .all()
    )
