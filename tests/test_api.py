import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal
from app import models
from app.security import get_password_hash
from app.services import job_queue as jq_module


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def create_user(email: str, password: str, role: models.UserRole):
    session = SessionLocal()
    user = models.User(email=email, password_hash=get_password_hash(password), role=role)
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def test_login(client):
    create_user("user@example.com", "secret123", models.UserRole.user)
    resp = client.post("/api/auth/login", json={"email": "user@example.com", "password": "secret123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


def test_regex_endpoint(client):
    admin = create_user("admin@example.com", "secret123", models.UserRole.admin)
    token = client.post("/api/auth/login", json={"email": admin.email, "password": "secret123"}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/actions/test-regex",
        headers=headers,
        json={"sample_text": "Temp: 72F", "regex": r"Temp: (\\d+F)"},
    )
    assert resp.status_code == 200
    assert resp.json()["matches"]


def test_create_and_run_job(client, monkeypatch):
    admin = create_user("admin2@example.com", "secret123", models.UserRole.admin)
    token = client.post("/api/auth/login", json={"email": admin.email, "password": "secret123"}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}

    # Create action
    resp = client.post(
        "/api/actions",
        headers=headers,
        json={
            "name": "Check temp",
            "slug": "check-temp",
            "description": "Get temp",
            "input_sequence": "READ\n",
            "result_regex": r"Temp: (\\d+F)",
            "timeout_seconds": 1,
            "is_enabled": True,
        },
    )
    action_id = resp.json()["id"]

    # Mock serial response
    monkeypatch.setattr(jq_module.job_queue.serial_client, "execute_sequence", lambda *args, **kwargs: "Temp: 70F")

    job_resp = client.post(f"/api/actions/{action_id}/jobs", headers=headers)
    assert job_resp.status_code == 200
    job_id = job_resp.json()["id"]

    # Poll until finished
    for _ in range(20):
        detail = client.get(f"/api/jobs/{job_id}", headers=headers).json()
        if detail["status"] in ["succeeded", "failed"]:
            break
        time.sleep(0.1)

    assert detail["status"] == "succeeded"
    assert detail["parsed_result"] == "70F"
