"""End-to-end RBAC tests via TestClient against an in-memory SQLite database."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from api.models import Base
from data.db import get_session

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def _override_get_session():
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_session] = _override_get_session
    # Not used as a context manager on purpose: the app lifespan would run
    # create_all against the real Postgres engine.
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def register(client, email, password="pass1234"):
    return client.post(
        "/auth/register", json={"email": email, "password": password}
    )


def token_for(client, email, password="pass1234"):
    resp = client.post(
        "/auth/login", data={"username": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_first_registered_user_is_admin(client):
    resp = register(client, "first@example.com")
    assert resp.status_code == 201
    assert resp.json()["role"] == "admin"

    resp = register(client, "second@example.com")
    assert resp.json()["role"] == "viewer"


def test_viewer_gets_403_on_admin_users(client):
    register(client, "admin@example.com")
    register(client, "viewer@example.com")
    resp = client.get(
        "/admin/users", headers=auth(token_for(client, "viewer@example.com"))
    )
    assert resp.status_code == 403


def test_admin_lists_users(client):
    register(client, "admin@example.com")
    register(client, "viewer@example.com")
    resp = client.get(
        "/admin/users", headers=auth(token_for(client, "admin@example.com"))
    )
    assert resp.status_code == 200
    users = resp.json()
    assert [(u["email"], u["role"]) for u in users] == [
        ("admin@example.com", "admin"),
        ("viewer@example.com", "viewer"),
    ]
    assert all("id" in u and "created_at" in u for u in users)


def test_admin_can_change_another_users_role(client):
    register(client, "admin@example.com")
    register(client, "viewer@example.com")
    headers = auth(token_for(client, "admin@example.com"))

    users = client.get("/admin/users", headers=headers).json()
    viewer_id = next(u["id"] for u in users if u["email"] == "viewer@example.com")

    resp = client.patch(
        f"/admin/users/{viewer_id}/role", json={"role": "admin"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    # The change is effective server-side immediately (role read from DB)
    me = client.get(
        "/auth/me", headers=auth(token_for(client, "viewer@example.com"))
    )
    assert me.json()["role"] == "admin"


def test_invalid_role_returns_400(client):
    register(client, "admin@example.com")
    register(client, "viewer@example.com")
    headers = auth(token_for(client, "admin@example.com"))

    users = client.get("/admin/users", headers=headers).json()
    viewer_id = next(u["id"] for u in users if u["email"] == "viewer@example.com")

    resp = client.patch(
        f"/admin/users/{viewer_id}/role", json={"role": "superuser"}, headers=headers
    )
    assert resp.status_code == 400
    assert "Invalid role" in resp.json()["detail"]


def test_cannot_demote_last_admin(client):
    register(client, "admin@example.com")
    register(client, "viewer@example.com")
    headers = auth(token_for(client, "admin@example.com"))

    users = client.get("/admin/users", headers=headers).json()
    admin_id = next(u["id"] for u in users if u["email"] == "admin@example.com")

    resp = client.patch(
        f"/admin/users/{admin_id}/role", json={"role": "viewer"}, headers=headers
    )
    assert resp.status_code == 400
    assert "last remaining admin" in resp.json()["detail"]

    # Once a second admin exists, the demotion is allowed
    viewer_id = next(u["id"] for u in users if u["email"] == "viewer@example.com")
    client.patch(
        f"/admin/users/{viewer_id}/role", json={"role": "admin"}, headers=headers
    )
    resp = client.patch(
        f"/admin/users/{admin_id}/role", json={"role": "viewer"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"
