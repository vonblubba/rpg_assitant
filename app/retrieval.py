import asyncio

from sqlalchemy.orm import Session

from app.models import Chunk
from app.ollama_client import embed_text


# Calibrated against the ingested corpus: on-topic queries scored 0.16-0.31
# cosine distance against nomic-embed-text, while off-topic and cross-system
# queries scored 0.35-0.53. 0.33 sits in that gap.
MAX_RELEVANT_DISTANCE = 0.33


async def retrieve_chunks(
    db: Session, game_system_id: int, query: str, k: int = 8, max_distance: float = MAX_RELEVANT_DISTANCE
) -> list[Chunk]:
    query_embedding = await embed_text(query)
    distance = Chunk.embedding.cosine_distance(query_embedding)
    return await asyncio.to_thread(
        lambda: db.query(Chunk)
        .filter(Chunk.game_system_id == game_system_id)
        .filter(distance < max_distance)
        .order_by(distance)
        .limit(k)
        .all()
    )
