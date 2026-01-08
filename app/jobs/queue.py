from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Job, JOB_PENDING


def create_job(db: Session, created_by_user_id: int, job_type: str, payload: dict) -> Job:
    job = Job(
        created_by_user_id=created_by_user_id,
        type=job_type,
        payload_json=payload,
        status=JOB_PENDING,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next_job(db: Session) -> Job | None:
    job = (
        db.query(Job)
        .filter(Job.status == JOB_PENDING)
        .order_by(Job.created_at.asc())
        .first()
    )
    if not job:
        return None
    job.status = JOB_RUNNING
    job.started_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job
