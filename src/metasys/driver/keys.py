"""Keystroke byte sequences for the CF Terminal.

The Panel Unit is "VT100-compatible" (1990s-loose). These sequences are the
best-guess defaults; Phase 0 spike must confirm them against the real device
and this table updated if any differ.
"""

from __future__ import annotations

ENTER = b"\r"
ESC = b"\x1b"
TAB = b"\t"
BACKSPACE = b"\x08"
SPACE = b" "

# Arrow keys — VT100 cursor key mode (application). If the device uses the
# "normal" mode instead, these would be ESC [ A/B/C/D. Confirm in Phase 0.
UP = b"\x1bOA"
DOWN = b"\x1bOB"
RIGHT = b"\x1bOC"
LEFT = b"\x1bOD"

# Fall-backs if the device is in normal cursor mode instead of application mode.
UP_CSI = b"\x1b[A"
DOWN_CSI = b"\x1b[B"
RIGHT_CSI = b"\x1b[C"
LEFT_CSI = b"\x1b[D"

# Function keys — CF Terminal only uses F1..F4. VT100 PF1..PF4 are ESC O P/Q/R/S.
F1 = b"\x1bOP"  # Cancel
F2 = b"\x1bOQ"  # Save
F3 = b"\x1bOR"  # More / paginate
F4 = b"\x1bOS"  # Acknowledge alarm


def menu(letter: str) -> bytes:
    """Single-letter menu shortcut (e.g. 'G' from Main Menu to Group Menu)."""
    if len(letter) != 1:
        raise ValueError("menu letter must be a single character")
    return letter.upper().encode("ascii")


def digits(value: int) -> bytes:
    return str(int(value)).encode("ascii")


def text(value: str) -> bytes:
    return value.encode("ascii")
