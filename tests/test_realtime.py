"""Real-time pipeline tests: publish -> Redis -> listener -> WebSocket clients.

Uses TestClient as a context manager so the app lifespan runs (Redis
subscriber task). Requires a real Redis on REDIS_HOST:REDIS_PORT — the
docker-compose redis service exposes 6379 to the host for this. The DB is
swapped for in-memory SQLite (lifespan create_all + get_session override).
"""

import json
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import api.main as main_module
from api.main import app
from api.models import Base
from data.db import get_session
from realtime.broadcaster import publish_event
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
    real_engine = main_module.engine
    main_module.engine = test_engine  # lifespan's create_all targets SQLite
    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as test_client:  # runs lifespan: starts redis_listener
        yield test_client
    app.dependency_overrides.clear()
    main_module.engine = real_engine
    Base.metadata.drop_all(bind=test_engine)


def test_ws_client_receives_published_event(client):
    with client.websocket_connect("/ws") as ws:
        sent = publish_event("test_event", {"n": 1})
        received = json.loads(ws.receive_text())
    assert received == sent
    assert received["event"] == "test_event"
    assert received["payload"] == {"n": 1}
    assert "timestamp" in received


def test_multiple_clients_all_receive_same_broadcast(client):
    with client.websocket_connect("/ws") as ws1, client.websocket_connect("/ws") as ws2:
        sent = publish_event("test_event", {"n": 2})
        assert json.loads(ws1.receive_text()) == sent
        assert json.loads(ws2.receive_text()) == sent


def test_disconnected_client_does_not_break_broadcast(client):
    with client.websocket_connect("/ws") as ws_stays:
        with client.websocket_connect("/ws"):
            pass  # second client connects and immediately disconnects
        sent = publish_event("test_event", {"n": 3})
        # The still-connected client gets the message; nothing crashed
        assert json.loads(ws_stays.receive_text()) == sent


def _register_and_login(client, email, password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    resp = client.post("/auth/login", data={"username": email, "password": password})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_simulate_new_order_requires_admin(client):
    admin_headers = _register_and_login(client, "admin@example.com")  # first = admin
    viewer_headers = _register_and_login(client, "viewer@example.com")

    resp = client.post("/simulate/new-order", headers=viewer_headers)
    assert resp.status_code == 403

    with client.websocket_connect("/ws") as ws:
        resp = client.post("/simulate/new-order", headers=admin_headers)
        assert resp.status_code == 202
        event = resp.json()["event"]
        assert event["event"] == "new_order"
        assert {"product", "price", "platform", "quantity"} <= set(event["payload"])
        # The published event reaches WebSocket clients end-to-end
        assert json.loads(ws.receive_text()) == event
