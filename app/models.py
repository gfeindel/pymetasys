from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

ROLE_ADMIN = "ADMIN"
ROLE_USER = "USER"

JOB_PENDING = "PENDING"
JOB_RUNNING = "RUNNING"
JOB_SUCCEEDED = "SUCCEEDED"
JOB_FAILED = "FAILED"

JOB_READ_GROUP = "READ_GROUP"
JOB_COMMAND_POINT = "COMMAND_POINT"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default=ROLE_USER)
    created_at = Column(DateTime, default=datetime.utcnow)

    jobs = relationship("Job", back_populates="created_by")

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    group_number = Column(Integer, unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    building = Column(String(255), nullable=True)
    floor = Column(String(255), nullable=True)

    points = relationship("Point", back_populates="group", cascade="all, delete-orphan")

class Point(Base):
    __tablename__ = "points"

    id = Column(Integer, primary_key=True)
    point_number = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    point_type = Column(String(50), nullable=True)
    read_only = Column(Boolean, default=False)
    allowed_operations = Column(JSON, nullable=True)
    unit = Column(String(50), nullable=True)
    last_value = Column(String(255), nullable=True)
    last_updated_at = Column(DateTime, nullable=True)

    group = relationship("Group", back_populates="points")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(50), nullable=False)
    payload_json = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default=JOB_PENDING)
    result_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    created_by = relationship("User", back_populates="jobs")
