"""Tests for alarm detection and auto-ack logic."""

from __future__ import annotations

import asyncio

import pytest

from metasys.config import AlarmPriority
from metasys.driver.alarms import AlarmWatcher, detect_alarm
from metasys.driver.screen import Screen
from tests.fixtures import CRITICAL_ALARM_ROWS, GROUP_SUMMARY_ROWS, layout


def test_detect_alarm_classifies_critical():
    s = Screen()
    s.feed(layout(CRITICAL_ALARM_ROWS))
    alarm = detect_alarm(s)
    assert alarm is not None
    assert alarm.priority is AlarmPriority.CRITICAL
    assert "CRITICAL" in alarm.text


def test_detect_alarm_none_when_quiet():
    s = Screen()
    s.feed(layout(GROUP_SUMMARY_ROWS))
    assert detect_alarm(s) is None


@pytest.mark.asyncio
async def test_watcher_blocks_on_critical_when_threshold_is_critical():
    s = Screen()
    acks: list[None] = []

    async def ack():
        acks.append(None)

    watcher = AlarmWatcher(
        s, autoack_below=AlarmPriority.CRITICAL, send_ack=ack, poll_interval=0.05
    )
    watcher.start()
    s.feed(layout(CRITICAL_ALARM_ROWS))
    await asyncio.sleep(0.2)
    try:
        assert watcher.is_blocked is True
        assert watcher.blocked_alarm is not None
        assert watcher.blocked_alarm.priority is AlarmPriority.CRITICAL
        assert acks == []  # did NOT auto-ack
    finally:
        await watcher.stop()


@pytest.mark.asyncio
async def test_watcher_autoacks_network_when_threshold_is_critical():
    # A network-priority alarm is strictly below CRITICAL → auto-ack.
    s = Screen()
    network_alarm_rows = list(CRITICAL_ALARM_ROWS)
    network_alarm_rows[1] = "  NETWORK ALARM: Controller 5 offline at 14:41:50"

    ack_calls = 0

    async def ack():
        nonlocal ack_calls
        ack_calls += 1
        # Simulate the panel clearing the alarm region after ack.
        s.feed(b"\x1b[2;1H" + (" " * 80).encode())

    watcher = AlarmWatcher(
        s, autoack_below=AlarmPriority.CRITICAL, send_ack=ack, poll_interval=0.05
    )
    watcher.start()
    s.feed(layout(network_alarm_rows))
    await asyncio.sleep(0.3)
    try:
        assert ack_calls >= 1
        assert watcher.is_blocked is False
    finally:
        await watcher.stop()
