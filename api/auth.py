"""Auth primitives: password hashing and JWT creation/verification.

No route logic here — routes live in api/main.py, dependencies in api/deps.py.
"""

import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _secret_key() -> str:
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is not set (see .env.example)")
    return secret


def _algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Return a signed JWT containing `data` plus an `exp` claim."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "30")))
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(to_encode, _secret_key(), algorithm=_algorithm())


def verify_token(token: str) -> dict:
    """Return the decoded payload. Raises JWTError if invalid, tampered, or expired."""
    return jwt.decode(token, _secret_key(), algorithms=[_algorithm()])


__all__ = [
    "JWTError",
    "create_access_token",
    "hash_password",
    "verify_password",
    "verify_token",
]
