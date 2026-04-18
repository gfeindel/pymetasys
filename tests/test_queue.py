"""Tests for the operation queue's priority ordering and pause/resume."""

from __future__ import annotations

import asyncio

import pytest

from metasys.queue import PRIO_COMMAND, PRIO_POLL, PRIO_READ, OpQueue


class _FakeDriver:
    """Driver stand-in for queue tests — records the order of op executions."""

    def __init__(self) -> None:
        self.order: list[str] = []

    async def work(self, label: str, delay: float = 0.0) -> str:
        if delay:
            await asyncio.sleep(delay)
        self.order.append(label)
        return label


@pytest.mark.asyncio
async def test_fifo_within_same_priority():
    driver = _FakeDriver()
    q = OpQueue(driver)  # type: ignore[arg-type]
    q.start()
    try:
        results = await asyncio.gather(
            q.submit(lambda d: d.work("a"), priority=PRIO_READ, name="a"),
            q.submit(lambda d: d.work("b"), priority=PRIO_READ, name="b"),
            q.submit(lambda d: d.work("c"), priority=PRIO_READ, name="c"),
        )
        assert results == ["a", "b", "c"]
        assert driver.order == ["a", "b", "c"]
    finally:
        await q.stop()


@pytest.mark.asyncio
async def test_higher_priority_preempts_waiting_lower():
    driver = _FakeDriver()
    q = OpQueue(driver)  # type: ignore[arg-type]
    q.start()
    try:
        # First op holds the consumer for a bit; queue up a POLL and then a
        # COMMAND behind it. COMMAND should run before POLL despite being
        # submitted later.
        first = asyncio.create_task(
            q.submit(lambda d: d.work("first", delay=0.2), priority=PRIO_READ, name="first")
        )
        await asyncio.sleep(0.05)  # let 'first' become the current op
        poll = asyncio.create_task(
            q.submit(lambda d: d.work("poll"), priority=PRIO_POLL, name="poll")
        )
        await asyncio.sleep(0.01)
        cmd = asyncio.create_task(
            q.submit(lambda d: d.work("cmd"), priority=PRIO_COMMAND, name="cmd")
        )
        await asyncio.gather(first, poll, cmd)
        # "first" always first (already dequeued). "cmd" before "poll".
        assert driver.order == ["first", "cmd", "poll"]
    finally:
        await q.stop()


@pytest.mark.asyncio
async def test_pause_blocks_new_ops():
    driver = _FakeDriver()
    q = OpQueue(driver)  # type: ignore[arg-type]
    q.start()
    q.pause()
    try:
        task = asyncio.create_task(
            q.submit(lambda d: d.work("x"), priority=PRIO_READ, name="x", timeout=0.5)
        )
        await asyncio.sleep(0.15)
        assert not task.done()
        q.resume()
        result = await task
        assert result == "x"
    finally:
        await q.stop()
