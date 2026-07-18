# realtime-analytics-platform

Multi-user real-time analytics platform: JWT auth with role-based access
(admin/viewer), live-updating Plotly Dash dashboards over WebSocket, backed by
FastAPI, PostgreSQL, and Redis.

## Architecture

| Piece | Role |
|---|---|
| **FastAPI** (`api/`) | Auth (JWT register/login), RBAC-protected REST API, WebSocket endpoint at `/ws` |
| **Dash** (`app.py`, `pages/`) | Frontend UI: live dashboard + admin panel, WebSocket client via dash-extensions |
| **PostgreSQL** | Persistent data: user accounts and roles |
| **Redis** | Pub/sub fan-out of real-time events to every connected WebSocket client, plus a response cache for frequently-hit queries |

Event flow: anything calls `publish_event()` (or `POST /simulate/new-order`)
→ Redis channel `analytics:updates` → one subscriber task in the API → every
connected `/ws` client → charts update in place in every open browser tab.

The `app` container runs both the FastAPI API (port 8000) and the Dash app
(port 8050) — a deliberate M1 simplification, splittable later.

## Getting started

```bash
cp .env.example .env   # then edit values (at minimum JWT_SECRET_KEY and DB_PASSWORD)
docker compose up --build
```

That's the whole setup — Postgres and Redis come up with healthchecks, the
app waits for both, tables are created on startup.

- **Dashboard**: http://localhost:8050
- **API docs (Swagger)**: http://localhost:8000/docs

**Admin bootstrap:** the *first* user registered on a fresh database
automatically becomes **admin**; everyone after that is a viewer until an
admin promotes them (`PATCH /admin/users/{id}/role`, or the Admin page in the
dashboard). The API refuses to demote the last remaining admin.

First run walkthrough:

1. Register via Swagger (`POST /auth/register`) or curl — this account is the admin.
2. Open http://localhost:8050, log in top-right, and watch the "Connected"
   indicator go green.
3. Click **Simulate New Order** — charts update instantly in every open tab,
   no reload.
4. Visit the **Admin** page to list users and change roles (server-side
   enforced: viewers get 403 from the API no matter what the UI shows).

## Caching

`GET /admin/users` responses are cached in Redis for 15 seconds and the key
(`cache:admin:users`) is deleted whenever a role change succeeds, so changes
show immediately. A Redis outage degrades to "no caching" — the endpoint
keeps working. Helpers live in `realtime/cache.py`.

## Tests

```bash
pip install -r requirements.txt
docker compose up -d redis   # realtime + cache tests use real Redis on localhost:6379
pytest
```

Covers auth primitives, RBAC (403s, role changes, last-admin guard), the
publish → Redis → WebSocket pipeline, chart-data transforms, and the caching
layer (hit, invalidation, graceful degradation).

## Local development (without Docker)

Requires PostgreSQL and Redis running to match your `.env`:

```bash
uvicorn api.main:app --reload   # API on :8000
python app.py                   # Dash on :8050 (separate terminal)
```

`API_URL` / `WS_URL` env vars override where the Dash app reaches the API
(defaults: `http://localhost:8000` and `ws://localhost:8000/ws`).
