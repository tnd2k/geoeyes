"""Download rate of this process, for the web app: every downloader reports its bytes with ``add``; while a run
watches a file (``watch``), the rate over the last seconds and the bytes so far are written there about once a
second (``<project>/.state/net.json``), without adding lines to the run log."""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from pathlib import Path

WINDOW_S = 5.0
_lock = threading.Lock()
_hist: deque[tuple[float, int]] = deque()
_total = 0
_target: Path | None = None
_last_write = 0.0


def watch(path: Path | None) -> None:
    """Write the rate to ``path`` from now on (None: stop)."""
    global _target, _total, _last_write
    with _lock:
        _target, _total, _last_write = (Path(path) if path else None), 0, 0.0
        _hist.clear()
    if path:
        _write(0.0, 0)


def add(n: int) -> None:
    """``n`` bytes just arrived."""
    global _total, _last_write
    if n <= 0:
        return
    now = time.monotonic()
    with _lock:
        _total += n
        _hist.append((now, n))
        while _hist and now - _hist[0][0] > WINDOW_S:
            _hist.popleft()
        if _target is None or now - _last_write < 1.0:
            return
        _last_write = now
        span = max(now - _hist[0][0], 1.0) if len(_hist) > 1 else WINDOW_S
        rate, total = sum(b for _, b in _hist) / min(span, WINDOW_S), _total
    _write(rate, total)


def _write(rate: float, total: int) -> None:
    target = _target
    if target is None:
        return
    try:
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps({"rate_bps": round(rate), "bytes": total, "updated": time.time()}), encoding="utf-8")
        tmp.replace(target)
    except OSError:                                   # the rate is a display aid: never fail a download for it
        pass


__all__ = ["add", "watch"]
