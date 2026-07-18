# realtime-analytics-platform — Project Context

## Overview
Multi-user real-time analytics platform. Users authenticate via JWT and are
assigned a role (admin or viewer) that gates access to routes and API
endpoints. Dashboard charts update live via WebSocket, backed by Redis
pub/sub so all connected clients see new data simultaneously without a page
reload. Expert-level project — the most architecturally complex in the
roadmap (auth + real-time + caching + multi-service Docker stack).

## Tech Stack
- Python 3.12+
- FastAPI (auth endpoints, WebSocket server, REST API)
- Plotly Dash (frontend dashboard, WebSocket client for live updates)
- PostgreSQL (user accounts, business data)
- SQLAlchemy (DB connection layer)
- Redis (caching + pub/sub for broadcasting real-time updates)
- python-jose (JWT creation/verification)
- passlib[bcrypt] (password hashing)
- Docker + Docker Compose (app, db, redis services)
- pytest (testing, especially auth/RBAC logic and pure data functions)

## Commands
- Run via Docker: `docker compose up --build`
- Run locally (dev): requires Postgres + Redis running, then `python app.py`
  (or separate FastAPI/Dash processes if split — decide at implementation time)
- Test: `pytest`
- Lint: `ruff check .`

## Project Structure
```
realtime-analytics-platform/
├── app.py                    # Dash app entry point (or split from API — TBD at M1)
├── api/
│   ├── main.py                 # FastAPI app: auth routes, WebSocket endpoint
│   ├── auth.py                   # JWT creation/verification, password hashing
│   ├── models.py                   # SQLAlchemy models: User, roles
│   └── deps.py                       # FastAPI dependencies (get_current_user, require_role)
├── pages/                              # Dash pages (protected by role where relevant)
├── realtime/
│   ├── redis_client.py                   # Redis connection, pub/sub helpers
│   └── broadcaster.py                      # Push updates to connected WebSocket clients
├── data/
│   ├── db.py                                 # PostgreSQL connection (SQLAlchemy)
│   └── queries.py                              # Reusable data-loading queries
├── components/                                   # Shared Dash components
├── tests/
├── docker-compose.yml                                # app + db (postgres) + redis
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## Conventions
- Auth logic (JWT, password hashing, role checks) lives entirely in api/ —
  never duplicated in page files
- Role checks happen server-side (FastAPI dependency / route guard), never
  trust client-side role display alone — a viewer hitting an admin endpoint
  directly must get a 403, not just a hidden UI element
- All DB queries go through data/queries.py, same convention as Project 3
- Redis pub/sub channel(s) and message shape documented in
  realtime/broadcaster.py — one clear source of truth for what gets broadcast
- Never hardcode credentials (DB, Redis, JWT secret) — everything from .env
- WebSocket connections must handle disconnects gracefully — a dropped
  client should not crash the broadcaster or affect other connected clients
- Admin bootstrap: the first user registered on a fresh database
  automatically becomes admin; all later registrations are viewers and can
  only be promoted by an existing admin (PATCH /admin/users/{id}/role).
  The API refuses to demote the last remaining admin (lockout guard).

## Milestones
- **M1** — FastAPI + Dash skeleton, Docker Compose (app + db + redis), user
  registration/login with JWT issued on success
- **M2** — Role-based access control: role field on User, protected routes
  (viewer vs admin), 403 on unauthorized access enforced server-side
- **M3** — WebSocket connection + Redis pub/sub wiring: a simulated "new
  data" event publishes to Redis, broadcasts to all connected WebSocket
  clients
- **M4** — Live-updating dashboard chart(s) consuming the WebSocket stream;
  admin panel for user/role management
- **M5** — Redis caching layer for frequently-hit queries, full Docker
  Compose verification (fresh `docker compose up` works end-to-end,
  multi-tab real-time demo confirmed)

## Current Milestone
All 5 milestones complete. Final feature set:
- JWT auth (register/login, protected routes via get_current_user)
- RBAC: admin/viewer roles enforced server-side, first-registered-user
  admin bootstrap, last-admin demotion guard, admin user-management API
- Real-time: Redis pub/sub ("analytics:updates") broadcast to all
  connected WebSocket clients; POST /simulate/new-order demo publisher
- Live Dash dashboard (dash-extensions WebSocket) + admin panel UI
- Redis caching layer: GET /admin/users cached (15s TTL), invalidated on
  role change, degrades gracefully if Redis is unreachable

## Data Source
Can reuse the e-commerce dataset from Project 3 (ecommerce-bi-dashboard),
simulating periodic "new order" events to demonstrate real-time updates
since the underlying scraped data is static, not a live feed.
