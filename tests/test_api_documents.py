import io
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import Document, GameSystem
from app.routes.documents import UPLOAD_DIR


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


def test_upload_document_with_slash_in_filename_is_sanitized(db_session, monkeypatch):
    fake_ingest = AsyncMock()
    monkeypatch.setattr("app.routes.documents.ingest_document", fake_ingest)

    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    response = client.post(
        f"/systems/{system.id}/documents",
        files={"file": ("a/b.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"

    # The file must be saved under the sanitized basename, not under a
    # non-existent nested directory derived from the raw filename.
    dest_path = UPLOAD_DIR / f"{body['id']}_b.pdf"
    try:
        assert dest_path.exists()

        # The row must not be stuck in "pending" forever with no file on disk;
        # ingestion should have been scheduled since the write succeeded.
        fake_ingest.assert_called_once()
        document = db_session.get(Document, body["id"])
        assert document.status == "pending"
    finally:
        dest_path.unlink(missing_ok=True)


def test_delete_document_removes_file_from_disk(db_session, monkeypatch):
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

    dest_path = UPLOAD_DIR / f"{document_id}_phb.pdf"
    assert dest_path.exists()

    delete_response = client.delete(f"/systems/{system.id}/documents/{document_id}")
    assert delete_response.status_code == 204

    assert not dest_path.exists()


def test_delete_document_without_saved_file_does_not_raise(db_session):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    document = Document(game_system_id=system.id, filename="never-written.pdf", status="failed")
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)

    client = make_client(db_session)
    delete_response = client.delete(f"/systems/{system.id}/documents/{document.id}")
    assert delete_response.status_code == 204
