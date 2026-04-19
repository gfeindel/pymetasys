"""Phase 1 CLI harness — smoke-test the Driver against the live device.

Exercises the full Driver stack (login, navigation FSM, parsers) and prints
structured results. Use this to validate that Phase 1 works end-to-end before
wiring up the web app.

Usage::

    python -m metasys.harness               # uses .env defaults
    python -m metasys.harness --group 7     # read a specific group
    python -m metasys.harness --all-groups  # read every defined group
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time

from .config import get_settings
from .driver.bridge import Bridge, PtyBridge
from .driver.driver import Driver
from .driver.screen import Screen
from .driver.states import detect_state

log = logging.getLogger("harness")


def _hr(label: str = "") -> None:
    w = 70
    if label:
        pad = (w - len(label) - 2) // 2
        print(f"\n{'─' * pad} {label} {'─' * (w - pad - len(label) - 2)}")
    else:
        print("─" * w)


def _print_group_summary(gs) -> None:
    print(f"  Group {gs.number}: {gs.name}")
    if not gs.points:
        print("    (no points — auto-refresh not yet ticked)")
        return
    for p in gs.points:
        flags = " ".join(p.flags) if p.flags else ""
        status_str = f"[{p.status}]" if p.status else ""
        unack = "U" if p.unacknowledged else " "
        print(
            f"    {unack} {p.number:3d}  {p.name:<20s}  {p.value:<12s}  "
            f"{status_str:<4s}  {flags}"
        )


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    host = args.host or settings.bridge_host
    port = args.port or settings.bridge_port
    pty_path = args.pty or settings.bridge_pty_path or ""

    screen = Screen()
    if pty_path:
        log.info("using PTY bridge: %s", pty_path)
        bridge: Bridge | PtyBridge = PtyBridge(pty_path)
    else:
        log.info("using TCP bridge: %s:%s", host, port)
        bridge = Bridge(host, port)

    driver = Driver(bridge, screen, settings)
    bridge.subscribe(screen.feed)

    log.info("connecting …")
    await bridge.start()
    await bridge.wait_connected()

    try:
        # ── 1. Connect + login ────────────────────────────────────────────
        _hr("connect + login")
        t0 = time.monotonic()
        await driver.goto_main_menu()
        elapsed = time.monotonic() - t0
        state_after = detect_state(screen)
        print(f"  goto_main_menu() → {state_after.name}  ({elapsed:.2f}s)")
        if state_after.name != "MAIN_MENU":
            print("  ERROR: not at Main Menu after recovery — aborting")
            return 1
        print("  Row 0:", screen.line(0).rstrip())

        # ── 2. Group list ─────────────────────────────────────────────────
        _hr("group list")
        t0 = time.monotonic()
        groups = await driver.read_group_list()
        elapsed = time.monotonic() - t0
        print(f"  read_group_list() → {len(groups)} groups  ({elapsed:.2f}s)")
        for g in groups:
            print(f"    {g.number:3d}  {g.name}")

        # Return to Main Menu to verify back-navigation works.
        await driver.goto_main_menu()
        print(f"  back to Main Menu → {detect_state(screen).name}")
        print(f"  goto_main_menu() after group list → {detect_state(screen).name}")

        # ── 3. Group summary ──────────────────────────────────────────────
        target_groups = [args.group] if args.group else ([g.number for g in groups] if args.all_groups else [])
        if not target_groups and groups:
            # Default: first group with a name that looks like it has points.
            target_groups = [groups[0].number]

        for gn in target_groups:
            _hr(f"group summary #{gn}")
            t0 = time.monotonic()
            gs = await driver.read_group_summary(gn)
            elapsed = time.monotonic() - t0

            if not gs.points:
                # Wait for one auto-refresh tick.
                print(f"  no points yet — waiting up to 12s for auto-refresh …")
                await screen.wait_for(
                    lambda s: any(
                        str(p.number) in s.text() for p in (gs.points or [])
                    ) or True,  # re-parse after wait
                    timeout=12.0,
                )
                await asyncio.sleep(12.0)
                from .driver.parsers import parse_group_summary
                gs2 = parse_group_summary(screen)
                if gs2 and gs2.points:
                    gs = gs2
            elapsed = time.monotonic() - t0
            print(f"  read_group_summary({gn}) → {len(gs.points)} points  ({elapsed:.2f}s)")
            _print_group_summary(gs)

            # Back to Main Menu before the next iteration.
            await driver.goto_main_menu()
            print(f"  back to Main Menu → {detect_state(screen).name}")

        # ── 4. Recovery smoke-test ─────────────────────────────────────────
        _hr("recovery from Group Summary")
        # Navigate into a group summary, then call goto_main_menu() to test
        # that F1-based recovery works.
        if groups:
            gn = (args.group or groups[0].number)
            await driver.goto_group_summary(gn)
            print(f"  landed on: {detect_state(screen).name}")
            t0 = time.monotonic()
            await driver.goto_main_menu()
            elapsed = time.monotonic() - t0
            print(f"  recovered to: {detect_state(screen).name}  ({elapsed:.2f}s)")

        _hr("PASSED")
        return 0

    except Exception:
        log.exception("harness failed")
        return 1
    finally:
        await driver.stop()
        await bridge.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 Driver harness.")
    parser.add_argument("--host", help="bridge TCP host")
    parser.add_argument("--port", type=int, help="bridge TCP port")
    parser.add_argument("--pty", help="PTY device path (overrides TCP)")
    parser.add_argument("--group", type=int, help="group number to read")
    parser.add_argument("--all-groups", action="store_true", help="read every defined group")
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
