from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool
from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    if settings.database_url == "sqlite:///:memory:":
        engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(settings.database_url, connect_args=connect_args)
else:
    engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
