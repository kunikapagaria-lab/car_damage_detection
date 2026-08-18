"""JWT-based authentication and role-based access control.

Provides login / refresh token endpoints, a User ORM model, a new
Alembic migration (002_add_users), and FastAPI dependency helpers
get_current_user() / require_role().
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, Enum, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from core.config import settings
from core.deps import get_db
from db.database import Base

logger = structlog.get_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ── User role enum ────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    operator = "operator"
    admin = "admin"


# ── User ORM model ────────────────────────────────────────────────────────────

class User(Base):
    """Application user — added by migration 002_add_users."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.operator
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── Token creation ────────────────────────────────────────────────────────────

def _create_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(username: str, role: str) -> str:
    return _create_token(
        {"sub": username, "role": role, "type": "access"},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(username: str) -> str:
    return _create_token(
        {"sub": username, "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_user(username: str, db: AsyncSession) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def _authenticate(username: str, password: str, db: AsyncSession) -> User | None:
    user = await _get_user(username, db)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user


# ── Pydantic response models ──────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ── FastAPI dependencies ──────────────────────────────────────────────────────

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: Annotated[str | None, Depends(_oauth2)],
    db: AsyncSession = Depends(get_db),
) -> User:
    if token is None:
        raise _credentials_exc
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise _credentials_exc
    username: str | None = payload.get("sub")
    if not username:
        raise _credentials_exc
    user = await _get_user(username, db)
    if user is None or not user.is_active:
        raise _credentials_exc
    return user


def require_role(minimum_role: str):
    """Return a dependency that enforces a minimum role level.

    Role hierarchy: admin > operator.
    """
    role_order = {UserRole.operator: 0, UserRole.admin: 1}
    required_level = role_order.get(UserRole(minimum_role), 0)

    async def _check(user: User = Depends(get_current_user)) -> User:
        user_level = role_order.get(user.role, 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{minimum_role}' or higher required",
            )
        return user

    return _check


# ── Auth endpoints ────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await _authenticate(form.username, form.password, db)
    if user is None:
        logger.warning("login_failed", username=form.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    logger.info("login_success", username=user.username, role=user.role.value)
    return TokenResponse(
        access_token=create_access_token(user.username, user.role.value),
        refresh_token=create_refresh_token(user.username),
        role=user.role.value,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    username: str | None = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await _get_user(username, db)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return TokenResponse(
        access_token=create_access_token(user.username, user.role.value),
        refresh_token=create_refresh_token(user.username),
        role=user.role.value,
    )


# ── Utility: create first admin user (run once at startup if no users exist) ──

async def ensure_default_admin(db: AsyncSession) -> None:
    """Create the default admin user if the users table is empty."""
    import os

    result = await db.execute(select(func.count()).select_from(User))
    if result.scalar_one() > 0:
        return

    default_user = os.environ.get("DEFAULT_ADMIN_USER", "admin")
    default_pass = os.environ.get("DEFAULT_ADMIN_PASSWORD", "changeme123!")

    admin = User(
        username=default_user,
        hashed_password=hash_password(default_pass),
        role=UserRole.admin,
    )
    db.add(admin)
    await db.commit()
    logger.info(
        "default_admin_created",
        username=default_user,
        warning="Change the default password immediately",
    )
