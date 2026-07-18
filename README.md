# 📡 realtime-analytics-platform — Multi-User Live Analytics

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?style=flat-square&logo=fastapi&logoColor=white)
![Dash](https://img.shields.io/badge/Plotly_Dash-Frontend-3F4F75?style=flat-square&logo=plotly&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Pub%2FSub_%2B_Cache-DC382D?style=flat-square&logo=redis&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-22_passing-brightgreen?style=flat-square)

---

## ❓ Problem

A dashboard that only one person can look at, with data that only updates on refresh, doesn't hold up for a team. Ops teams, business stakeholders, and multiple viewers watching the same metrics need everyone to see the same live picture at once — and not everyone should have the same level of access to change things.

---

## 💡 Solution

A multi-user analytics platform where authenticated users see live-updating charts in real time, with server-enforced role-based permissions:

- **JWT authentication** with two roles — admin (full access) and viewer (read-only)
- **Real-time updates** pushed to every connected browser tab via WebSocket, fanned out through Redis pub/sub — no polling, no manual refresh
- **Server-side enforced permissions** — a viewer hitting an admin-only endpoint gets a 403 regardless of what the UI shows
- **Redis-cached admin queries** for performance, invalidated automatically the instant data changes

---

## ✨ Features

- 🔐 **JWT Auth** — register/login, tokens carry the user's role
- 👥 **Role-Based Access Control** — admin vs viewer, enforced server-side on every protected route
- 🥇 **Zero-Config Admin Bootstrap** — the first registered user automatically becomes admin; a guard prevents demoting the last remaining admin
- ⚡ **Live WebSocket Updates** — charts update in every open browser tab simultaneously, the instant new data is published
- 📢 **Redis Pub/Sub Broadcasting** — decouples "who publishes an event" from "who's watching," so any process can publish and every connected client gets it
- 📊 **Live Dashboard** — order-count-by-platform bar chart and a running cumulative revenue line, both updating without a page reload
- 🛠️ **Admin Panel** — list users, change roles, directly from the UI (backed by the same server-enforced permissions)
- 🚀 **Redis Response Caching** — frequently-hit queries cached with a short TTL, invalidated immediately on writes, and degrades gracefully if Redis is ever unreachable
- 🐳 **One-Command Docker Deploy** — `docker compose up --build` and the whole stack (API, dashboard, Postgres, Redis) is live

---

## 🛠️ Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| API / Auth / WebSocket | FastAPI | JWT auth, RBAC-protected REST endpoints, WebSocket server |
| Frontend | Plotly Dash + dash-extensions | Live dashboard UI, browser-side WebSocket client |
| Database | PostgreSQL | User accounts and roles |
| Real-time | Redis Pub/Sub | Event broadcasting to all connected WebSocket clients |
| Caching | Redis | Short-TTL response cache with write-invalidation |
| Auth | python-jose, passlib (bcrypt) | JWT signing/verification, password hashing |
| Deployment | Docker Compose | App + Postgres + Redis, healthcheck-gated startup |
| Testing | pytest | 22 tests — auth, RBAC, real-time pipeline, cache, chart logic |

---

## 📡 Architecture

```
Client (browser)
   │
   ├─ HTTP ──────────► FastAPI (auth, REST API, /admin/*)
   │                        │
   │                        ├─ PostgreSQL (users, roles)
   │                        └─ Redis (cache: admin queries)
   │
   └─ WebSocket ──────► FastAPI /ws
                             │
                        Redis Pub/Sub (channel: analytics:updates)
                             │
                    Any publisher (e.g. POST /simulate/new-order)
```

Anything that calls `publish_event()` pushes to Redis; a background listener
fans that out to every connected WebSocket client — so charts update live
in every open tab, simultaneously.

---

## ⚡ Quick Start

```bash
git clone https://github.com/rizalcodes/realtime-analytics-platform.git
cd realtime-analytics-platform

cp .env.example .env   # set JWT_SECRET_KEY and DB_PASSWORD
docker compose up --build
```

- **Dashboard:** http://localhost:8050
- **API docs (Swagger):** http://localhost:8000/docs

**Admin bootstrap:** the *first* user you register automatically becomes admin. Everyone after that is a viewer until promoted.

### First run

1. Register via Swagger (`POST /auth/register`) — this account is your admin.
2. Open the dashboard, log in top-right, watch the connection status go green.
3. Click **Simulate New Order** — charts update instantly, in every open tab.
4. Visit **Admin** to manage users and roles.

### Tests

```bash
pip install -r requirements.txt
docker compose up -d redis
pytest
```

---

## 📁 Project Structure

```
realtime-analytics-platform/
├── app.py                  # Dash entry point + session login
├── api/
│   ├── main.py               # FastAPI: auth, admin, WebSocket, simulate
│   ├── auth.py                 # JWT + password hashing primitives
│   ├── models.py                 # User model (email, role)
│   └── deps.py                     # get_current_user, require_role/require_admin
├── realtime/
│   ├── broadcaster.py                # Redis pub/sub -> WebSocket fan-out
│   ├── redis_client.py                 # Shared Redis connection
│   └── cache.py                          # Cache get/set/delete helpers
├── pages/
│   ├── dashboard.py                        # Live charts + simulate button
│   └── admin.py                              # User management UI
├── components/order_stats.py                   # Pure chart-data transforms
├── tests/                                         # 22 tests
├── docker-compose.yml                               # app + db + redis
└── Dockerfile
```

---

## 👤 Author

**Rizal**

[![Portfolio](https://img.shields.io/badge/Portfolio-rizalcodes.github.io-0A66C2?style=flat-square)](https://rizalcodes.github.io)
[![GitHub](https://img.shields.io/badge/GitHub-rizalcodes-181717?style=flat-square&logo=github)](https://github.com/rizalcodes)
[![Twitter/X](https://img.shields.io/badge/X-@rizalcodes_-000000?style=flat-square&logo=x)](https://x.com/rizalcodes_)

---

*Built with FastAPI, Redis pub/sub, and the conviction that a dashboard someone has to refresh isn't really live.*
