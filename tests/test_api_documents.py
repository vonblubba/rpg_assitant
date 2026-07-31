import io
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import GameSystem


def make_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_upload_document_creates_pending_row_and_schedules_ingestion(db_session, monkeypatch):
    fake_ingest = AsyncMock()
    monkeypatch.setattr("app.routes.documents.ingest_document", fake_ingest)

    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    response = client.post(
        f"/systems/{system.id}/documents",
        files={"file": ("phb.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "phb.pdf"
    assert body["status"] == "pending"
    fake_ingest.assert_called_once()
    assert fake_ingest.call_args.args[0] == body["id"]


def test_upload_document_for_missing_system_returns_404(db_session):
    client = make_client(db_session)
    response = client.post(
        "/systems/999/documents",
        files={"file": ("phb.pdf", io.BytesIO(b"content"), "application/pdf")},
    )
    assert response.status_code == 404


def test_list_and_delete_documents(db_session, monkeypatch):
    monkeypatch.setattr("app.routes.documents.ingest_document", AsyncMock())
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    upload_response = client.post(
        f"/systems/{system.id}/documents",
        files={"file": ("phb.pdf", io.BytesIO(b"content"), "application/pdf")},
    )
    document_id = upload_response.json()["id"]

    list_response = client.get(f"/systems/{system.id}/documents")
    assert len(list_response.json()) == 1

    delete_response = client.delete(f"/systems/{system.id}/documents/{document_id}")
    assert delete_response.status_code == 204

    list_response = client.get(f"/systems/{system.id}/documents")
    assert list_response.json() == []
