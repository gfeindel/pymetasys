"""Screen parsers — turn a :class:`Screen` into structured records.

The manual (Figure 3-1, Table 3-1) specifies the point information format:

    [U] [*|T|S|X|O]  NNN NAME-16-CHARS  VALUE  UNITS  FLAGS

Where:

* ``U`` (column 0) — alarm unacknowledged. Blank if not.
* ``* T S X O`` (column 1) — point status. Blank if normal/online.
* ``NNN`` — 3-digit point number (right-justified, may be left-padded).
* ``NAME`` — 16-character point name.
* ``VALUE`` — analog value or binary state (e.g., ``Off``, ``70.0``).
* ``UNITS`` — engineering units (4 chars user-defined) or state text.
* ``FLAGS`` — feature-control / analog-status codes (``OV``, ``CL``, ``GD``,
  ``SS``, ``DL``, ``LR``, ``WS``, ``MC``, ``LO``, ``OR``, ``HI``).

The Group Summary lays these records out in two or three vertical columns
across the main area. Which column a record is in doesn't carry meaning; we
read rows left-to-right, columns left-to-right, and yield records in
point-number order.

Because exact column positions shift across firmware revisions and the
different features that may be enabled, this parser is permissive: it
extracts records by regex on full rows. Phase 0 traces will tell us whether
we need to pin positions more tightly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .screen import MAIN_AREA, MESSAGE_LINE, Screen

# ---- dataclasses ---------------------------------------------------------


@dataclass(frozen=True)
class PointRecord:
    """One row in a Group Summary or Point Summary."""

    number: int
    name: str
    value: str  # raw text as seen on screen — caller parses if numeric
    unacknowledged: bool = False
    status: str = ""  # '', '*', 'T', 'S', 'X', 'O'
    flags: tuple[str, ...] = ()  # e.g. ('OV', 'HI')

    @property
    def is_abnormal(self) -> bool:
        return self.status == "*"

    @property
    def is_offline(self) -> bool:
        return self.status == "X"

    @property
    def is_overridden(self) -> bool:
        return "OV" in self.flags or self.status == "O"


@dataclass(frozen=True)
class GroupInfo:
    """Group number + name from the List of Defined Groups."""

    number: int
    name: str


@dataclass(frozen=True)
class GroupSummary:
    number: int
    name: str
    points: tuple[PointRecord, ...]
    message: str = ""  # bottom-of-screen prompt/error


@dataclass(frozen=True)
class PointSummary:
    summary_type: str
    points: tuple[PointRecord, ...]
    has_more: bool = False


@dataclass(frozen=True)
class CommandFieldOptions:
    """The set of command types offered for the currently selected point.

    Per the manual (Table 4-1 referenced in Ch. 4):
      BO: Override, Auto, Command, Release
      AI/BI: Override, Auto
      AO: Override, Auto, Adjust
      AC: (not commandable)
    """

    point_number: int
    point_name: str
    types: tuple[str, ...] = field(default_factory=tuple)
    default_type: str = ""
    default_value: str = ""


# ---- regexes -------------------------------------------------------------

# One point record on a line. Tolerant of variable whitespace.
#
# Layout (columns 0..2 are status/unack, can be in either order, and either
# can be blank):
#   [U][*TSXO ] <num> <name(1..16)>  <value>[ units] [flags]
_POINT_RECORD = re.compile(
    r"""
    ^[ ]*                                          # leading spaces before the record
    (?P<prefix>[U*TSXO ]{0,2}?)                    # 0-2 status chars (unack / status)
    [ ]*
    (?P<num>\d{1,3})                               # point number
    [ ]+
    (?P<name>\S(?:.{0,14}\S)?)                     # 1-16 char name (no trailing spaces)
    \s{2,}                                         # 2+ space separator to value
    (?P<value>\S+(?:[ ]\S+)?)                      # value, optionally "1500.0 KW"
    (?:\s+(?P<flags>(?:OV|CL|GD|SS|DL|LR|WS|MC|LO|HI|OR)(?:\s+(?:OV|CL|GD|SS|DL|LR|WS|MC|LO|HI|OR))*))?
    """,
    re.VERBOSE,
)

# Group list row: "  1 Bldg Overview                  2 Chillers  ..."
# A group entry is "<num> <name>" where <name> ends at the first run of 2+
# spaces or end-of-line. Negative lookbehind prevents matching digits
# embedded in other tokens (e.g. "[ 1]" or the "1" inside "Floor 1").
_GROUP_ENTRY = re.compile(
    r"(?:^|(?<=\s{2}))\s*(\d{1,3})\s+([^\s\d][^\n]*?)(?=\s{2,}|\s*$)"
)


# ---- parsers -------------------------------------------------------------


def parse_point_row(row: str) -> PointRecord | None:
    """Parse a single screen row. Returns None if no point found."""
    m = _POINT_RECORD.match(row)
    if not m:
        # Try searching the row from any column — the Group Summary has
        # records in multiple columns on the same screen line.
        m = _POINT_RECORD.search(row)
        if not m:
            return None
    try:
        num = int(m.group("num"))
    except ValueError:
        return None

    prefix = m.group("prefix") or ""
    unack = "U" in prefix
    status = ""
    for ch in prefix:
        if ch in "*TSXO":
            status = ch
            break

    flags_raw = m.group("flags") or ""
    return PointRecord(
        number=num,
        name=m.group("name").rstrip(),
        value=m.group("value").strip(),
        unacknowledged=unack,
        status=status,
        flags=tuple(flags_raw.split()) if flags_raw else (),
    )


def parse_group_summary(screen: Screen) -> GroupSummary | None:
    """Extract group number, name, and point list from a Group Summary screen."""
    full = screen.text()
    # "For Group Number:    1 Bldg Overview"
    header = re.search(
        r"For Group Number:\s*(\d+)\s+(.+?)(?:\s{2,}|$)", full, re.MULTILINE
    )
    if not header:
        return None
    num = int(header.group(1))
    name = header.group(2).strip()

    points: list[PointRecord] = []
    for row in screen.text(MAIN_AREA).splitlines():
        # A row may contain multiple records (left column and right column).
        # Try to pull each one out by scanning the line repeatedly.
        start = 0
        while True:
            sub = row[start:]
            rec = parse_point_row(sub)
            if not rec:
                break
            points.append(rec)
            # Advance past this match. We only have the re.Match info if we
            # re-run, so use a simple progressive slice.
            m = _POINT_RECORD.search(sub)
            if not m or m.end() == 0:
                break
            start += m.end()

    message = screen.text(MESSAGE_LINE).strip()
    points.sort(key=lambda p: p.number)
    return GroupSummary(number=num, name=name, points=tuple(points), message=message)


def parse_group_list(screen: Screen) -> tuple[GroupInfo, ...]:
    """Extract all defined groups from the List of Defined Groups screen."""
    groups: dict[int, str] = {}
    for row in screen.text(MAIN_AREA).splitlines():
        for m in _GROUP_ENTRY.finditer(row):
            try:
                n = int(m.group(1))
            except ValueError:
                continue
            name = m.group(2).strip()
            # Filter out garbage: group numbers are 1..60 per the manual
            if 1 <= n <= 60 and name:
                groups.setdefault(n, name)
    return tuple(GroupInfo(number=n, name=groups[n]) for n in sorted(groups))


def parse_point_summary(screen: Screen) -> PointSummary | None:
    full = screen.text()
    header = re.search(r"Summary of\s+(.+?)\s{2,}", full)
    summary_type = header.group(1).strip() if header else "All Points"

    points: list[PointRecord] = []
    for row in screen.text(MAIN_AREA).splitlines():
        rec = parse_point_row(row)
        if rec:
            points.append(rec)

    has_more = "F3 More" in screen.text()
    return PointSummary(
        summary_type=summary_type, points=tuple(points), has_more=has_more
    )


def parse_message_line(screen: Screen) -> str:
    """Return the current content of the message line (prompt or error)."""
    return screen.text(MESSAGE_LINE).strip()


def parse_command_fields(screen: Screen) -> CommandFieldOptions | None:
    """Parse the command-field strip shown after selecting a point to command.

    Expected shape (Figure 4-2-ish):

        Point To Command 20 HW Setpoint
        ... group summary ...
        Command [ ]  Value [ ]        (actual labels vary by point type)

    Returns None if the command-field header can't be found.
    """
    full = screen.text()
    m = re.search(r"Point To Command\s+(\d+)\s+(.+?)\s{2,}", full)
    if not m:
        return None
    point_num = int(m.group(1))
    point_name = m.group(2).strip()

    types: list[str] = []
    for tok in ("Override", "Auto", "Command", "Release", "Adjust"):
        if f"{tok} [" in full or re.search(rf"\b{tok}\b\s*\[", full):
            types.append(tok)

    # Default type/value: look for the bracketed default on the command line.
    default_type = ""
    default_value = ""
    cmd_default = re.search(r"(Override|Auto|Command|Release|Adjust)\s*\[\s*([^\]]*)\]", full)
    if cmd_default:
        default_type = cmd_default.group(1)
        default_value = cmd_default.group(2).strip()

    return CommandFieldOptions(
        point_number=point_num,
        point_name=point_name,
        types=tuple(types),
        default_type=default_type,
        default_value=default_value,
    )
