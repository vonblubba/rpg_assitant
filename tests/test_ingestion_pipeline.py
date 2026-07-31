import pytest

from app.ingestion.chunker import Chunk
from app.ingestion.pipeline import ingest_document
from app.models import Chunk as ChunkModel
from app.models import Document, GameSystem


@pytest.mark.asyncio
async def test_ingest_document_success_stores_chunks_and_marks_ready(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()
    document = Document(game_system_id=system.id, filename="phb.pdf", status="pending")
    db_session.add(document)
    db_session.commit()

    monkeypatch.setattr("app.ingestion.pipeline.parse_pdf", lambda path: [])
    monkeypatch.setattr(
        "app.ingestion.pipeline.chunk_elements",
        lambda elements: [Chunk(content="A fighter is skilled in combat.", page_number=1, is_table=False)],
    )

    async def fake_embed_text(text):
        return [0.1] * 768

    monkeypatch.setattr("app.ingestion.pipeline.embed_text", fake_embed_text)

    await ingest_document(document.id, "fake/path.pdf")

    db_session.expire_all()
    refreshed = db_session.get(Document, document.id)
    assert refreshed.status == "ready"
    stored_chunks = db_session.query(ChunkModel).filter_by(document_id=document.id).all()
    assert len(stored_chunks) == 1
    assert stored_chunks[0].content == "A fighter is skilled in combat."
    assert stored_chunks[0].game_system_id == system.id


@pytest.mark.asyncio
async def test_ingest_document_failure_marks_failed_and_cleans_up(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()
    document = Document(game_system_id=system.id, filename="broken.pdf", status="pending")
    db_session.add(document)
    db_session.commit()

    def raise_corrupt(path):
        raise ValueError("corrupt PDF")

    monkeypatch.setattr("app.ingestion.pipeline.parse_pdf", raise_corrupt)

    await ingest_document(document.id, "fake/path.pdf")

    db_session.expire_all()
    refreshed = db_session.get(Document, document.id)
    assert refreshed.status == "failed"
    assert "corrupt PDF" in refreshed.error_message
    stored_chunks = db_session.query(ChunkModel).filter_by(document_id=document.id).all()
    assert stored_chunks == []


@pytest.mark.asyncio
async def test_ingest_document_marks_failed_when_no_content_extracted(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()
    document = Document(game_system_id=system.id, filename="empty.pdf", status="pending")
    db_session.add(document)
    db_session.commit()

    monkeypatch.setattr("app.ingestion.pipeline.parse_pdf", lambda path: [])
    monkeypatch.setattr("app.ingestion.pipeline.chunk_elements", lambda elements: [])

    await ingest_document(document.id, "fake/path.pdf")

    db_session.expire_all()
    refreshed = db_session.get(Document, document.id)
    assert refreshed.status == "failed"
    assert "No content" in refreshed.error_message
