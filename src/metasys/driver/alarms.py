"""Alarm detection and acknowledgment.

Critical and Network alarms appear in the Alarm Report Area whenever they
happen. They must be F4-acknowledged before a lower-priority alarm can
display. The :class:`AlarmWatcher` task continuously inspects the alarm
region; on detection it:

1. Logs the alarm.
2. Emits the alarm on an async queue so the web app can surface it.
3. Either auto-acks (if config.alarm_autoack_below allows) or blocks the
   driver in "alarm-blocked" state until a human acks via the UI.

Alarm region starts on row 1 (below the operator/time line) and runs until
the dashes separator. We use a heuristic: non-empty content in rows 1-2 that
contains an alarm keyword ("ALARM", "CRITICAL", "NETWORK"), or is clearly
non-menu text.

Acknowledgment is F4. Rate-limited to 1/sec to avoid spamming during alarm
storms.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..config import AlarmPriority
from .screen import ALARM_REPORT, Screen

log = logging.getLogger(__name__)

# Priority ordering (higher = more severe). The autoack config gate is
# "auto-ack anything strictly below this priority".
_PRIORITY_RANK = {
    AlarmPriority.STATUS: 0,
    AlarmPriority.FOLLOWUP: 1,
    AlarmPriority.NETWORK: 2,
    AlarmPriority.CRITICAL: 3,
}


@dataclass
class Alarm:
    """One alarm read out of the Alarm Report area."""

    text: str
    priority: AlarmPriority
    seen_at: float = field(default_factory=time.time)

    @property
    def rank(self) -> int:
        return _PRIORITY_RANK[self.priority]


def _classify(text: str) -> AlarmPriority:
    t = text.upper()
    if "CRITICAL" in t or "FIRE" in t:
        return AlarmPriority.CRITICAL
    if "NETWORK" in t:
        return AlarmPriority.NETWORK
    if "STATUS" in t:
        return AlarmPriority.STATUS
    return AlarmPriority.FOLLOWUP


_ALARM_HINTS = re.compile(r"\b(ALARM|CRITICAL|NETWORK|FIRE|TROUBLE)\b", re.IGNORECASE)


def detect_alarm(screen: Screen) -> Alarm | None:
    """Look at the alarm region. Return an Alarm if something non-trivial is there."""
    text = screen.text(ALARM_REPORT).strip()
    if not text:
        return None
    # Filter out the dashes-separator if it happens to be in the region.
    lines = [ln.strip(" -") for ln in text.splitlines() if ln.strip(" -")]
    if not lines:
        return None
    joined = " ".join(lines)
    if not _ALARM_HINTS.search(joined):
        return None
    return Alarm(text=joined, priority=_classify(joined))


Ackable = Callable[[], Awaitable[None]]  # sends F4 and waits for screen to settle


class AlarmWatcher:
    """Background task that watches the alarm region and auto-acks as configured."""

    def __init__(
        self,
        screen: Screen,
        *,
        autoack_below: AlarmPriority,
        send_ack: Ackable,
        poll_interval: float = 0.25,
        rate_limit: float = 1.0,
    ) -> None:
        self._screen = screen
        self._autoack_below = autoack_below
        self._send_ack = send_ack
        self._poll_interval = poll_interval
        self._rate_limit = rate_limit
        self._task: asyncio.Task[None] | None = None
        self._stop = False
        self._listeners: set[asyncio.Queue[Alarm]] = set()
        self._blocked = asyncio.Event()  # set => a human-ack-required alarm is up
        self._blocked_alarm: Alarm | None = None
        self._last_seen: str = ""
        self._last_ack_at: float = 0.0

    # ---- lifecycle ----------------------------------------------------

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop = False
        self._task = asyncio.create_task(self._run(), name="alarm-watcher")

    async def stop(self) -> None:
        self._stop = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    # ---- pub/sub ------------------------------------------------------

    def subscribe(self) -> asyncio.Queue[Alarm]:
        q: asyncio.Queue[Alarm] = asyncio.Queue(maxsize=64)
        self._listeners.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Alarm]) -> None:
        self._listeners.discard(q)

    # ---- state --------------------------------------------------------

    @property
    def is_blocked(self) -> bool:
        return self._blocked.is_set()

    @property
    def blocked_alarm(self) -> Alarm | None:
        return self._blocked_alarm

    async def wait_unblocked(self) -> None:
        while self.is_blocked:
            await asyncio.sleep(0.1)

    async def human_ack(self) -> None:
        """Called when a human clicks 'Ack' in the web UI."""
        now = time.monotonic()
        if now - self._last_ack_at < self._rate_limit:
            await asyncio.sleep(self._rate_limit - (now - self._last_ack_at))
        await self._send_ack()
        self._last_ack_at = time.monotonic()
        self._blocked.clear()
        self._blocked_alarm = None

    # ---- loop ---------------------------------------------------------

    async def _run(self) -> None:
        while not self._stop:
            try:
                alarm = detect_alarm(self._screen)
                if alarm is not None and alarm.text != self._last_seen:
                    self._last_seen = alarm.text
                    log.info("alarm detected [%s]: %s", alarm.priority.value, alarm.text)
                    for q in list(self._listeners):
                        try:
                            q.put_nowait(alarm)
                        except asyncio.QueueFull:
                            pass

                    target_rank = _PRIORITY_RANK[self._autoack_below]
                    if alarm.rank < target_rank:
                        # strictly-below threshold → auto-ack
                        now = time.monotonic()
                        if now - self._last_ack_at >= self._rate_limit:
                            log.info("auto-acking alarm (below threshold %s)", self._autoack_below.value)
                            try:
                                await self._send_ack()
                                self._last_ack_at = time.monotonic()
                            except Exception:  # noqa: BLE001
                                log.exception("auto-ack failed")
                    else:
                        self._blocked_alarm = alarm
                        self._blocked.set()
                elif alarm is None and self._blocked.is_set():
                    # Alarm region cleared — someone else acked or it timed out.
                    self._blocked.clear()
                    self._blocked_alarm = None
                    self._last_seen = ""
            except Exception:  # noqa: BLE001
                log.exception("alarm watcher iteration failed")
            await asyncio.sleep(self._poll_interval)
