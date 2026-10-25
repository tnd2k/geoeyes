"""Content hashes for manifests and phase fingerprints."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

_CHUNK = 8 * 1024 * 1024


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(_CHUNK):
            h.update(block)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    """Stable JSON text: sorted keys, no whitespace, numpy scalars/arrays converted."""
    def default(o):
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, Path):
            return o.as_posix()
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        raise TypeError(f"not JSON serialisable: {type(o).__name__}")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=default, ensure_ascii=False)


def sha256_params(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_array(a: np.ndarray) -> str:
    """Hash of dtype, shape and contents (C order)."""
    a = np.ascontiguousarray(a)
    h = hashlib.sha256()
    h.update(f"{a.dtype.str}{a.shape}".encode())
    h.update(a.tobytes())
    return h.hexdigest()


def combine(*digests: str) -> str:
    """Order-sensitive hash of several hex digests (e.g. input hashes + params + phase version)."""
    h = hashlib.sha256()
    for d in digests:
        h.update(d.encode("ascii"))
        h.update(b"\0")
    return h.hexdigest()
