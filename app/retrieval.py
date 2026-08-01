import asyncio

from sqlalchemy.orm import Session

from app.models import Chunk
from app.ollama_client import embed_text


# Calibrated against the ingested corpus using natural, loosely-phrased
# questions (not ones echoing the book's own wording): genuinely answerable
# queries' best match ranged 0.20-0.39 cosine distance against
# nomic-embed-text, while off-topic queries' best match was never better
# than 0.46. 0.42 sits in that gap.
MAX_RELEVANT_DISTANCE = 0.42


# How many of the most recent prior turns to fold into the retrieval query.
# Short follow-ups ("option 1", "choose freely") carry no searchable meaning
# on their own; combining them with the turns that gave them meaning lets
# embedding search find the relevant chunk.
SEARCH_QUERY_CONTEXT_TURNS = 2


def build_search_query(question: str, recent_turns: list[str]) -> str:
    return " ".join([*recent_turns[-SEARCH_QUERY_CONTEXT_TURNS:], question])


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
