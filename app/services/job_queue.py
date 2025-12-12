import threading
import queue
import re
from datetime import datetime
from typing import Callable
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.database import SessionLocal
from app.services.serial_client import SerialClient
from app.services.regex_utils import normalize_pattern


class InMemoryJobQueue:
    """
    Simple FIFO queue with a single worker thread to ensure serial exclusivity.
    """

    def __init__(self, db_factory: Callable[[], Session], serial_client: SerialClient):
        self.db_factory = db_factory
        self.serial_client = serial_client
        self.queue: queue.Queue[int] = queue.Queue()
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._started = False

    def start(self):
        if not self._started:
            self.worker_thread.start()
            self._started = True

    def enqueue(self, job_id: int):
        self.queue.put(job_id)

    def _worker(self):
        while True:
            job_id = self.queue.get()
            try:
                self._process_job(job_id)
            except Exception as exc:  # pragma: no cover - defensive
                print(f"Job {job_id} failed with unhandled error: {exc}")
            finally:
                self.queue.task_done()

    def _process_job(self, job_id: int):
        db = self.db_factory()
        try:
            job = db.query(models.ActionJob).filter(models.ActionJob.id == job_id).first()
            if not job:
                return
            action = job.action_definition
            if not action or not action.is_enabled:
                job.status = models.JobStatus.failed
                job.error_message = "Action disabled or missing"
                job.finished_at = datetime.utcnow()
                db.commit()
                return

            job.status = models.JobStatus.running
            job.started_at = datetime.utcnow()
            job.raw_request_payload = action.input_sequence
            db.commit()

            timeout = action.timeout_seconds or get_settings().serial_timeout
            try:
                raw_response = self.serial_client.execute_sequence(action.input_sequence, timeout=timeout)
                job.raw_response = raw_response
            except TimeoutError:
                job.status = models.JobStatus.timeout
                job.error_message = "Timed out waiting for device response"
                job.finished_at = datetime.utcnow()
                db.commit()
                return
            except Exception as serial_exc:
                job.status = models.JobStatus.failed
                job.error_message = f"Serial error: {serial_exc}"
                job.finished_at = datetime.utcnow()
                db.commit()
                return

            parsed = None
            try:
                pattern = normalize_pattern(action.result_regex)
                match = re.search(pattern, raw_response, re.MULTILINE)
                if match:
                    if match.groupdict():
                        parsed = next(iter(match.groupdict().values()))
                    elif match.groups():
                        parsed = match.group(1)
                    else:
                        parsed = match.group(0)
                if parsed is None:
                    job.status = models.JobStatus.failed
                    job.error_message = "No regex match found"
                else:
                    job.parsed_result = parsed
                    job.status = models.JobStatus.succeeded
            except re.error as regex_err:
                job.status = models.JobStatus.failed
                job.error_message = f"Regex error: {regex_err}"

            job.finished_at = datetime.utcnow()
            db.commit()
        except Exception as exc:
            # Defensive catch-all to avoid stuck queue
            job_record = db.query(models.ActionJob).filter(models.ActionJob.id == job_id).first()
            if job_record:
                job_record.status = models.JobStatus.failed
                job_record.error_message = str(exc)
                job_record.finished_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()


serial_client = SerialClient()
job_queue = InMemoryJobQueue(SessionLocal, serial_client)
