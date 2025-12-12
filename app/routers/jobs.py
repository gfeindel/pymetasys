from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.dependencies import get_current_user, get_db, require_admin
from app.services.job_queue import job_queue

router = APIRouter(prefix="/api", tags=["jobs"])


@router.post("/actions/{action_id}/jobs", response_model=schemas.ActionJobOut)
def create_job(
    action_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    action = db.query(models.ActionDefinition).filter(models.ActionDefinition.id == action_id).first()
    if not action or (not action.is_enabled and current_user.role != models.UserRole.admin):
        raise HTTPException(status_code=404, detail="Action not found")

    job = models.ActionJob(
        action_definition_id=action.id,
        requested_by_user_id=current_user.id,
        status=models.JobStatus.queued,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    job_queue.enqueue(job.id)

    return job


@router.get("/jobs", response_model=list[schemas.ActionJobOut])
def list_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    status_filter: str | None = None,
):
    query = db.query(models.ActionJob)
    if current_user.role != models.UserRole.admin:
        query = query.filter(models.ActionJob.requested_by_user_id == current_user.id)
    if status_filter:
        query = query.filter(models.ActionJob.status == status_filter)
    return query.order_by(models.ActionJob.created_at.desc()).limit(100).all()


@router.get("/jobs/{job_id}", response_model=schemas.ActionJobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    job = db.query(models.ActionJob).filter(models.ActionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if current_user.role != models.UserRole.admin and job.requested_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return job
