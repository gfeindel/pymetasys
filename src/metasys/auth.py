"""Cookie-session auth and password hashing.

Small, purpose-built. Sessions are signed (itsdangerous) cookies containing
``{"uid": int, "role": str}``. No server-side session store — the cookie is
the session. Good enough for a single-panel, <20-user deployment.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeSerializer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import User, get_session

SESSION_COOKIE = "metasys_session"

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(get_settings().secret_key, salt="session")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd.verify(password, hashed)
    except Exception:  # noqa: BLE001
        return False


def issue_session(response: Response, user: User) -> None:
    token = _serializer().dumps({"uid": user.id, "role": user.role, "username": user.username})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=False,  # flip to True behind HTTPS
        max_age=60 * 60 * 12,
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


async def current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    session_cookie: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User:
    # Also accept a token via the Sec-WebSocket-Protocol header for WS handshakes
    # where cookies aren't convenient.
    token = session_cookie or request.headers.get("x-metasys-session")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated"
        )
    try:
        data = _serializer().loads(token)
    except BadSignature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session"
        ) from None
    user = await session.scalar(select(User).where(User.id == data["uid"]))
    if user is None or user.disabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found or disabled"
        )
    return user


def require_role(*roles: str):
    async def dep(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role {user.role} not in {roles}",
            )
        return user

    return dep


require_admin = require_role("admin")
require_any = require_role("admin", "user")
