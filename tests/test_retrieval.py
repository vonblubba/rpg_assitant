import pytest

from app.models import Chunk, Document, GameSystem
from app.retrieval import retrieve_chunks


@pytest.mark.asyncio
async def test_retrieve_chunks_filters_by_game_system_and_orders_by_similarity(db_session, monkeypatch):
    system_a = GameSystem(name="D&D 5e")
    system_b = GameSystem(name="Call of Cthulhu")
    db_session.add_all([system_a, system_b])
    db_session.commit()

    doc_a = Document(game_system_id=system_a.id, filename="phb.pdf", status="ready")
    doc_b = Document(game_system_id=system_b.id, filename="keeper.pdf", status="ready")
    db_session.add_all([doc_a, doc_b])
    db_session.commit()

    query_vector = [1.0] + [0.0] * 767

    closest = Chunk(
        document_id=doc_a.id,
        game_system_id=system_a.id,
        content="Closest match",
        embedding=query_vector,
    )
    farther = Chunk(
        document_id=doc_a.id,
        game_system_id=system_a.id,
        content="Farther match",
        embedding=[0.0] * 768,
    )
    other_system = Chunk(
        document_id=doc_b.id,
        game_system_id=system_b.id,
        content="Wrong system, should never be returned",
        embedding=query_vector,
    )
    db_session.add_all([closest, farther, other_system])
    db_session.commit()

    async def fake_embed_text(text):
        return query_vector

    monkeypatch.setattr("app.retrieval.embed_text", fake_embed_text)

    results = await retrieve_chunks(db_session, system_a.id, "What is the closest match?", k=5)

    assert [c.content for c in results] == ["Closest match", "Farther match"]
