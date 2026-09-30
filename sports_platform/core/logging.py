"""
Structured JSON logging formatter.
All application logs are emitted as JSON for easy ingestion by Loki / CloudWatch.
"""
import json
import logging
import traceback
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Standard fields:
      timestamp, level, logger, message, module, lineno
    Optional fields (when present):
      exc_info, request_id, user_id, match_id, trace_id
    """

    def format(self, record: logging.LogRecord) -> str:
        log_object: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "lineno": record.lineno,
            "message": record.getMessage(),
        }

        # Include contextual fields if attached to the record
        for field in ("request_id", "user_id", "match_id", "trace_id", "service"):
            value = getattr(record, field, None)
            if value is not None:
                log_object[field] = value

        # Include exception traceback if present
        if record.exc_info:
            log_object["exc_info"] = self.formatException(record.exc_info)

        # Include extra fields attached via logger.info(..., extra={...})
        standard_keys = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "request_id", "user_id", "match_id", "trace_id", "service",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in standard_keys:
                log_object[key] = value

        return json.dumps(log_object, default=str)
