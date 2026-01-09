import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass
from dataclasses import dataclass

def _get_int(name, default):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default

def _get_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

@dataclass
class Settings:
    app_secret_key: str = os.getenv("APP_SECRET_KEY", "change-me")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")

    default_admin_username: str = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
    default_admin_password: str = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin")

    serial_port: str = os.getenv("SERIAL_PORT", "/dev/ttyUSB0")
    serial_baud: int = _get_int("SERIAL_BAUD", 9600)
    serial_timeout: float = float(os.getenv("SERIAL_TIMEOUT", "1.0"))
    serial_write_timeout: float = float(os.getenv("SERIAL_WRITE_TIMEOUT", "1.0"))
    serial_bytesize: int = _get_int("SERIAL_BYTESIZE", 8)
    serial_parity: str = os.getenv("SERIAL_PARITY", "N")
    serial_stopbits: int = _get_int("SERIAL_STOPBITS", 1)

    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_file: str = os.getenv("LOG_FILE", "./app.log")
    log_debug_screens: bool = _get_bool("LOG_DEBUG_SCREENS", False)

    worker_poll_interval: float = float(os.getenv("WORKER_POLL_INTERVAL", "1.0"))
    terminal_main_menu_hint: str = os.getenv("TERMINAL_MAIN_MENU_HINT", "Main Menu")
    terminal_login_hint: str = os.getenv("TERMINAL_LOGIN_HINT", "Password")
    terminal_login_password: str = os.getenv("TERMINAL_LOGIN_PASSWORD", "")

settings = Settings()
