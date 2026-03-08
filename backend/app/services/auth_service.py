"""Authentication service: password hashing, JWT tokens, user CRUD."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# Configuration
SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "draft-dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "1440"))  # 24h


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, email: str) -> str:
    """Create a JWT access token for a user."""
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT token. Returns payload or None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") is None:
            return None
        return payload
    except JWTError:
        return None


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Look up a user by email."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    """Look up a user by ID."""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession, email: str, password: str, display_name: str
) -> User:
    """Create a new user account. Caller must handle duplicate email checks."""
    user = User(
        id=str(uuid.uuid4()),
        email=email.lower().strip(),
        display_name=display_name.strip(),
        hashed_password=hash_password(password),
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    """Authenticate a user by email and password. Returns User or None."""
    user = await get_user_by_email(db, email.lower().strip())
    if user is None:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
