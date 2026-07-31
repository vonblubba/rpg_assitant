from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app


def make_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_create_and_list_game_systems(db_session):
    client = make_client(db_session)

    response = client.post("/systems", json={"name": "D&D 5e"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "D&D 5e"
    assert "id" in body

    response = client.get("/systems")
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert names == ["D&D 5e"]


def test_delete_game_system(db_session):
    client = make_client(db_session)
    created = client.post("/systems", json={"name": "Call of Cthulhu"}).json()

    response = client.delete(f"/systems/{created['id']}")
    assert response.status_code == 204

    response = client.get("/systems")
    assert response.json() == []
