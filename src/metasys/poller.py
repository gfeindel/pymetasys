"""Background poller that refreshes Group Summaries for WS subscribers.

One poller per subscribed group, shared across subscribers. Uses the lowest
priority lane on the OpQueue so user-initiated reads and commands always
preempt polling.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator

from .driver.parsers import GroupSummary
from .queue import PRIO_POLL, OpQueue

log = logging.getLogger(__name__)


@dataclass
class _GroupChannel:
    task: asyncio.Task[None]
    subscribers: set[asyncio.Queue[GroupSummary]]
    last: GroupSummary | None = None


class GroupPoller:
    def __init__(self, queue: OpQueue, *, interval: float) -> None:
        self._queue = queue
        self._interval = interval
        self._channels: dict[int, _GroupChannel] = {}
        self._lock = asyncio.Lock()

    async def stop(self) -> None:
        for ch in list(self._channels.values()):
            ch.task.cancel()
            try:
                await ch.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._channels.clear()

    async def subscribe(self, group_number: int) -> AsyncIterator[GroupSummary]:
        q: asyncio.Queue[GroupSummary] = asyncio.Queue(maxsize=8)
        async with self._lock:
            ch = self._channels.get(group_number)
            if ch is None:
                task = asyncio.create_task(
                    self._poll(group_number), name=f"poll-group-{group_number}"
                )
                ch = _GroupChannel(task=task, subscribers=set())
                self._channels[group_number] = ch
            ch.subscribers.add(q)
            if ch.last is not None:
                try:
                    q.put_nowait(ch.last)
                except asyncio.QueueFull:
                    pass
        try:
            while True:
                yield await q.get()
        finally:
            async with self._lock:
                ch = self._channels.get(group_number)
                if ch is not None:
                    ch.subscribers.discard(q)
                    if not ch.subscribers:
                        ch.task.cancel()
                        try:
                            await ch.task
                        except (asyncio.CancelledError, Exception):  # noqa: BLE001
                            pass
                        self._channels.pop(group_number, None)

    async def _poll(self, group_number: int) -> None:
        while True:
            try:
                summary: GroupSummary = await self._queue.submit(
                    lambda d: d.read_group_summary(group_number),
                    priority=PRIO_POLL,
                    name=f"poll-group-{group_number}",
                    user="_poller",
                    timeout=15.0,
                )
                ch = self._channels.get(group_number)
                if ch is not None:
                    ch.last = summary
                    for q in list(ch.subscribers):
                        try:
                            q.put_nowait(summary)
                        except asyncio.QueueFull:
                            # Drop oldest, push newest.
                            try:
                                q.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                            try:
                                q.put_nowait(summary)
                            except asyncio.QueueFull:
                                pass
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("poll iteration failed for group %d", group_number)
            await asyncio.sleep(self._interval)
