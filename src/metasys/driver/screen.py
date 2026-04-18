"""pyte-backed virtual screen with a settle heuristic.

The Panel Unit renders into a 24x80 VT100-ish screen. We keep a running
:class:`pyte.Screen` that the bridge feeds bytes into, and expose helpers
for querying it by row/column.

Settle strategy (from the plan, §9): prefer anchor-based confirmation over
pure time-based quiescence. :meth:`Screen.wait_for` lets callers wait until
a known marker appears at a known coordinate — this is the positive signal
that a screen is fully drawn. We still expose a time-based
:meth:`Screen.wait_quiet` for the corner cases where no stable anchor exists.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable

import pyte

log = logging.getLogger(__name__)

ROWS = 24
COLS = 80


@dataclass(frozen=True)
class Region:
    """Inclusive rectangular region of the screen."""

    top: int
    left: int
    bottom: int
    right: int

    def clamp(self) -> "Region":
        return Region(
            top=max(0, self.top),
            left=max(0, self.left),
            bottom=min(ROWS - 1, self.bottom),
            right=min(COLS - 1, self.right),
        )


# Layout regions from the manual — can be tuned after Phase 0. These are
# 0-indexed inclusive bounds.
TIME_LINE = Region(top=0, left=0, bottom=0, right=COLS - 1)
ALARM_REPORT = Region(top=1, left=0, bottom=2, right=COLS - 1)
MAIN_AREA = Region(top=3, left=0, bottom=21, right=COLS - 1)
MESSAGE_LINE = Region(top=22, left=0, bottom=22, right=COLS - 1)
FKEY_LINE = Region(top=23, left=0, bottom=23, right=COLS - 1)


Predicate = Callable[["Screen"], bool]


class Screen:
    """Async-friendly wrapper around a pyte screen."""

    def __init__(self, rows: int = ROWS, cols: int = COLS) -> None:
        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.ByteStream(self._screen)
        self._updated = asyncio.Event()
        self._last_byte_at: float = 0.0

    # ---- feed ---------------------------------------------------------

    def feed(self, data: bytes) -> None:
        """Feed raw bytes into the virtual terminal. Safe to call from sync ctx."""
        if not data:
            return
        self._stream.feed(data)
        self._last_byte_at = time.monotonic()
        # set() from any thread is OK for asyncio.Event because we use a single
        # loop and the bridge sink is invoked from that loop. Guard by checking
        # the running loop exists.
        self._updated.set()

    # ---- raw access ---------------------------------------------------

    @property
    def rows(self) -> int:
        return self._screen.lines

    @property
    def cols(self) -> int:
        return self._screen.columns

    def line(self, row: int) -> str:
        """Full text of a row, including trailing spaces."""
        if row < 0 or row >= self._screen.lines:
            return ""
        return self._screen.display[row]

    def text(self, region: Region | None = None) -> str:
        """Newline-joined text of a region (or full screen)."""
        region = region.clamp() if region else Region(0, 0, ROWS - 1, COLS - 1)
        return "\n".join(
            self._screen.display[r][region.left : region.right + 1]
            for r in range(region.top, region.bottom + 1)
        )

    def snapshot(self) -> list[str]:
        """Copy of the full display — stable, unaffected by later feeds."""
        return list(self._screen.display)

    def cursor(self) -> tuple[int, int]:
        """(row, col) 0-indexed."""
        return self._screen.cursor.y, self._screen.cursor.x

    def contains_at(self, row: int, col: int, needle: str) -> bool:
        if row < 0 or row >= self._screen.lines:
            return False
        line = self._screen.display[row]
        end = col + len(needle)
        if end > len(line):
            return False
        return line[col:end] == needle

    def contains(self, needle: str, region: Region | None = None) -> bool:
        return needle in self.text(region)

    # ---- waiting ------------------------------------------------------

    async def wait_for(
        self,
        predicate: Predicate,
        *,
        timeout: float,
    ) -> bool:
        """Wait until ``predicate(self)`` is True, or timeout.

        The predicate is re-evaluated each time bytes are received. This is the
        anchor-based settle strategy recommended in the plan.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        if predicate(self):
            return True
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return predicate(self)
            self._updated.clear()
            try:
                await asyncio.wait_for(self._updated.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                return predicate(self)
            if predicate(self):
                return True

    async def wait_quiet(self, quiet_ms: int, *, timeout: float) -> bool:
        """Return True when the stream has been idle for ``quiet_ms`` ms.

        Prefer :meth:`wait_for` with a positive anchor when one is available.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            now = asyncio.get_event_loop().time()
            if now >= deadline:
                return False
            idle = (now * 1000) - (self._last_byte_at * 1000)
            if idle >= quiet_ms and self._last_byte_at > 0:
                return True
            wait = min(quiet_ms / 1000.0, deadline - now)
            self._updated.clear()
            try:
                await asyncio.wait_for(self._updated.wait(), timeout=wait)
            except asyncio.TimeoutError:
                # No new bytes in the slice. Loop to re-check idle time.
                pass
