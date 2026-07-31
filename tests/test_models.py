from app.models import Chunk, Document, GameSystem


def test_create_game_system_document_and_chunk(db_session):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    document = Document(game_system_id=system.id, filename="phb.pdf", status="ready")
    db_session.add(document)
    db_session.commit()

    chunk = Chunk(
        document_id=document.id,
        game_system_id=system.id,
        content="A fighter is a master of martial combat.",
        page_number=12,
        embedding=[0.0] * 768,
    )
    db_session.add(chunk)
    db_session.commit()

    fetched = db_session.get(Chunk, chunk.id)
    assert fetched.content.startswith("A fighter")
    assert fetched.page_number == 12
    assert len(fetched.embedding) == 768


def test_deleting_game_system_cascades_to_documents_and_chunks(db_session):
    system = GameSystem(name="Call of Cthulhu")
    db_session.add(system)
    db_session.commit()

    document = Document(game_system_id=system.id, filename="keeper.pdf", status="ready")
    db_session.add(document)
    db_session.commit()

    chunk = Chunk(
        document_id=document.id,
        game_system_id=system.id,
        content="Sanity loss occurs when...",
        embedding=[0.0] * 768,
    )
    db_session.add(chunk)
    db_session.commit()
    chunk_id = chunk.id

    db_session.delete(system)
    db_session.commit()

    assert db_session.get(Document, document.id) is None
    assert db_session.get(Chunk, chunk_id) is None
