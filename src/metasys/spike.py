"""Phase 0 spike — validate pyte against the real device.

This is the go/no-go gate from the plan. It:

1. Connects to the bridge.
2. Records every byte received to ``spike-raw.bin`` so we have a real
   captured trace to build test fixtures against.
3. Feeds them through pyte and dumps the virtual screen to stdout.
4. Wakes the terminal (ENTER + ESC x3), optionally logs in, and walks
   ``G → S → <group> → Enter`` to get to a Group Summary.
5. Prints the settled screen and exits.

If pyte handles the device's actual VT100 dialect, you'll see a readable
24x80 grid with recognizable menu content. If it doesn't — the grid will
be garbled or empty — the driver design needs to use pyte's lower-level
``Stream`` with custom listeners, or hand-rolled escape parsing. **Do not
proceed to Phase 1 until this spike produces a clean screen.**

Usage::

    python -m metasys.spike --host 10.0.0.50 --port 4001 --group 1
    # password picked up from METASYS_PANEL_PASSWORD env var, or --password

All arguments are optional; defaults come from .env / config.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import get_settings
from .driver import keys
from .driver.bridge import Bridge, PtyBridge
from .driver.screen import Screen

log = logging.getLogger("spike")


def _dump_screen(screen: Screen, label: str) -> None:
    sys.stdout.write(f"\n========== {label} ==========\n")
    for row in screen.snapshot():
        sys.stdout.write(row.rstrip() + "\n")
    cr, cc = screen.cursor()
    sys.stdout.write(f"[cursor: row={cr} col={cc}]\n")
    sys.stdout.flush()


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    host = args.host or settings.bridge_host
    port = args.port or settings.bridge_port
    password = args.password or settings.panel_password
    pty_path = args.pty or settings.bridge_pty_path or ""

    raw_path = Path(args.raw_output)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_fh = raw_path.open("wb")

    screen = Screen()
    if pty_path:
        log.info("using PTY bridge: %s", pty_path)
        bridge: Bridge | PtyBridge = PtyBridge(pty_path)
    else:
        log.info("using TCP bridge: %s:%s", host, port)
        bridge = Bridge(host, port)

    def sink(data: bytes) -> None:
        raw_fh.write(data)
        raw_fh.flush()
        screen.feed(data)

    bridge.subscribe(sink)
    log.info("connecting to %s:%s", host, port)
    await bridge.start()

    try:
        # Step 1 — wake the terminal. Many serial devices wait for any input.
        await bridge.send(keys.ENTER)
        await asyncio.sleep(0.5)
        _dump_screen(screen, "after ENTER (wake)")

        # Step 2 — ESC a few times to back out of whatever half-state we're in.
        for _ in range(3):
            await bridge.send(keys.ESC)
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.5)
        _dump_screen(screen, "after ESC x3")

        # Step 3 — the CF Terminal uses lazy authentication: the "Password [  ]"
        # dialog appears the first time any menu key is pressed.  The 4-digit
        # password auto-submits on the 4th character (no Enter needed).
        # We do NOT try to authenticate at the Building Name screen.
        log.info("at idle screen — proceeding to navigation (login is lazy)")

        # Step 4 — log in, then navigate to Group Summary <group>.
        #
        # Login is lazy: the first G key press triggers a "Password [  ]" dialog
        # (centred, row 11).  The 4-digit password auto-submits on the 4th char —
        # no Enter needed.  After auto-submit the device returns to the Main Menu
        # with cursor on row ~14.
        #
        # G from cursor col 40 is REJECTED (BEL+CR) — wait for cursor col 0 first.
        log.info("waiting for idle screen to settle (cursor col 0)")
        await screen.wait_for(lambda s: s.cursor()[1] == 0, timeout=3.0)

        # Trigger Password dialog and log in.
        await bridge.send(keys.menu("G"))
        login_seen = await screen.wait_for(
            lambda s: "password" in s.text().lower(),
            timeout=2.0,
        )
        if login_seen and password:
            log.info("password prompt — entering password (auto-submit on 4th digit)")
            await bridge.send(keys.text(password))
            # Auto-submit: wait for dialog to clear AND cursor to leave row 11.
            await screen.wait_for(
                lambda s: "password" not in s.text().lower() and s.cursor()[0] != 11,
                timeout=4.0,
            )
            await asyncio.sleep(0.8)
            log.info("login complete: %s", screen.line(0).strip())
            _dump_screen(screen, "after login (Main Menu)")
        elif not password:
            log.warning("no password configured — navigation will likely fail")

        # Navigate from the Main Menu: G → Group Menu → S → Group Number field.
        # The Group Number field sits on the message line (row 22, col ~11).
        log.info("navigating G → S → %s → Enter", args.group)
        await bridge.send(keys.menu("G"))
        await asyncio.sleep(1.0)
        _dump_screen(screen, "after G (Group menu)")

        await bridge.send(keys.menu("S"))
        # Wait for the Group Number entry field to appear (cursor at row >= 20).
        await screen.wait_for(lambda s: s.cursor()[0] >= 20, timeout=3.0)
        _dump_screen(screen, "after S (Group Number prompt)")

        # Enter the group number.
        await bridge.send(keys.digits(args.group))
        await bridge.send(keys.ENTER)

        # Wait for Group Summary header ("For Group") then let the 10-second
        # auto-refresh tick populate the point rows.
        await screen.wait_for(
            lambda s: "for group" in s.text().lower(),
            timeout=5.0,
        )
        await asyncio.sleep(12.0)  # wait for at least one 10-second refresh
        _dump_screen(screen, f"Group Summary #{args.group} (after auto-refresh)")

        # Step 5 — back out to Main Menu so we leave the device in a known state.
        for _ in range(4):
            await bridge.send(keys.ESC)
            await asyncio.sleep(0.3)
        _dump_screen(screen, "after ESC x4 (back to Main Menu, hopefully)")
    finally:
        await bridge.stop()
        raw_fh.close()
        log.info("raw trace written to %s (%d bytes)", raw_path, raw_path.stat().st_size)

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 0 spike for Metasys CF Terminal.")
    parser.add_argument("--host", help="bridge TCP host (default: METASYS_BRIDGE_HOST)")
    parser.add_argument("--port", type=int, help="bridge TCP port (default: METASYS_BRIDGE_PORT)")
    parser.add_argument(
        "--pty",
        help="PTY device path, e.g. /tmp/metasys-pty (overrides TCP; default: METASYS_BRIDGE_PTY_PATH)",
    )
    parser.add_argument(
        "--password",
        help="Panel Unit password (default: METASYS_PANEL_PASSWORD)",
    )
    parser.add_argument("--group", type=int, default=1, help="group number to open (default: 1)")
    parser.add_argument(
        "--raw-output",
        default="logs/spike-raw.bin",
        help="where to write the raw byte stream (default: logs/spike-raw.bin)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
    )

    rc = asyncio.run(_run(args))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
