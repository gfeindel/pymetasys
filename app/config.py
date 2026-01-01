from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "Building Control API"
    database_url: str = Field("sqlite:///./db.sqlite3", alias="DATABASE_URL")
    redis_url: str | None = Field(None, alias="REDIS_URL")

    jwt_secret: str = Field("changeme", alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(60 * 12, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    serial_port: str = Field("COM1", alias="SERIAL_PORT")
    serial_baudrate: int = Field(9600, alias="SERIAL_BAUDRATE")
    serial_timeout: float = Field(3.0, alias="SERIAL_TIMEOUT")
    serial_password: str = Field("0000", alias="SERIAL_PASSWORD")
    serial_xonxoff: bool = Field(False, alias="SERIAL_XONXOFF")
    serial_rtscts: bool = Field(False, alias="SERIAL_RTSCTS")
    serial_write_timeout: float | None = Field(None, alias="SERIAL_WRITE_TIMEOUT")

    admin_bootstrap_email: str | None = Field(None, alias="ADMIN_EMAIL")
    admin_bootstrap_password: str | None = Field(None, alias="ADMIN_PASSWORD")
    allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"])

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
