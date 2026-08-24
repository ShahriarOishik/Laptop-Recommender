from __future__ import annotations

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Injects the current request's correlation id into every log record
    emitted while handling that request, so lines from different concurrent
    requests can be told apart in the log stream."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [req:%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    # Replace rather than add — re-running configure_logging (e.g. in
    # tests that import main multiple times) shouldn't duplicate lines.
    root.handlers = [handler]
