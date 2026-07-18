"""FastAPI app: auth routes, admin routes, and the real-time WebSocket endpoint.

Real-time flow (M3): publish_event() -> Redis pub/sub -> redis_listener
(one background task, started in the lifespan) -> all connected /ws clients.
See realtime/broadcaster.py for the channel and message shape.
"""

import asyncio
import random
from contextlib import asynccontextmanager, suppress
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.auth import create_access_token, hash_password, verify_password
from api.deps import get_current_user, require_admin
from api.models import VALID_ROLES, Base, User
from data.db import engine, get_session
from realtime.broadcaster import manager, publish_event, redis_listener
from realtime.cache import cache_delete, cache_get, cache_set


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # One Redis subscriber task for the app's lifetime — not per-connection
    ready = asyncio.Event()
    listener_task = asyncio.create_task(redis_listener(ready))
    await asyncio.wait_for(ready.wait(), timeout=10)
    yield
    listener_task.cancel()
    with suppress(asyncio.CancelledError):
        await listener_task


app = FastAPI(title="realtime-analytics-platform API", lifespan=lifespan)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    email: str
    role: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    created_at: datetime


class RoleUpdate(BaseModel):
    role: str


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_session)):
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    # Admin bootstrap: the very first registered user becomes admin; everyone
    # after that is a viewer until promoted via PATCH /admin/users/{id}/role.
    is_first_user = db.scalar(select(func.count()).select_from(User)) == 0
    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role="admin" if is_first_user else "viewer",
    )
    db.add(user)
    db.commit()
    return {"message": "User registered successfully", "role": user.role}


@app.post("/auth/login", response_model=TokenResponse)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)
):
    # OAuth2 form's "username" field carries the email
    user = db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user.email, "role": user.role})
    return TokenResponse(access_token=token)


@app.get("/auth/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    return MeResponse(email=user.email, role=user.role)


USERS_CACHE_KEY = "cache:admin:users"
USERS_CACHE_TTL = 15  # seconds — user list changes rarely; PATCH invalidates anyway


@app.get("/admin/users", response_model=list[UserOut])
def list_users(
    admin: User = Depends(require_admin), db: Session = Depends(get_session)
):
    cached = cache_get(USERS_CACHE_KEY)
    if cached is not None:
        return cached
    users = db.scalars(select(User).order_by(User.id)).all()
    data = [UserOut.model_validate(u).model_dump(mode="json") for u in users]
    cache_set(USERS_CACHE_KEY, data, USERS_CACHE_TTL)
    return data


@app.patch("/admin/users/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: int,
    body: RoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_session),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role {body.role!r}; must be one of {sorted(VALID_ROLES)}",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if user.role == "admin" and body.role != "admin":
        admin_count = db.scalar(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last remaining admin",
            )
    user.role = body.role
    db.commit()
    cache_delete(USERS_CACHE_KEY)  # role change must be visible immediately
    return user


SIMULATED_PRODUCTS = [
    ("Wireless Earbuds Pro", 89.99),
    ("Mechanical Keyboard TKL", 129.00),
    ("USB-C Hub 7-in-1", 45.50),
    ("4K Webcam", 149.99),
    ("Ergonomic Mouse", 59.90),
    ("Portable SSD 1TB", 119.00),
]
SIMULATED_PLATFORMS = ["shopee", "lazada", "tokopedia"]


@app.post("/simulate/new-order", status_code=status.HTTP_202_ACCEPTED)
def simulate_new_order(admin: User = Depends(require_admin)):
    """Publish a fake new_order event to Redis; every connected /ws client sees it."""
    product, base_price = random.choice(SIMULATED_PRODUCTS)
    payload = {
        "product": product,
        "price": round(base_price * random.uniform(0.9, 1.1), 2),
        "platform": random.choice(SIMULATED_PLATFORMS),
        "quantity": random.randint(1, 3),
    }
    message = publish_event("new_order", payload)
    return {"message": "Event published", "event": message}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Register with the broadcaster; the client receives every published event."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; inbound client messages are ignored
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
