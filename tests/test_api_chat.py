import json

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import Chunk, Document, GameSystem
from app.ollama_client import OllamaError


def make_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_chat_streams_answer_grounded_in_retrieved_chunks(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()
    document = Document(game_system_id=system.id, filename="phb.pdf", status="ready")
    db_session.add(document)
    db_session.commit()
    db_session.add(
        Chunk(
            document_id=document.id,
            game_system_id=system.id,
            content="A fighter is a master of martial combat.",
            embedding=[0.1] * 768,
        )
    )
    db_session.commit()

    async def fake_retrieve_chunks(db, game_system_id, query, k=8):
        return db.query(Chunk).filter(Chunk.game_system_id == game_system_id).all()

    async def fake_chat_stream(messages):
        assert "master of martial combat" in messages[0]["content"]
        for piece in ["A ", "fighter."]:
            yield piece

    monkeypatch.setattr("app.routes.chat.retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr("app.routes.chat.chat_stream", fake_chat_stream)

    client = make_client(db_session)
    response = client.post(f"/systems/{system.id}/chat", json={"question": "What is a fighter?"})

    assert response.status_code == 200
    events = [line for line in response.text.splitlines() if line.startswith("data: ")]
    payloads = [json.loads(line.removeprefix("data: ")) for line in events]
    assert [p["content"] for p in payloads if "content" in p] == ["A ", "fighter."]


def test_chat_uses_history_for_retrieval_query_and_llm_context(db_session, monkeypatch):
    system = GameSystem(name="Blade Runner")
    db_session.add(system)
    db_session.commit()
    document = Document(game_system_id=system.id, filename="core.pdf", status="ready")
    db_session.add(document)
    db_session.commit()
    db_session.add(
        Chunk(
            document_id=document.id,
            game_system_id=system.id,
            content="Choose one of the seven core archetypes described on pages 039-051.",
            embedding=[0.1] * 768,
        )
    )
    db_session.commit()

    captured_query = {}

    async def fake_retrieve_chunks(db, game_system_id, query, k=8):
        captured_query["query"] = query
        return db.query(Chunk).filter(Chunk.game_system_id == game_system_id).all()

    async def fake_chat_stream(messages):
        assert messages[1] == {"role": "user", "content": "choose freely"}
        assert messages[2] == {"role": "assistant", "content": "Pick freely or roll a D6?"}
        assert messages[3] == {"role": "user", "content": "option 1"}
        yield "Sure."

    monkeypatch.setattr("app.routes.chat.retrieve_chunks", fake_retrieve_chunks)
    monkeypatch.setattr("app.routes.chat.chat_stream", fake_chat_stream)

    client = make_client(db_session)
    response = client.post(
        f"/systems/{system.id}/chat",
        json={
            "question": "option 1",
            "history": [
                {"role": "user", "content": "choose freely"},
                {"role": "assistant", "content": "Pick freely or roll a D6?"},
            ],
        },
    )

    assert response.status_code == 200
    assert captured_query["query"] == "choose freely Pick freely or roll a D6? option 1"


def test_chat_with_no_retrieved_chunks_says_so_explicitly(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    async def fake_retrieve_chunks(db, game_system_id, query, k=8):
        return []

    monkeypatch.setattr("app.routes.chat.retrieve_chunks", fake_retrieve_chunks)

    client = make_client(db_session)
    response = client.post(f"/systems/{system.id}/chat", json={"question": "What is a fighter?"})

    assert response.status_code == 200
    assert "couldn't find anything" in response.text


def test_chat_streams_error_event_when_embedding_fails(db_session, monkeypatch):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    async def fake_retrieve_chunks(db, game_system_id, query, k=8):
        raise OllamaError("Ollama embeddings request failed: connection refused")

    monkeypatch.setattr("app.routes.chat.retrieve_chunks", fake_retrieve_chunks)

    client = make_client(db_session)
    response = client.post(f"/systems/{system.id}/chat", json={"question": "What is a fighter?"})

    assert response.status_code == 200
    events = [line for line in response.text.splitlines() if line.startswith("data: ")]
    payloads = [json.loads(line.removeprefix("data: ")) for line in events]
    assert any("error" in p and "Ollama embeddings request failed" in p["error"] for p in payloads)
    assert "event: done" in response.text


def test_chat_for_missing_system_returns_404(db_session):
    client = make_client(db_session)
    response = client.post("/systems/999/chat", json={"question": "anything"})
    assert response.status_code == 404
