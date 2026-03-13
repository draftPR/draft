"""Tests for multi-user authentication system."""

import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.base import Base

# Module-level engine (created once, reused across tests)
_test_engine = None
_test_session_maker = None


def _get_engine():
    global _test_engine, _test_session_maker
    if _test_engine is None:
        _test_engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        _test_session_maker = async_sessionmaker(
            _test_engine, class_=AsyncSession, expire_on_commit=False
        )
    return _test_engine, _test_session_maker


@pytest.fixture
async def auth_client(monkeypatch):
    """Create a test client with auth enabled and fresh in-memory DB."""
    import app.dependencies.auth as auth_mod

    monkeypatch.setattr(auth_mod, "AUTH_ENABLED", True)

    engine, session_maker = _get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from app.database import get_db
    from app.main import app

    async def override_get_db():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


# ---- Auth endpoint tests ----


@pytest.mark.asyncio
async def test_register_user(auth_client):
    """Test user registration."""
    resp = await auth_client.post(
        "/auth/register",
        json={
            "email": "alice@example.com",
            "password": "securepass123",
            "display_name": "Alice",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["token_type"] == "bearer"
    assert "access_token" in data
    assert data["user"]["email"] == "alice@example.com"
    assert data["user"]["display_name"] == "Alice"
    assert data["user"]["is_active"] is True


@pytest.mark.asyncio
async def test_register_duplicate_email(auth_client):
    """Duplicate email should be rejected."""
    payload = {
        "email": "bob@example.com",
        "password": "securepass123",
        "display_name": "Bob",
    }
    resp1 = await auth_client.post("/auth/register", json=payload)
    assert resp1.status_code == 201

    resp2 = await auth_client.post("/auth/register", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_register_short_password(auth_client):
    """Password must be at least 8 characters."""
    resp = await auth_client.post(
        "/auth/register",
        json={
            "email": "short@example.com",
            "password": "short",
            "display_name": "Short",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(auth_client):
    """Test successful login."""
    await auth_client.post(
        "/auth/register",
        json={
            "email": "carol@example.com",
            "password": "securepass123",
            "display_name": "Carol",
        },
    )

    resp = await auth_client.post(
        "/auth/login",
        json={
            "email": "carol@example.com",
            "password": "securepass123",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "carol@example.com"


@pytest.mark.asyncio
async def test_login_wrong_password(auth_client):
    """Wrong password should be rejected."""
    await auth_client.post(
        "/auth/register",
        json={
            "email": "dave@example.com",
            "password": "securepass123",
            "display_name": "Dave",
        },
    )

    resp = await auth_client.post(
        "/auth/login",
        json={
            "email": "dave@example.com",
            "password": "wrongpassword",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email(auth_client):
    """Login with non-existent email should fail."""
    resp = await auth_client.post(
        "/auth/login",
        json={
            "email": "nobody@example.com",
            "password": "securepass123",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(auth_client):
    """GET /auth/me with valid token returns user profile."""
    reg = await auth_client.post(
        "/auth/register",
        json={
            "email": "eve@example.com",
            "password": "securepass123",
            "display_name": "Eve",
        },
    )
    token = reg.json()["access_token"]

    resp = await auth_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "eve@example.com"


@pytest.mark.asyncio
async def test_get_me_no_token(auth_client):
    """GET /auth/me without token should return 401 when auth enabled."""
    resp = await auth_client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(auth_client):
    """GET /auth/me with invalid token should return 401."""
    resp = await auth_client.get(
        "/auth/me", headers={"Authorization": "Bearer invalid.token.here"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_board_owned_by_user(auth_client):
    """Boards created by a user should have owner_id set."""
    # Register and get token
    reg = await auth_client.post(
        "/auth/register",
        json={
            "email": "frank@example.com",
            "password": "securepass123",
            "display_name": "Frank",
        },
    )
    token = reg.json()["access_token"]
    user_id = reg.json()["user"]["id"]

    # Create a temp git repo
    with tempfile.TemporaryDirectory() as tmpdir:
        os.system(f"cd {tmpdir} && git init -q && git commit --allow-empty -m init -q")

        resp = await auth_client.post(
            "/boards",
            json={
                "name": "Frank's Board",
                "repo_root": tmpdir,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["owner_id"] == user_id


@pytest.mark.asyncio
async def test_boards_scoped_by_user(auth_client):
    """Users should only see their own boards."""
    # Register two users
    reg1 = await auth_client.post(
        "/auth/register",
        json={
            "email": "user1@example.com",
            "password": "securepass123",
            "display_name": "User1",
        },
    )
    token1 = reg1.json()["access_token"]

    reg2 = await auth_client.post(
        "/auth/register",
        json={
            "email": "user2@example.com",
            "password": "securepass123",
            "display_name": "User2",
        },
    )
    token2 = reg2.json()["access_token"]

    # Each creates a board with a temp git repo
    with tempfile.TemporaryDirectory() as tmpdir:
        os.system(f"cd {tmpdir} && git init -q && git commit --allow-empty -m init -q")

        await auth_client.post(
            "/boards",
            json={
                "name": "User1 Board",
                "repo_root": tmpdir,
            },
            headers={"Authorization": f"Bearer {token1}"},
        )

        await auth_client.post(
            "/boards",
            json={
                "name": "User2 Board",
                "repo_root": tmpdir,
            },
            headers={"Authorization": f"Bearer {token2}"},
        )

    # User1 should only see their board
    resp1 = await auth_client.get(
        "/boards", headers={"Authorization": f"Bearer {token1}"}
    )
    assert resp1.status_code == 200
    boards1 = resp1.json()["boards"]
    assert len(boards1) == 1
    assert boards1[0]["name"] == "User1 Board"

    # User2 should only see their board
    resp2 = await auth_client.get(
        "/boards", headers={"Authorization": f"Bearer {token2}"}
    )
    boards2 = resp2.json()["boards"]
    assert len(boards2) == 1
    assert boards2[0]["name"] == "User2 Board"


# ---- Unit tests (no HTTP, no DB) ----


def test_password_hashing():
    """Test password hashing and verification."""
    from app.services.auth_service import hash_password, verify_password

    hashed = hash_password("mypassword")
    assert hashed != "mypassword"
    assert verify_password("mypassword", hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_jwt_roundtrip():
    """Test JWT token creation and decoding."""
    from app.services.auth_service import create_access_token, decode_access_token

    token = create_access_token("user-123", "test@example.com")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["email"] == "test@example.com"


def test_jwt_invalid():
    """Invalid token should return None."""
    from app.services.auth_service import decode_access_token

    assert decode_access_token("bad.token.here") is None
    assert decode_access_token("") is None
