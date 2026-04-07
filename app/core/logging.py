"""
Structured JSON Logging — Week 5

Configures the application-wide logger to output structured JSON lines.
Each log entry includes:
  • timestamp (ISO 8601, UTC)
  • level
  • logger name
  • message
  • module / function / line
  • extra context (request_id, card_id, etc.)

Usage:
    from app.core.logging import setup_logging
    setup_logging()   # Call once at application startup
"""
import logging
import json
import sys
from datetime import datetime, timezone


class StructuredJsonFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include any extra fields passed via `logger.info("msg", extra={...})`
        for key in ("request_id", "card_id", "user_id", "statement_id", "payment_id"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """
    Configure root logger + all zbanque.* loggers with structured JSON output.
    """
    formatter = StructuredJsonFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers = []
    root_logger.addHandler(console_handler)

    # Application loggers
    for logger_name in (
        "zbanque",
        "zbanque.billing",
        "zbanque.payments",
        "zbanque.fraud",
        "zbanque.idempotency",
        "zbanque.jobs",
    ):
        app_logger = logging.getLogger(logger_name)
        app_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        app_logger.propagate = True

    # Quiet noisy libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # apscheduler removed — using asyncio-native scheduler

    root_logger.info("Structured JSON logging initialized (level=%s)", level)
