"""Screen states and recognizers for the CF Terminal FSM.

A "state" is the identity of whatever screen the Panel Unit is currently
displaying. Each state has a recognizer — a cheap predicate over the current
:class:`~metasys.driver.screen.Screen` — and optionally a canonical target
row/column on which we pin the recognizer so we can anchor-wait on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from .screen import Screen


class State(Enum):
    UNKNOWN = auto()
    LOGIN_PROMPT = auto()  # "Press any key to log on" / "Password:"
    MAIN_MENU = auto()
    GROUP_MENU = auto()
    GROUP_LIST = auto()  # Group Number [ ] prompt with defined-groups list
    GROUP_SUMMARY = auto()
    POINT_MENU = auto()
    POINT_SUMMARY_SELECT = auto()  # Point Number [ ] + Summary Type [ ]
    POINT_SUMMARY = auto()
    POINT_OVERRIDE = auto()  # P→O: Point To Command [ ]
    POINT_COMMAND_FIELDS = auto()  # After point# entered, command type/value fields
    MANUAL = auto()  # passthrough mode — FSM not tracking


Recognizer = Callable[[Screen], bool]


@dataclass(frozen=True)
class StateSpec:
    state: State
    recognizer: Recognizer
    # A human-readable anchor string we expect somewhere on the screen when
    # this state is settled. Used for logging.
    anchor_hint: str = ""


# --- Recognizers ----------------------------------------------------------
#
# These are deliberately loose matchers — anchor strings at flexible positions
# — because the device's exact spacing and column positions vary across
# firmware revisions. Once Phase 0 captures real traces, tighten the
# coordinates that matter.


def _has(s: Screen, *needles: str) -> bool:
    return all(s.contains(n) for n in needles)


def is_login_prompt(s: Screen) -> bool:
    text = s.text().lower()
    return "password" in text or "press any key" in text or "log on" in text


def is_main_menu(s: Screen) -> bool:
    # Main menu lists: Group, Point, Data Trend, Weekly Scheduling,
    # Totalization, Energy Management, Control Logic, Network, Reports,
    # System Setup, Quit.
    return _has(s, "Group", "Point") and (
        _has(s, "Data Trend") or _has(s, "Weekly Scheduling") or _has(s, "System Setup")
    )


def is_group_menu(s: Screen) -> bool:
    # Group menu: Summary, Modify/Add/Delete, Return to Main Menu.
    # "Modify/Add/Delete" is unique to the Group Menu (Point Menu uses
    # separate "Modify Point" / "Add Point" items).
    text = s.text()
    if "Modify/Add/Delete" not in text:
        return False
    if "Summary" not in text:
        return False
    # Not a Group Summary (which has "Point To Command").
    if "Point To Command" in text:
        return False
    # Not on Main Menu (which has "System Setup").
    if "System Setup" in text:
        return False
    return True


def is_group_list(s: Screen) -> bool:
    # "Group Number [" prompt + "List Of Defined Groups" header.
    text = s.text()
    return "Group Number [" in text and "List Of Defined Groups" in text


def is_group_summary(s: Screen) -> bool:
    text = s.text()
    return "Point To Command" in text and "For Group Number" in text


def is_point_menu(s: Screen) -> bool:
    text = s.text()
    return (
        "Override Or Command" in text
        and "Modify Point" in text
        and "Add Point" in text
    )


def is_point_summary_select(s: Screen) -> bool:
    text = s.text()
    return (
        "Point Number [" in text
        and "Summary Type [" in text
        and "List Of Summary Types" in text
    )


def is_point_summary(s: Screen) -> bool:
    text = s.text()
    return "Summary of" in text and "Software" in text and "Controller" in text


def is_point_override(s: Screen) -> bool:
    # P→O lands on a Group Summary view with "Point To Command [" field ready.
    # After entering the point#, command fields become visible.
    text = s.text()
    return "Point To Command" in text and "For Group Number" in text


def is_command_fields(s: Screen) -> bool:
    # After a point is selected for commanding: "Point To Command <n> <name>"
    # (no brackets — point number + name are filled in) AND a command-type
    # field like "Override [ ]" / "Auto [ ]" / "Adjust [ ]" / "Release [ ]"
    # appears. We deliberately avoid matching bare "Command [" because it
    # collides with "Point To Command [" on a bare Group Summary.
    text = s.text()
    import re as _re

    if not _re.search(r"Point To Command\s+\d+\s+\S", text):
        return False
    return any(
        token in text
        for token in ("Override [", "Auto [", "Release [", "Adjust [")
    )


SPECS: tuple[StateSpec, ...] = (
    StateSpec(State.LOGIN_PROMPT, is_login_prompt, "Password / Press any key"),
    StateSpec(State.POINT_COMMAND_FIELDS, is_command_fields, "Command [ ] / Override [ ]"),
    StateSpec(State.GROUP_SUMMARY, is_group_summary, "For Group Number:"),
    StateSpec(State.POINT_OVERRIDE, is_point_override, "Point To Command [ ]"),
    StateSpec(State.GROUP_LIST, is_group_list, "List Of Defined Groups"),
    StateSpec(State.POINT_SUMMARY_SELECT, is_point_summary_select, "List Of Summary Types"),
    StateSpec(State.POINT_SUMMARY, is_point_summary, "Summary of ..."),
    StateSpec(State.POINT_MENU, is_point_menu, "Override Or Command / Modify Point"),
    StateSpec(State.GROUP_MENU, is_group_menu, "Summary / Modify-Add-Delete / Graphics"),
    StateSpec(State.MAIN_MENU, is_main_menu, "Main Menu"),
)


def detect_state(screen: Screen) -> State:
    """Cheap, heuristic state detector. Order matters — specific before general.

    Returns :attr:`State.UNKNOWN` if nothing matches. ``UNKNOWN`` is the
    trigger for the driver's recovery escape-hatch.
    """
    for spec in SPECS:
        try:
            if spec.recognizer(screen):
                return spec.state
        except Exception:  # noqa: BLE001 — defensive, never trust pyte output
            continue
    return State.UNKNOWN
