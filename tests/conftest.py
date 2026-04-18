"""Shared test fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the src/ layout importable without installing.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Required by config; give any non-empty values so get_settings() doesn't
# read a stray .env from the dev machine.
os.environ.setdefault("METASYS_BRIDGE_HOST", "127.0.0.1")
os.environ.setdefault("METASYS_BRIDGE_PORT", "4001")
os.environ.setdefault("METASYS_PANEL_PASSWORD", "test-password")
os.environ.setdefault("METASYS_SECRET_KEY", "test-secret-key-123456")
os.environ.setdefault("METASYS_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
