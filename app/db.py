from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import settings
from .models import Base, User, ROLE_ADMIN
from .auth.security import hash_password

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

@contextmanager
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    with get_db_session() as db:
        existing = db.query(User).first()
        if existing:
            return
        admin = User(
            email=settings.default_admin_username,
            password_hash=hash_password(settings.default_admin_password),
            role=ROLE_ADMIN,
        )
        db.add(admin)
        db.commit()
