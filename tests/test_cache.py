"""Tests for the Redis caching layer on GET /admin/users.

Uses real Redis (same guard as test_realtime.py) and in-memory SQLite via
dependency override; lifespan is not run (no listener needed here).
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import realtime.cache as cache_module
from api.main import USERS_CACHE_KEY, app
from api.models import Base, User
from data.db import get_session
from realtime.redis_client import get_redis

try:
    get_redis().ping()
except Exception:
    pytest.skip(
        "Redis not reachable — start it with `docker compose up -d redis`",
        allow_module_level=True,
    )

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
    get_redis().delete(USERS_CACHE_KEY)
    yield TestClient(app)
    get_redis().delete(USERS_CACHE_KEY)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _admin_headers(client):
    client.post(
        "/auth/register", json={"email": "admin@example.com", "password": "pass1234"}
    )
    resp = client.post(
        "/auth/login", data={"username": "admin@example.com", "password": "pass1234"}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_second_call_is_served_from_cache_not_db(client):
    headers = _admin_headers(client)
    client.post(
        "/auth/register", json={"email": "viewer@example.com", "password": "pass1234"}
    )
    first = client.get("/admin/users", headers=headers)
    assert first.status_code == 200
    assert get_redis().exists(USERS_CACHE_KEY)

    # Mutate the DB behind the API's back; a cached response won't see it
    session = TestingSession()
    user = session.scalar(select(User).where(User.email == "viewer@example.com"))
    user.role = "admin"
    session.commit()
    session.close()

    second = client.get("/admin/users", headers=headers)
    assert second.status_code == 200
    assert second.json() == first.json()  # stale by design => came from cache


def test_role_change_invalidates_cache_immediately(client):
    headers = _admin_headers(client)
    client.post(
        "/auth/register", json={"email": "viewer@example.com", "password": "pass1234"}
    )
    users = client.get("/admin/users", headers=headers).json()  # populates cache
    viewer = next(u for u in users if u["email"] == "viewer@example.com")
    assert viewer["role"] == "viewer"

    resp = client.patch(
        f"/admin/users/{viewer['id']}/role", json={"role": "admin"}, headers=headers
    )
    assert resp.status_code == 200
    assert not get_redis().exists(USERS_CACHE_KEY)  # invalidated, not stale

    users = client.get("/admin/users", headers=headers).json()
    assert next(u for u in users if u["id"] == viewer["id"])["role"] == "admin"


def test_endpoint_survives_redis_being_unreachable(client, monkeypatch):
    headers = _admin_headers(client)

    def broken_redis():
        raise ConnectionError("redis down")

    monkeypatch.setattr(cache_module, "get_redis", broken_redis)
    resp = client.get("/admin/users", headers=headers)
    assert resp.status_code == 200  # feature works, just uncached
    assert resp.json()[0]["email"] == "admin@example.com"

    # Role changes (which invalidate the cache) also survive Redis being down
    resp = client.post(
        "/auth/register", json={"email": "viewer@example.com", "password": "pass1234"}
    )
    users = client.get("/admin/users", headers=headers).json()
    viewer = next(u for u in users if u["email"] == "viewer@example.com")
    resp = client.patch(
        f"/admin/users/{viewer['id']}/role", json={"role": "admin"}, headers=headers
    )
    assert resp.status_code == 200
