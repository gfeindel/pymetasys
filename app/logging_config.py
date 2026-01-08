import logging
import json
from logging.handlers import RotatingFileHandler
from .config import settings

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
            "time": self.formatTime(record, self.datefmt),
        }
        if record.__dict__.get("job_id") is not None:
            payload["job_id"] = record.__dict__["job_id"]
        if record.__dict__.get("user_id") is not None:
            payload["user_id"] = record.__dict__["user_id"]
        if record.__dict__.get("event") is not None:
            payload["event"] = record.__dict__["event"]
        return json.dumps(payload)


def configure_logging():
    logger = logging.getLogger()
    logger.setLevel(settings.log_level.upper())

    formatter = JsonFormatter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(settings.log_file, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
