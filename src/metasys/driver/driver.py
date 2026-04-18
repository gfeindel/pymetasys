"""Terminal driver — navigation FSM over the CF Terminal screens.

The driver is the only thing that sends keystrokes to the bridge during normal
operation. The web app enqueues operations; the queue consumer calls methods
on the driver; the driver plans a keystroke path from current state to target
state and executes it, waiting for each screen to settle by positive anchor
confirmation (see plan §9).

Recovery: whenever state detection returns UNKNOWN, the driver sends ESC up
to a fixed number of times until it recognizes Main Menu. If that fails it
reconnects the bridge.

Manual passthrough: the driver can enter a MANUAL state in which it stops
parsing and yields the bridge to a subscriber that does bidirectional byte
forwarding. The queue must be paused by the caller before this is entered.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

from ..config import Settings
from . import keys
from .alarms import AlarmWatcher
from .bridge import Bridge
from .parsers import (
    CommandFieldOptions,
    GroupInfo,
    GroupSummary,
    PointSummary,
    parse_command_fields,
    parse_group_list,
    parse_group_summary,
    parse_message_line,
    parse_point_summary,
)
from .screen import Screen
from .states import State, detect_state

log = logging.getLogger(__name__)


class DriverError(RuntimeError):
    pass


class StateMismatch(DriverError):
    def __init__(self, expected: State, actual: State, message: str = "") -> None:
        super().__init__(f"expected {expected.name}, got {actual.name}. {message}")
        self.expected = expected
        self.actual = actual


@dataclass
class CommandRequest:
    point_number: int
    command_type: str  # e.g. "Override", "Auto", "Command", "Release", "Adjust"
    value: str  # the value to set; "" for commands that take no value (e.g. Release)


@dataclass
class CommandResult:
    before: str | None  # value as seen before the command was issued
    after: str | None  # value as seen after re-reading
    message: str  # message line after issuing (error or confirmation)
    success: bool


class Driver:
    """Own the bridge socket + pyte Screen; expose high-level operations."""

    def __init__(
        self,
        bridge: Bridge,
        screen: Screen,
        settings: Settings,
    ) -> None:
        self._bridge = bridge
        self._screen = screen
        self._settings = settings
        self._state: State = State.UNKNOWN
        self._manual_mode = False
        self.alarms = AlarmWatcher(
            screen,
            autoack_below=settings.alarm_autoack_below,
            send_ack=self._send_ack,
        )

    # ---- lifecycle ----------------------------------------------------

    async def start(self) -> None:
        """Start alarm watcher and subscribe screen to the bridge.

        Does NOT block on bridge connection or navigation — the app may come up
        with the bridge down. Actual wake + recovery runs in the background
        once the bridge connects; ops that need the terminal in a known state
        are responsible for calling :meth:`goto_main_menu`.
        """
        self._bridge.subscribe(self._screen.feed)
        self.alarms.start()
        asyncio.create_task(self._initial_recovery(), name="driver-initial-recover")

    async def _initial_recovery(self) -> None:
        try:
            await self._bridge.wait_connected()
            await self._bridge.send(keys.ENTER)
            await self._wait_settled(timeout=self._settings.settle_timeout)
            await self._recover_to_main_menu()
        except Exception:  # noqa: BLE001
            log.exception("driver: initial recovery failed — ops will surface the error")

    async def stop(self) -> None:
        await self.alarms.stop()

    @property
    def state(self) -> State:
        return self._state

    @property
    def manual_mode(self) -> bool:
        return self._manual_mode

    # ---- low-level helpers --------------------------------------------

    async def _send_ack(self) -> None:
        await self._bridge.send(keys.F4)
        await asyncio.sleep(0.2)

    async def _send(self, data: bytes) -> None:
        if self._manual_mode:
            raise DriverError("cannot send structured keystrokes while in manual mode")
        await self.alarms.wait_unblocked()
        await self._bridge.send(data)

    async def _wait_settled(
        self,
        *,
        expect: Callable[[], bool] | None = None,
        timeout: float | None = None,
    ) -> None:
        """Wait for the screen to settle.

        If ``expect`` is given, wait for that predicate to be True (anchor
        confirmation). Otherwise fall back to quiet-time heuristic.
        """
        t = timeout or self._settings.settle_timeout
        if expect is not None:
            ok = await self._screen.wait_for(lambda _s: expect(), timeout=t)
            if not ok:
                log.debug("wait_settled: expected anchor never appeared within %.2fs", t)
            return
        await self._screen.wait_quiet(self._settings.settle_quiet_ms, timeout=t)

    def _detect(self) -> State:
        self._state = detect_state(self._screen)
        return self._state

    async def _recover_to_main_menu(self, attempts: int = 8) -> None:
        """ESC our way back to Main Menu. Also ack any blocking alarm first."""
        for _ in range(attempts):
            if self.alarms.is_blocked:
                # Human is required — we can't recover. Surface this to caller.
                raise DriverError(
                    "cannot recover to Main Menu while a human-ack alarm is up"
                )
            current = self._detect()
            if current is State.MAIN_MENU:
                return
            if current is State.LOGIN_PROMPT:
                await self._login()
                continue
            await self._bridge.send(keys.ESC)
            await self._wait_settled(timeout=1.0)
        raise DriverError("could not recover to Main Menu after %d ESC attempts" % attempts)

    async def _login(self) -> None:
        pw = self._settings.panel_password
        if not pw:
            raise DriverError("password prompt hit but METASYS_PANEL_PASSWORD is empty")
        await self._bridge.send(keys.ENTER)
        await asyncio.sleep(0.2)
        await self._bridge.send(keys.text(pw))
        await self._bridge.send(keys.ENTER)
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.MAIN_MENU,
            timeout=5.0,
        )

    # ---- navigation ---------------------------------------------------

    async def goto_main_menu(self) -> None:
        await self._recover_to_main_menu()

    async def goto_group_list(self) -> None:
        """Main Menu → G → S."""
        await self.goto_main_menu()
        await self._send(keys.menu("G"))
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.GROUP_MENU,
            timeout=2.0,
        )
        if self._detect() is not State.GROUP_MENU:
            raise StateMismatch(State.GROUP_MENU, self._state)

        await self._send(keys.menu("S"))
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.GROUP_LIST,
            timeout=2.0,
        )
        if self._detect() is not State.GROUP_LIST:
            raise StateMismatch(State.GROUP_LIST, self._state)

    async def goto_group_summary(self, group_number: int) -> None:
        """Main Menu → G → S → <n> → Enter."""
        await self.goto_group_list()
        await self._send(keys.digits(group_number))
        await self._send(keys.ENTER)
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.GROUP_SUMMARY,
            timeout=3.0,
        )
        if self._detect() is not State.GROUP_SUMMARY:
            raise StateMismatch(
                State.GROUP_SUMMARY,
                self._state,
                f"after entering group number {group_number}",
            )

    async def goto_point_menu(self) -> None:
        await self.goto_main_menu()
        await self._send(keys.menu("P"))
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.POINT_MENU,
            timeout=2.0,
        )
        if self._detect() is not State.POINT_MENU:
            raise StateMismatch(State.POINT_MENU, self._state)

    async def goto_point_summary(self, starting_point: int = 1) -> None:
        await self.goto_point_menu()
        await self._send(keys.menu("S"))
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.POINT_SUMMARY_SELECT,
            timeout=2.0,
        )
        await self._send(keys.digits(starting_point))
        await self._send(keys.ENTER)
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.POINT_SUMMARY,
            timeout=3.0,
        )
        if self._detect() is not State.POINT_SUMMARY:
            raise StateMismatch(State.POINT_SUMMARY, self._state)

    async def goto_point_override(self) -> None:
        """Main Menu → P → O. Lands on a Group Summary with Point To Command [ ] field."""
        await self.goto_point_menu()
        await self._send(keys.menu("O"))
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.POINT_OVERRIDE,
            timeout=3.0,
        )
        if self._detect() is not State.POINT_OVERRIDE:
            raise StateMismatch(State.POINT_OVERRIDE, self._state)

    # ---- read operations ----------------------------------------------

    async def read_group_list(self) -> tuple[GroupInfo, ...]:
        await self.goto_group_list()
        return parse_group_list(self._screen)

    async def read_group_summary(self, group_number: int) -> GroupSummary:
        await self.goto_group_summary(group_number)
        gs = parse_group_summary(self._screen)
        if gs is None:
            raise DriverError("group summary detected but parser returned None")
        return gs

    async def read_point_summary(self, starting_point: int = 1) -> PointSummary:
        await self.goto_point_summary(starting_point)
        ps = parse_point_summary(self._screen)
        if ps is None:
            raise DriverError("point summary detected but parser returned None")
        return ps

    # ---- command ------------------------------------------------------

    async def command_point(self, req: CommandRequest) -> CommandResult:
        """Execute a Point Override / Command.

        Per plan §2: every command path re-reads the current value first and
        returns it alongside the new value so callers can surface "before → after"
        to the operator.
        """
        # First, read current value via Point Summary starting at this point.
        # We can't rely on Group Summary unless we know the point's group.
        before: str | None = None
        try:
            ps = await self.read_point_summary(req.point_number)
            for p in ps.points:
                if p.number == req.point_number:
                    before = p.value
                    break
        except Exception:  # noqa: BLE001
            log.warning("could not pre-read value for point %d", req.point_number)

        # Now walk the command flow: P → O → <n> Enter → <type> → <value> Enter.
        await self.goto_point_override()
        await self._send(keys.digits(req.point_number))
        await self._send(keys.ENTER)
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.POINT_COMMAND_FIELDS,
            timeout=3.0,
        )
        if self._detect() is not State.POINT_COMMAND_FIELDS:
            raise StateMismatch(
                State.POINT_COMMAND_FIELDS,
                self._state,
                f"entering point {req.point_number} to command",
            )

        # Command type: many defaults are correct; in the general case type the
        # full word. The device accepts space-bar scrolling as well, but typing
        # is deterministic.
        await self._send(keys.text(req.command_type))
        await self._send(keys.ENTER)
        await asyncio.sleep(0.2)

        # Value.
        if req.value:
            await self._send(keys.text(req.value))
        await self._send(keys.ENTER)
        await self._wait_settled(timeout=3.0)

        message = parse_message_line(self._screen)
        # Success heuristic: no flashing-error indicator in the message line,
        # and we're still on GROUP_SUMMARY / POINT_OVERRIDE (not stuck in
        # command fields).
        current = self._detect()
        success = current in (State.GROUP_SUMMARY, State.POINT_OVERRIDE) and not _looks_like_error(
            message
        )

        # Re-read the value.
        after: str | None = None
        try:
            ps2 = await self.read_point_summary(req.point_number)
            for p in ps2.points:
                if p.number == req.point_number:
                    after = p.value
                    break
        except Exception:  # noqa: BLE001
            log.warning("could not post-read value for point %d", req.point_number)

        return CommandResult(before=before, after=after, message=message, success=success)

    # ---- command field discovery --------------------------------------

    async def probe_command_options(self, point_number: int) -> CommandFieldOptions:
        """Enter the command screen for a point and parse available command types.

        Used by the web UI to populate the command-type dropdown. Immediately
        cancels out with F1 afterward, no side effects.
        """
        await self.goto_point_override()
        await self._send(keys.digits(point_number))
        await self._send(keys.ENTER)
        await self._wait_settled(
            expect=lambda: detect_state(self._screen) == State.POINT_COMMAND_FIELDS,
            timeout=3.0,
        )
        opts = parse_command_fields(self._screen)
        # Back out — F1 Cancel discards and returns.
        await self._send(keys.F1)
        await self._wait_settled(timeout=1.5)
        if opts is None:
            raise DriverError(f"could not parse command field options for point {point_number}")
        return opts

    # ---- manual passthrough -------------------------------------------

    async def enter_manual_mode(self) -> None:
        """Stop parsing and let a caller bidirectionally forward bytes.

        Caller is responsible for pausing the op queue before invoking this and
        for calling :meth:`exit_manual_mode` when done. While in manual mode,
        structured operations will raise.
        """
        log.info("driver: entering MANUAL passthrough mode")
        self._manual_mode = True

    async def exit_manual_mode(self) -> None:
        log.info("driver: exiting MANUAL passthrough mode")
        self._manual_mode = False
        # Recover to a known state.
        try:
            await self._recover_to_main_menu()
        except Exception:  # noqa: BLE001
            log.exception("could not recover to Main Menu after manual mode")

    async def manual_send(self, data: bytes) -> None:
        """Bypass-the-FSM send. Caller must have entered manual mode."""
        if not self._manual_mode:
            raise DriverError("manual_send called outside MANUAL mode")
        await self._bridge.send(data)


def _looks_like_error(message: str) -> bool:
    if not message:
        return False
    lower = message.lower()
    # Heuristic — the manual shows error text like "Value too high (1-130)".
    return any(
        tok in lower
        for tok in ("invalid", "error", "too high", "too low", "not allowed", "must be")
    )
