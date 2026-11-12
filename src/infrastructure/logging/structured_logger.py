import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Any

from src.shared.clock import isoformat_utc, utcnow

#: The networking libraries' standard lines (httpx's ``HTTP Request: GET <URL> ...``, httpcore's connection lines) include the full URL.
#: Imported calendar URLs (Google private addresses, Outlook public URLs) expose the contents by themselves, so
#: nothing at INFO or below is emitted (task #495, ADR-0037). Error lines (WARNING and above) are kept.
QUIET_URL_LOGGERS = ("httpx", "httpcore")

_STDLIB_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        log: dict[str, Any] = {
            "timestamp": isoformat_utc(utcnow()),
            "level": record.levelname,
            "logger": record.name,
            "message": record.message,
        }
        for key, val in record.__dict__.items():
            if key not in _STDLIB_ATTRS and not key.startswith("_"):
                log[key] = val
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False, default=str)


def _make_rotating_handler(path: str) -> logging.handlers.TimedRotatingFileHandler:
    handler = logging.handlers.TimedRotatingFileHandler(
        filename=path,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        # Contract: logs are in UTC (HANDOVER §14). With the default utc=False, only the rollover and
        # the date in the file name follow the process TZ and drift from the timestamps inside.
        utc=True,
    )
    handler.setFormatter(StructuredFormatter())
    return handler


def setup_logging(level: str = "INFO", log_dir: str = "logs") -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    formatter = StructuredFormatter()
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(_make_rotating_handler(os.path.join(log_dir, "app.log")))

    # Separate access log – not propagated to root
    access = logging.getLogger("access")
    access.setLevel(logging.INFO)
    access.handlers.clear()
    access.addHandler(_make_rotating_handler(os.path.join(log_dir, "access.log")))
    access.propagate = False

    for name in QUIET_URL_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Suppress uvicorn's built-in access log (we handle it via middleware)
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False
