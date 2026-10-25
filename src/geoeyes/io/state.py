"""StateStore: processing-engine state in HDF5 with a declared schema (ARCHITECTURE §10.3).

Each engine (``ps``, ``ps_lite``) declares a ``StateSchema``: every variable has a path
(``step4/ph``), dtype, dimension names, units and a description, plus the legacy StaMPS name it
replaces so old ``.mat`` outputs can be compared. Arrays keep their natural shape (no MATLAB
``(1, 1)`` scalars). Completed steps are recorded in the file (replaces ``left-off.txt``).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

from geoeyes.core.errors import StoreError


@dataclass(frozen=True)
class VarSpec:
    path: str                       # "step4/ph"
    dtype: str                      # numpy dtype string
    dims: tuple[str, ...]           # ("ps", "ifg")
    units: str = ""
    description: str = ""
    legacy: str = ""                # legacy StaMPS name, e.g. "ph2.mat:ph"


@dataclass(frozen=True)
class StateSchema:
    name: str                       # "geoeyes.ps" / "geoeyes.ps_lite"
    version: int
    vars: Mapping[str, VarSpec] = field(default_factory=dict)

    @classmethod
    def of(cls, name: str, version: int, specs: Iterable[VarSpec]) -> StateSchema:
        return cls(name, version, {s.path: s for s in specs})


class StateStore:
    def __init__(self, path: str | Path, schema: StateSchema):
        self.path = Path(path)
        self.schema = schema

    # -------------------------------------------------------------- write
    def write(self, key: str, data, **attrs) -> None:
        spec = self._spec(key)
        arr = np.asarray(data)
        if arr.ndim != len(spec.dims):
            raise StoreError(f"{key}: expected {len(spec.dims)}-D {spec.dims}, got shape {arr.shape}")
        arr = arr.astype(spec.dtype, copy=False)
        with self._open("a") as f:
            if key in f:
                del f[key]
            kw = {"compression": "gzip", "compression_opts": 4, "shuffle": True} if arr.size > 1024 else {}
            ds = f.create_dataset(key, data=arr, **kw)
            ds.attrs["dims"] = list(spec.dims)
            ds.attrs["units"] = spec.units
            ds.attrs["description"] = spec.description
            if spec.legacy:
                ds.attrs["legacy"] = spec.legacy
            for k, v in attrs.items():
                ds.attrs[k] = v

    def write_many(self, values: Mapping[str, object]) -> None:
        for k, v in values.items():
            self.write(k, v)

    def mark_done(self, step: str) -> None:
        with self._open("a") as f:
            done = list(f.attrs.get("done_steps", []))
            if step not in done:
                f.attrs["done_steps"] = [*done, step]

    # -------------------------------------------------------------- read
    def read(self, key: str) -> np.ndarray:
        self._spec(key)
        if not self.path.exists():
            raise StoreError(f"{self.path}: no state file")
        with h5py.File(self.path, "r") as f:
            if key not in f:
                raise StoreError(f"{self.path}: {key} not written")
            return f[key][()]

    def has(self, key: str) -> bool:
        if not self.path.exists():
            return False
        with h5py.File(self.path, "r") as f:
            return key in f

    def keys(self) -> list[str]:
        if not self.path.exists():
            return []
        out: list[str] = []
        with h5py.File(self.path, "r") as f:
            f.visititems(lambda n, o: out.append(n) if isinstance(o, h5py.Dataset) else None)
        return out

    def done_steps(self) -> list[str]:
        if not self.path.exists():
            return []
        with h5py.File(self.path, "r") as f:
            return [str(s) for s in f.attrs.get("done_steps", [])]

    # -------------------------------------------------------------- internals
    def _spec(self, key: str) -> VarSpec:
        try:
            return self.schema.vars[key]
        except KeyError:
            raise StoreError(f"{key!r} is not in schema {self.schema.name} v{self.schema.version}") from None

    def _open(self, mode: str) -> h5py.File:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        f = h5py.File(self.path, mode)
        if "schema" not in f.attrs and mode != "r":
            f.attrs["schema"] = self.schema.name
            f.attrs["schema_version"] = self.schema.version
        elif f.attrs.get("schema") != self.schema.name:
            name = f.attrs.get("schema")
            f.close()
            raise StoreError(f"{self.path}: schema {name!r}, expected {self.schema.name!r}")
        return f
