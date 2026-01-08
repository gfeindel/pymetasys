import json
import logging
import time
from datetime import datetime
from sqlalchemy.orm import Session
from ..config import settings
from ..db import get_db_session
from ..logging_config import configure_logging
from ..models import (
    JOB_COMMAND_POINT,
    JOB_FAILED,
    JOB_READ_GROUP,
    JOB_SUCCEEDED,
    Point,
    Job,
)
from ..terminal.driver import TerminalDriver
from .queue import claim_next_job

logger = logging.getLogger(__name__)


def _handle_read_group(db: Session, driver: TerminalDriver, job: Job) -> dict:
    group_number = job.payload_json.get("group_number")
    result = driver.read_group_values(group_number)
    points = result.get("points", [])
    for point in points:
        if point.point_number is None:
            continue
        db_point = (
            db.query(Point)
            .filter(Point.group_id == job.payload_json.get("group_id"))
            .filter(Point.point_number == point.point_number)
            .first()
        )
        if db_point:
            db_point.last_value = point.value
            db_point.last_updated_at = datetime.utcnow()
    db.commit()
    result["points"] = [p.__dict__ for p in points]
    return result


def _handle_command_point(db: Session, driver: TerminalDriver, job: Job) -> dict:
    payload = job.payload_json
    point = db.query(Point).filter(Point.id == payload.get("point_id")).first()
    old_value = point.last_value if point else None
    result = driver.command_point(
        payload.get("group_number"),
        payload.get("point_number"),
        payload.get("command_type"),
        payload.get("command_value"),
    )
    result.update(
        {
            "point_id": payload.get("point_id"),
            "old_value": old_value,
            "command_value": payload.get("command_value"),
        }
    )
    logger.info(
        "command_executed point_id=%s old_value=%s new_value=%s raw=%s",
        payload.get("point_id"),
        old_value,
        payload.get("command_value"),
        result.get("raw_screen"),
        extra={"event": "command_executed", "job_id": job.id, "user_id": job.created_by_user_id},
    )
    return result


def run_worker():
    configure_logging()
    driver = TerminalDriver()
    logger.info("worker_start", extra={"event": "worker_start"})
    while True:
        with get_db_session() as db:
            job = claim_next_job(db)
            if not job:
                time.sleep(settings.worker_poll_interval)
                continue
            logger.info("job_claimed", extra={"event": "job_claimed", "job_id": job.id, "user_id": job.created_by_user_id})
            try:
                if job.type == JOB_READ_GROUP:
                    result = _handle_read_group(db, driver, job)
                elif job.type == JOB_COMMAND_POINT:
                    result = _handle_command_point(db, driver, job)
                else:
                    raise ValueError(f"Unknown job type: {job.type}")
                job.result_json = result
                job.status = JOB_SUCCEEDED
                job.finished_at = datetime.utcnow()
                db.commit()
                logger.info("job_succeeded", extra={"event": "job_succeeded", "job_id": job.id, "user_id": job.created_by_user_id})
            except Exception as exc:
                job.status = JOB_FAILED
                job.error = str(exc)
                job.finished_at = datetime.utcnow()
                db.commit()
                logger.exception("job_failed", extra={"event": "job_failed", "job_id": job.id, "user_id": job.created_by_user_id})
        time.sleep(0.1)


if __name__ == "__main__":
    run_worker()
