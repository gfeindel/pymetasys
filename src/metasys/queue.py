"""Single-consumer operation queue in front of the Driver.

The bridge is single-connection; the driver is single-threaded; this queue is
the choke point that enforces that. Every read, write, and manual-mode
transition goes through :meth:`OpQueue.submit`.

Priority lanes (lower int = higher priority):
    0: COMMAND (user-initiated write / F4 ack)
    1: READ (on-demand read requested by a user HTTP call)
    2: POLL (background refresh)
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .driver.driver import Driver

log = logging.getLogger(__name__)


# Priority values.
PRIO_COMMAND = 0
PRIO_READ = 1
PRIO_POLL = 2


@dataclass(order=True)
class _Op:
    """Wrapper for PriorityQueue ordering. Only priority and seq are compared."""

    priority: int
    seq: int
    # the rest are not part of the comparison key
    name: str = field(compare=False, default="")
    user: str = field(compare=False, default="")
    fn: Callable[[Driver], Awaitable[Any]] = field(compare=False, default=None)  # type: ignore[assignment]
    future: asyncio.Future[Any] = field(compare=False, default=None)  # type: ignore[assignment]
    timeout: float = field(compare=False, default=30.0)
    submitted_at: float = field(compare=False, default_factory=time.monotonic)


class OpQueue:
    """Async priority queue with a single consumer that holds the Driver."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver
        self._queue: asyncio.PriorityQueue[_Op] = asyncio.PriorityQueue()
        self._seq = itertools.count()
        self._consumer: asyncio.Task[None] | None = None
        self._stop = False
        self._paused = asyncio.Event()
        self._paused.set()  # set == running; cleared == paused
        self._current_op: _Op | None = None

    # ---- lifecycle ----------------------------------------------------

    def start(self) -> None:
        if self._consumer is None:
            self._stop = False
            self._consumer = asyncio.create_task(self._run(), name="op-queue")

    async def stop(self) -> None:
        self._stop = True
        if self._consumer is not None:
            self._consumer.cancel()
            try:
                await self._consumer
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._consumer = None

    # ---- pause / resume (for manual mode) -----------------------------

    def pause(self) -> None:
        """Stop consuming new ops. The currently-running op finishes normally."""
        self._paused.clear()

    def resume(self) -> None:
        self._paused.set()

    @property
    def is_paused(self) -> bool:
        return not self._paused.is_set()

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    @property
    def current(self) -> _Op | None:
        return self._current_op

    # ---- submission ---------------------------------------------------

    async def submit(
        self,
        fn: Callable[[Driver], Awaitable[Any]],
        *,
        priority: int = PRIO_READ,
        name: str = "",
        user: str = "",
        timeout: float = 30.0,
    ) -> Any:
        """Enqueue an op and await its result.

        ``fn`` is an async callable that receives the driver and returns
        anything. Exceptions propagate to the caller.
        """
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        op = _Op(
            priority=priority,
            seq=next(self._seq),
            name=name or fn.__name__,
            user=user,
            fn=fn,
            future=fut,
            timeout=timeout,
        )
        await self._queue.put(op)
        try:
            return await asyncio.wait_for(fut, timeout=timeout + 5.0)
        except asyncio.TimeoutError as e:  # noqa: PERF203
            if not fut.done():
                fut.cancel()
            raise TimeoutError(f"op {name} exceeded wall-clock timeout") from e

    # ---- consumer -----------------------------------------------------

    async def _run(self) -> None:
        while not self._stop:
            await self._paused.wait()
            try:
                op: _Op = await self._queue.get()
            except asyncio.CancelledError:
                return
            self._current_op = op
            log.debug(
                "op dequeued: prio=%d name=%s user=%s queued=%.2fs",
                op.priority,
                op.name,
                op.user,
                time.monotonic() - op.submitted_at,
            )
            if op.future.cancelled():
                self._current_op = None
                continue
            try:
                result = await asyncio.wait_for(op.fn(self._driver), timeout=op.timeout)
                if not op.future.done():
                    op.future.set_result(result)
            except asyncio.CancelledError:
                if not op.future.done():
                    op.future.cancel()
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("op %s failed", op.name)
                if not op.future.done():
                    op.future.set_exception(e)
            finally:
                self._current_op = None
