"""Manual-terminal passthrough session management.

At most one manual session may be active at a time. While active:
  * the op queue is paused
  * the driver is in MANUAL mode (structured ops will error)
  * keystrokes from the user's xterm.js are forwarded to the bridge
  * every byte in both directions is audit-logged
  * a timeout (default 10 min) closes the session and resumes the queue
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from .config import get_settings
from .driver.driver import Driver
from .queue import OpQueue

log = logging.getLogger(__name__)


@dataclass
class ManualSession:
    owner: str
    started_at: float = field(default_factory=time.monotonic)
    deadline: float = 0.0
    warn_at: float = 0.0

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())


class ManualSessionManager:
    def __init__(self, driver: Driver, queue: OpQueue) -> None:
        self._driver = driver
        self._queue = queue
        self._lock = asyncio.Lock()
        self._current: ManualSession | None = None
        self._settings = get_settings()

    @property
    def current(self) -> ManualSession | None:
        return self._current

    async def acquire(self, owner: str) -> ManualSession:
        async with self._lock:
            if self._current is not None:
                raise RuntimeError(
                    f"manual session already held by {self._current.owner}"
                )
            # Pause the queue first so no structured op is mid-flight.
            self._queue.pause()
            await self._driver.enter_manual_mode()
            now = time.monotonic()
            sess = ManualSession(
                owner=owner,
                started_at=now,
                deadline=now + self._settings.manual_session_seconds,
                warn_at=now + self._settings.manual_warn_seconds,
            )
            self._current = sess
            log.info("manual session acquired by %s (deadline in %ds)", owner,
                     self._settings.manual_session_seconds)
            return sess

    async def release(self, owner: str) -> None:
        async with self._lock:
            if self._current is None or self._current.owner != owner:
                return
            await self._driver.exit_manual_mode()
            self._queue.resume()
            self._current = None
            log.info("manual session released by %s", owner)

    async def extend(self, owner: str, seconds: int) -> None:
        async with self._lock:
            if self._current is None or self._current.owner != owner:
                raise RuntimeError("no active session to extend")
            self._current.deadline += seconds
            self._current.warn_at += seconds
