"""Screen fixture helpers for tests.

We synthesize pyte-compatible byte streams by writing plain text into a
known 24x80 grid. Once Phase 0 captures real device traces, replace these
synthesized fixtures with the actual bytes so tests run against real data.
"""

from __future__ import annotations

from typing import Iterable

CLEAR = b"\x1b[2J\x1b[H"


def layout(rows: Iterable[str]) -> bytes:
    """Produce a byte stream that clears the screen and places each row.

    Rows are written with ``ESC [ r ; 1 H`` cursor-position sequences so
    pyte puts them at the expected row.
    """
    out = bytearray(CLEAR)
    for idx, row in enumerate(rows, start=1):
        out += f"\x1b[{idx};1H".encode("ascii")
        out += row.ljust(80)[:80].encode("ascii", errors="replace")
    return bytes(out)


MAIN_MENU_ROWS = [
    "Operator Name: J. Smith                                   Thu Jan 8, 1998 14:40",
    "",
    "-" * 80,
    "",
    "                        Main Function Menu",
    "",
    "                        Group",
    "                        Point",
    "                        Data Trend",
    "                        Weekly Scheduling",
    "                        Totalization",
    "                        Energy Management",
    "                        Control Logic",
    "                        Network",
    "                        Reports",
    "                        System Setup",
    "                        Quit",
    "",
    "",
    "",
    "",
    "",
    "",
    "F1 Cancel                                                       ",
]


GROUP_MENU_ROWS = [
    "Operator Name: J. Smith                                   Thu Jan 8, 1998 14:40",
    "",
    "-" * 80,
    "",
    "                        Group Menu",
    "",
    "                        Summary",
    "                        Modify/Add/Delete",
    "                        Graphics",
    "                        Return to Main Menu",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "F1 Cancel",
]


GROUP_LIST_ROWS = [
    "Operator Name: J. Smith                                   Thu Jan 8, 1998 14:40",
    "",
    "-" * 80,
    "                                                                Group Summary",
    "",
    "Group Number [ 1]                 List Of Defined Groups   3 Floor 1 Status",
    "                                                           6 Exhaust Fans",
    "   1 Bldg Overview                    2 Chillers           9 LCP 05 BD POINTS",
    "   4 AHU1 Status                      5 Lighting Zones    12 N2 Dialer NDM127",
    "   7 MARKS GROUP                      8 Doug's Group      15 15",
    "  10 TC11 BI                         11 TC 11              18 UNT 18",
    "  13 dave's group                    14 VAV 06 GROUP       21 DX21",
    "  16 16                              17 17                 24 Doug's Group",
    "  19 Fire Group 19                   20 20                 27 27",
    "  22 DX21 XT1,2,3,4                  23 DX21 POINTS        30 30",
    "  25 25                              26 26",
    "  28 28                              29 29",
    "",
    "",
    "",
    "",
    "",
    "F1 Cancel                F3 More",
    "Select a group by number (1 - 60)",
]


GROUP_SUMMARY_ROWS = [
    "Operator Name: J. Smith                                 Thu Jan 8, 1998 14:42",
    "",
    "-" * 80,
    "Point To Command [ ]",
    "",
    "For Group Number:        1 Bldg Overview",
    "",
    "  1 ACM BI7 AHU255  1500.0 KW     2 AHU9 ACM BI----8  70.0 CFSS",
    "  3 DX21 PMA1       1500.0 KW     4 LCP-1 AI2         0.0 %",
    "  5 LCP-1 AI3       69.0 Deg      6 LCP-1 AI4         70.0 Deg",
    "  7 LCP 01 AI5      61.0 Deg      8 DX21 ADI2         1500.0 KW",
    "* 9 LCP-1 BI2       Off          10 LCP-1 BI3         Off",
    " 11 LCP-1 BI4 stat  Off          12 LCP-1 BI5 stat    Off",
    " 13 LCP-1 BI6 CRIT  Off          14 LCP-1 BI BD5      Off",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "F1 Cancel                 F3 More",
    "Select a point to command (1 - 799)",
]


POINT_MENU_ROWS = [
    "Operator Name: J. Smith                                 Thu Jan 8, 1998 14:42",
    "",
    "-" * 80,
    "",
    "                        Point Menu",
    "",
    "                        Summary",
    "                        Override Or Command",
    "                        Modify Point",
    "                        Add Point",
    "                        Delete Point",
    "                        Copy Controller Points",
    "                        List Of Alarm Messages",
    "                        Return to Main Menu",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "F1 Cancel",
]


LOGIN_ROWS = [
    "",
    "",
    "",
    "",
    "                            Johnson Controls Metasys Panel Unit",
    "",
    "                            Press any key to log on",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
]


PASSWORD_ROWS = [
    "",
    "",
    "",
    "",
    "                            Password: [              ]",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
]


CRITICAL_ALARM_ROWS = [
    "Operator Name: J. Smith                                 Thu Jan 8, 1998 14:42",
    "  CRITICAL ALARM: Point 9 LCP-1 BI2 Off at 14:41:50",
    "-" * 80,
    "Point To Command [ ]",
    "",
    "For Group Number:        1 Bldg Overview",
    "",
    "  1 ACM BI7 AHU255  1500.0 KW     2 AHU9 ACM BI----8  70.0 CFSS",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "",
    "F1 Cancel  F4 Acknow",
]
