import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Any

from src.shared.clock import isoformat_utc, utcnow

#: 通信の道具の標準の行（httpx の ``HTTP Request: GET <URL> ...``・httpcore の接続の行）は URL を丸ごと載せる。
#: 取り込んだカレンダーの URL（Google の非公開アドレス・Outlook の公開 URL）はそれだけで中身が読めるので、
#: INFO 以下は出さない（task #495・ADR-0037）。誤りの行（WARNING 以上）は残す。
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
        # 契約: ログは UTC（HANDOVER §14）。既定の utc=False だと切り替えと
        # ファイル名の日付だけがプロセスの TZ になり、中身の timestamp とずれる。
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
