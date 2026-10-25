"""Central logging (ARCHITECTURE §12).

Library modules only do ``log = logging.getLogger(__name__)``. The CLI / controller calls
``configure()`` once; it installs a console handler and, optionally, a JSON-lines file that records
everything. ``log_context()`` attaches run/phase/track/tile/step to every record emitted inside it,
``file_log()`` adds a plain-text log file for the duration of a phase, and ``event()`` emits a
structured event (``phase_start``, ``phase_end``, ``progress``, ``metric`` ...) that progress and
timing summaries are derived from.
"""
from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CONTEXT_KEYS = ("run_id", "phase", "track", "tile", "step")

_CTX: ContextVar[dict[str, Any]] = ContextVar("geoeyes_log_context", default={})  # noqa: B039 - never mutated
_STD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}
_OWNED = "_geoeyes_handler"


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    """Attach fields (``run_id``, ``phase``, ``track``, ``tile``, ``step`` or any other) to every
    record logged inside the block; nests, inner values win."""
    token = _CTX.set({**_CTX.get(), **{k: v for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _CTX.reset(token)


def current_context() -> dict[str, Any]:
    return dict(_CTX.get())


class ContextFilter(logging.Filter):
    """Copies the active ``log_context`` onto the record as ``record.ctx``."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "ctx"):
            record.ctx = current_context()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger, msg, context, event fields, exception."""

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        out.update(getattr(record, "ctx", None) or {})
        for k, v in record.__dict__.items():
            if k not in _STD_ATTRS and k != "ctx":
                out[k] = v
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """``2026-10-21 08:00:00 INFO    [phase/track] logger: message``"""

    def __init__(self, with_logger: bool = True):
        super().__init__(datefmt="%Y-%m-%d %H:%M:%S")
        self.with_logger = with_logger

    def format(self, record: logging.LogRecord) -> str:
        ctx = getattr(record, "ctx", None) or {}
        where = "/".join(str(ctx[k]) for k in ("phase", "track", "tile", "step") if k in ctx)
        head = f"{self.formatTime(record, self.datefmt)} {record.levelname:<7}"
        if where:
            head += f" [{where}]"
        if self.with_logger:
            head += f" {record.name}:"
        text = f"{head} {record.getMessage()}"
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


def _own(handler: logging.Handler) -> logging.Handler:
    setattr(handler, _OWNED, True)
    handler.addFilter(ContextFilter())
    return handler


def configure(level: str | int = "INFO", *, console: bool = True, jsonl: str | Path | None = None,
              console_stream=None) -> None:
    """Configure the root logger (idempotent: replaces handlers installed by a previous call).

    Legacy modules that still use ``logging`` are captured too, since handlers sit on the root.
    """
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _OWNED, False)]:
        root.removeHandler(h)
        h.close()
    root.setLevel(logging.DEBUG)
    lvl = logging.getLevelName(level.upper()) if isinstance(level, str) else level
    if console:
        h = _own(logging.StreamHandler(console_stream or sys.stderr))
        h.setLevel(lvl)
        h.setFormatter(TextFormatter(with_logger=False))
        root.addHandler(h)
    if jsonl is not None:
        Path(jsonl).parent.mkdir(parents=True, exist_ok=True)
        h = _own(logging.FileHandler(jsonl, encoding="utf-8"))
        h.setLevel(logging.DEBUG)
        h.setFormatter(JsonFormatter())
        root.addHandler(h)
    for noisy in ("urllib3", "matplotlib", "fiona", "rasterio", "numba", "h5py", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


@contextmanager
def file_log(path: str | Path, level: int = logging.DEBUG) -> Iterator[Path]:
    """Also write a plain-text log to ``path`` while the block runs (one file per phase)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    h = _own(logging.FileHandler(path, encoding="utf-8"))
    h.setLevel(level)
    h.setFormatter(TextFormatter())
    root = logging.getLogger()
    root.addHandler(h)
    try:
        yield path
    finally:
        root.removeHandler(h)
        h.close()


def event(logger: logging.Logger, name: str, msg: str | None = None, /, *, level: int = logging.INFO,
          **fields: Any) -> None:
    """Structured event; ``fields`` land as top-level keys in the JSON log (a key that clashes with
    a ``LogRecord`` attribute, e.g. ``name``, gets a trailing underscore)."""
    extra = {(f"{k}_" if k in _STD_ATTRS else k): v for k, v in fields.items()}
    logger.log(level, msg or name, extra={"event": name, **extra})
