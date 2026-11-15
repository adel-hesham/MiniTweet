import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["RABBITMQ_URL"] = ""

import jwt
import pytest
from fastapi.testclient import TestClient

import app as user_app


@pytest.fixture()
def client(monkeypatch):
    sent = []
    monkeypatch.setattr(user_app, "publish_event", lambda event_type, data: sent.append((event_type, data)))
    user_app.Base.metadata.drop_all(user_app.engine)
    with TestClient(user_app.app) as test_client:
        test_client.sent_events = sent
        yield test_client


def register(client, username="adel", password="secret123"):
    return client.post("/api/users/register", json={"username": username, "password": password})


def login(client, username="adel", password="secret123"):
    return client.post("/api/users/login", json={"username": username, "password": password})


def test_register_creates_user_and_publishes_event(client):
    response = register(client)
    assert response.status_code == 201
    assert response.json()["username"] == "adel"
    event_type, data = client.sent_events[0]
    assert event_type == "user.registered"
    assert data["username"] == "adel"


def test_username_is_case_insensitive(client):
    assert register(client, "Adel").json()["username"] == "adel"
    assert register(client, "ADEL").status_code == 409


def test_duplicate_username_is_rejected(client):
    register(client)
    assert register(client).status_code == 409


def test_short_password_is_rejected(client):
    assert register(client, password="123").status_code == 422


def test_login_returns_valid_token(client):
    user_id = register(client).json()["id"]
    response = login(client)
    assert response.status_code == 200
    claims = jwt.decode(response.json()["access_token"], "test-secret", algorithms=["HS256"])
    assert claims["sub"] == str(user_id)
    assert claims["username"] == "adel"


def test_login_with_wrong_password_fails(client):
    register(client)
    assert login(client, password="wrong-password").status_code == 401


def test_me_requires_a_token(client):
    assert client.get("/api/users/me").status_code == 401


def test_me_rejects_a_token_without_a_numeric_subject(client):
    token = jwt.encode({"username": "adel"}, "test-secret", algorithm="HS256")
    response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_returns_the_logged_in_user(client):
    register(client)
    token = login(client).json()["access_token"]
    response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "adel"


def test_get_user_by_id_is_public_and_minimal(client):
    user_id = register(client).json()["id"]
    response = client.get(f"/api/users/{user_id}")
    assert response.status_code == 200
    assert set(response.json()) == {"id", "username"}
    assert client.get("/api/users/9999").status_code == 404


def test_health_and_ready(client):
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"
