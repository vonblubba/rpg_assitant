from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models import GameSystem


def make_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_systems_page_lists_created_systems(db_session):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    response = client.get("/")

    assert response.status_code == 200
    # Jinja2's default autoescape (on for .html templates) renders "&" as
    # "&amp;" -- this is correct, secure behavior, so we assert on the
    # escaped form rather than disabling autoescape to match a raw string.
    assert "D&amp;D 5e" in response.text
    assert 'id="create-system-form"' in response.text


def test_system_detail_page_renders_upload_form(db_session):
    system = GameSystem(name="Call of Cthulhu")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    response = client.get(f"/systems/{system.id}")

    assert response.status_code == 200
    assert "Call of Cthulhu" in response.text
    assert 'id="upload-form"' in response.text


def test_system_detail_page_404s_for_missing_system(db_session):
    client = make_client(db_session)
    response = client.get("/systems/999")
    assert response.status_code == 404


def test_chat_page_renders_chat_form(db_session):
    system = GameSystem(name="D&D 5e")
    db_session.add(system)
    db_session.commit()

    client = make_client(db_session)
    response = client.get(f"/systems/{system.id}/chat")

    assert response.status_code == 200
    assert 'id="chat-form"' in response.text
