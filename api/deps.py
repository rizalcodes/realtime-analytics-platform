"""FastAPI dependencies for authentication (and, from M2, role enforcement)."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import JWTError, verify_token
from api.models import User
from data.db import get_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_session),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_token(token)
    except JWTError:
        raise credentials_error
    email = payload.get("sub")
    if email is None:
        raise credentials_error
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise credentials_error
    return user


def require_role(role: str):
    """Route guard: current user must have `role`, else 403.

    Composes with get_current_user, so a missing/invalid token is still 401;
    403 means "authenticated but not allowed". Use as a dependency:
    `Depends(require_role("admin"))` or the `require_admin` alias below.
    """

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


require_admin = require_role("admin")
