"""Provenance manifest written next to every artifact (stack, PS run, product, run) — ARCHITECTURE §10.6."""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from geoeyes.core.errors import StoreError
from geoeyes.core.hashing import sha256_file

SCHEMA = "geoeyes.manifest/1"
MANIFEST_NAME = "manifest.json"


def atomic_write_text(path: str | Path, text: str, encoding: str = "utf-8") -> Path:
    """Write via a temporary file in the same folder and rename, so readers never see a partial file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def atomic_write_json(path: str | Path, obj: Any) -> Path:
    return atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n")


def read_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise StoreError(f"{path}: not found") from None
    except json.JSONDecodeError as exc:
        raise StoreError(f"{path}: invalid JSON ({exc})") from None


@dataclass
class FileEntry:
    path: str          # relative to the artifact folder, POSIX separators
    sha256: str
    bytes: int


@dataclass
class InputRef:
    kind: str
    uri: str
    sha256: str = ""


@dataclass
class Manifest:
    kind: str                                   # stack | ps_run | product | run
    id: str
    created: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))
    run_id: str = ""
    engine: str = ""
    software: dict[str, Any] = field(default_factory=dict)
    inputs: list[InputRef] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)       # {"sha256": ..., "snapshot": "params.json"}
    outputs: list[FileEntry] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    phases: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA

    def add_outputs(self, root: str | Path, paths) -> None:
        """Record files (relative to ``root``) with checksum and size."""
        root = Path(root)
        for p in paths:
            p = Path(p)
            full = p if p.is_absolute() else root / p
            self.outputs.append(FileEntry(full.relative_to(root).as_posix(), sha256_file(full), full.stat().st_size))

    def write(self, folder: str | Path) -> Path:
        if not self.software:
            self.software = software_info()
        return atomic_write_json(Path(folder) / MANIFEST_NAME, asdict(self))

    @classmethod
    def read(cls, folder: str | Path) -> Manifest:
        d = read_json(Path(folder) / MANIFEST_NAME)
        if d.get("schema") != SCHEMA:
            raise StoreError(f"{folder}: unsupported manifest schema {d.get('schema')!r}")
        d["inputs"] = [InputRef(**x) for x in d.get("inputs", [])]
        d["outputs"] = [FileEntry(**x) for x in d.get("outputs", [])]
        return cls(**d)

    def verify(self, folder: str | Path) -> list[str]:
        """Paths whose checksum no longer matches (missing files included)."""
        bad = []
        for f in self.outputs:
            p = Path(folder) / f.path
            if not p.exists() or sha256_file(p) != f.sha256:
                bad.append(f.path)
        return bad


def software_info(packages=("numpy", "scipy", "xarray", "zarr", "h5py", "pyarrow", "geopandas", "rasterio")) -> dict:
    import contextlib
    from importlib.metadata import PackageNotFoundError, version
    pk = {}
    for n in packages:
        with contextlib.suppress(PackageNotFoundError):
            pk[n] = version(n)
    from geoeyes import __version__
    return {"geoeyes": __version__, "python": sys.version.split()[0], "platform": platform.platform(),
            "packages": pk}
