"""SQLAlchemy async models: users and audit log."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # 'admin' | 'user'
    disabled: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="user")


class AuditEvent(Base):
    """Record of any operator action that touches the Panel Unit.

    Per plan §4 — this is the only record of who-did-what because the device
    sees every action as the same service account.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="")  # denormalized
    kind: Mapped[str] = mapped_column(String(32))  # e.g. 'command', 'ack', 'manual_send', 'login'
    point_number: Mapped[int | None] = mapped_column(nullable=True)
    command_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    command_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    after_value: Mapped[str | None] = mapped_column(String(128), nullable=True)
    success: Mapped[bool] = mapped_column(default=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # For manual-mode keystroke logs.
    raw_bytes_hex: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User | None] = relationship(back_populates="audit_events")


# ---- engine + session accessor ------------------------------------------

_engine = None
_Session: async_sessionmaker[AsyncSession] | None = None
_init_lock = asyncio.Lock()


async def init_db() -> None:
    global _engine, _Session
    async with _init_lock:
        if _engine is not None:
            return
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, future=True)
        _Session = async_sessionmaker(_engine, expire_on_commit=False)
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    if _Session is None:
        await init_db()
    assert _Session is not None
    async with _Session() as session:
        yield session
