"""Runtime configuration, read from env / .env."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AlarmPriority(str, Enum):
    CRITICAL = "CRITICAL"
    NETWORK = "NETWORK"
    FOLLOWUP = "FOLLOWUP"
    STATUS = "STATUS"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="METASYS_",
        extra="ignore",
    )

    # Bridge
    bridge_host: str = "127.0.0.1"
    bridge_port: int = 4001

    # Device auth
    panel_password: str = ""

    # Web
    secret_key: str = "dev-only-change-me"
    database_url: str = "sqlite+aiosqlite:///./metasys.db"
    host: str = "0.0.0.0"
    port: int = 8000

    # Driver timing
    settle_timeout: float = 2.0
    settle_quiet_ms: int = 150
    reconnect_min: float = 1.0
    reconnect_max: float = 30.0

    # Alarm behavior — priorities strictly below this value auto-ack.
    # CRITICAL means nothing auto-acks (require human); STATUS means all auto-ack.
    alarm_autoack_below: AlarmPriority = AlarmPriority.CRITICAL

    # Polling
    poll_interval: float = 10.0

    # Manual terminal session limit
    manual_session_seconds: int = 600
    manual_warn_seconds: int = 480


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
