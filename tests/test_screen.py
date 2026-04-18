"""Tests for the pyte-backed Screen wrapper + settle waits."""

from __future__ import annotations

import asyncio

import pytest

from metasys.driver.screen import Screen
from tests.fixtures import GROUP_SUMMARY_ROWS, MAIN_MENU_ROWS, layout


def test_feed_plain_text():
    s = Screen()
    s.feed(b"hello")
    assert "hello" in s.line(0)


def test_feed_layout_places_rows_correctly():
    s = Screen()
    s.feed(layout(MAIN_MENU_ROWS))
    assert "Main Function Menu" in s.text()
    assert "F1 Cancel" in s.line(23)


def test_contains_at_is_position_sensitive():
    s = Screen()
    s.feed(layout(GROUP_SUMMARY_ROWS))
    assert s.contains("Point To Command", ) is True
    # The Point To Command label starts at column 0 on row 3.
    assert s.contains_at(3, 0, "Point To Command") is True
    assert s.contains_at(3, 5, "Point To Command") is False


def test_snapshot_is_immutable_copy():
    s = Screen()
    s.feed(layout(MAIN_MENU_ROWS))
    snap = s.snapshot()
    s.feed(b"\x1b[2J\x1b[H")  # clear
    assert "Main Function Menu" in "\n".join(snap)


@pytest.mark.asyncio
async def test_wait_for_fires_on_new_bytes():
    s = Screen()

    async def feeder():
        await asyncio.sleep(0.05)
        s.feed(layout(MAIN_MENU_ROWS))

    asyncio.create_task(feeder())
    ok = await s.wait_for(lambda sc: "Main Function Menu" in sc.text(), timeout=1.0)
    assert ok is True


@pytest.mark.asyncio
async def test_wait_for_times_out():
    s = Screen()
    ok = await s.wait_for(lambda sc: False, timeout=0.1)
    assert ok is False
