"""Per-project run lock (port of ``modules/ops/lock.py``).

Lock files live in ``<project>/.state/locks/<scope>.lock`` and hold JSON {pid, create_time,
started_at, argv, host, scope}. A run scoped to some tracks/subswaths conflicts only with runs that
share one of them; an unscoped run conflicts with every run. A lock whose process is gone (or whose
PID was recycled) is stale and is taken over.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

from geoeyes.core.errors import LockedError
from geoeyes.io.manifest import atomic_write_json

log = logging.getLogger(__name__)
ALL = "_all"


def _scope_set(scope) -> frozenset[str]:
    if not scope:
        return frozenset()
    items = scope.split(",") if isinstance(scope, str) else scope
    return frozenset(s.strip() for s in items if s and s.strip())


def _conflicts(a: frozenset[str], b: frozenset[str]) -> bool:
    return not a or not b or bool(a & b)


def _is_alive(info: dict) -> bool:
    import psutil
    pid = info.get("pid")
    if not isinstance(pid, int):
        return False
    try:
        proc = psutil.Process(pid)
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
            return False
        ct = info.get("create_time")
        return ct is None or abs(proc.create_time() - float(ct)) < 1.0
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return False


def _read(path: Path) -> dict | None:
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        return info if isinstance(info, dict) else None
    except (OSError, ValueError):
        return None


def list_locks(locks_dir: str | Path) -> list[dict]:
    """Every lock file with an ``alive`` flag."""
    locks_dir = Path(locks_dir)
    out = []
    for path in sorted(locks_dir.glob("*.lock")):
        info = _read(path) or {}
        if info:
            alive = _is_alive(info)
        else:   # being written by another process right now (O_EXCL create), or garbage
            try:
                alive = time.time() - path.stat().st_mtime < 10
            except OSError:
                continue
        out.append({**info, "lock_path": path.as_posix(), "alive": alive})
    return out


class ProjectLock:
    """``with ProjectLock(layout.locks, scope=["capella-asc"]): ...`` — raises ``LockedError``."""

    def __init__(self, locks_dir: str | Path, scope=None):
        self.locks_dir = Path(locks_dir)
        self.scope = _scope_set(scope)
        name = "-".join(sorted(self.scope)) if self.scope else ALL
        self.path = self.locks_dir / f"{name}.lock"
        self.acquired = False

    def acquire(self) -> ProjectLock:
        import psutil
        self.locks_dir.mkdir(parents=True, exist_ok=True)
        for other in list_locks(self.locks_dir):
            if not _conflicts(self.scope, _scope_set(other.get("scope"))):
                continue
            if other["alive"]:
                raise LockedError(
                    f"locked by PID {other.get('pid')} (started {other.get('started_at')}, host "
                    f"{other.get('host')}, scope {other.get('scope') or 'all'}); lock file {other['lock_path']}")
            log.warning("taking over stale lock %s (PID %s is gone)", other["lock_path"], other.get("pid"))
            with contextlib.suppress(OSError):
                os.remove(other["lock_path"])
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            holder = _read(self.path) or {}
            raise LockedError(f"locked by PID {holder.get('pid')}; lock file {self.path}") from None
        atomic_write_json(self.path, {
            "pid": os.getpid(), "create_time": psutil.Process(os.getpid()).create_time(),
            "started_at": datetime.now().isoformat(timespec="seconds"), "argv": list(sys.argv),
            "host": socket.gethostname(), "scope": sorted(self.scope)})
        self.acquired = True
        return self

    def release(self) -> None:
        if not self.acquired:
            return
        info = _read(self.path) or {}
        if info.get("pid") in (None, os.getpid()):
            with contextlib.suppress(OSError):
                os.remove(self.path)
        self.acquired = False

    def __enter__(self) -> ProjectLock:
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()
