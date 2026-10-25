"""StackStore: coregistered SAR stack as a Zarr v3 store (ARCHITECTURE §10.2).

One store per stack (one track, plus one subswath for Sentinel-1)::

    stack.zarr/   attrs: stack_id, track, sensor, reference_date, wavelength_m, engine, ...
      slc        (date, y, x)  complex64
      ifg        (pair, y, x)  complex64
      coherence  (pair, y, x)  float32
      geometry/… (y, x)        float32/64     stored as variables named geometry_<name>
      coords     date (datetime64[D]), pair (str), y, x

Variables are written whole (``write``) or allocated then filled block by block
(``allocate`` + ``write_region``), so processing never needs the full cube in memory.
"""
from __future__ import annotations

import shutil
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from geoeyes.core.errors import StoreError

DEFAULT_CHUNKS = {"date": 1, "pair": 1, "y": 1024, "x": 1024}
ZARR_FORMAT = 3


def _chunks_for(dims: tuple[str, ...], shape: tuple[int, ...], chunks: Mapping[str, int] | None) -> tuple[int, ...]:
    c = {**DEFAULT_CHUNKS, **(chunks or {})}
    return tuple(min(int(c.get(d, n)), n) if n else 1 for d, n in zip(dims, shape, strict=True))


class StackStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    # -------------------------------------------------------------- lifecycle
    @classmethod
    def create(cls, path: str | Path, *, coords: Mapping[str, Any], attrs: Mapping[str, Any] | None = None,
               overwrite: bool = False) -> StackStore:
        path = Path(path)
        if path.exists():
            if not overwrite:
                raise StoreError(f"{path}: stack already exists")
            shutil.rmtree(path)
        ds = xr.Dataset(coords={k: np.asarray(v) for k, v in coords.items()}, attrs=dict(attrs or {}))
        cls._to_zarr(ds, path, mode="w")
        return cls(path)

    def exists(self) -> bool:
        return (self.path / "zarr.json").exists()

    # -------------------------------------------------------------- read
    def open(self) -> xr.Dataset:
        """Lazy dataset (dask-backed)."""
        if not self.exists():
            raise StoreError(f"{self.path}: no stack")
        return xr.open_zarr(self.path, consolidated=False, zarr_format=ZARR_FORMAT)

    @property
    def attrs(self) -> dict[str, Any]:
        return dict(self.open().attrs)

    def has(self, name: str) -> bool:
        return self.exists() and name in self.open().data_vars

    def read(self, name: str, **isel) -> np.ndarray:
        """Load (a selection of) one variable into memory, e.g. ``read("slc", date=3)``."""
        ds = self.open()
        if name not in ds:
            raise StoreError(f"{self.path}: no variable {name!r}")
        return ds[name].isel(**isel).values

    # -------------------------------------------------------------- write
    def write(self, name: str, data, dims: tuple[str, ...], *, attrs: Mapping[str, Any] | None = None,
              chunks: Mapping[str, int] | None = None) -> None:
        """Write (or replace) a whole variable."""
        arr = np.asarray(data)
        da = xr.DataArray(arr, dims=dims, attrs=dict(attrs or {}))
        enc = {name: {"chunks": _chunks_for(dims, arr.shape, chunks)}}
        if self.has(name):
            self._drop(name)
        self._to_zarr(xr.Dataset({name: da}, attrs=self._group_attrs()), self.path, mode="a", encoding=enc)

    def allocate(self, name: str, dims: tuple[str, ...], dtype, *, attrs: Mapping[str, Any] | None = None,
                 chunks: Mapping[str, int] | None = None, fill_value=None) -> None:
        """Create an empty variable sized by the store's coordinates, to be filled with ``write_region``."""
        import dask.array as dsa
        ds = self.open()
        shape = tuple(ds.sizes[d] for d in dims)
        ch = _chunks_for(dims, shape, chunks)
        lazy = dsa.zeros(shape, dtype=dtype, chunks=ch)
        da = xr.DataArray(lazy, dims=dims, attrs=dict(attrs or {}))
        enc = {name: {"chunks": ch, **({"fill_value": fill_value} if fill_value is not None else {})}}
        if name in ds.data_vars:
            self._drop(name)
        self._to_zarr(xr.Dataset({name: da}, attrs=self._group_attrs()), self.path, mode="a", encoding=enc,
                      compute=False)

    def write_region(self, name: str, data, region: Mapping[str, slice]) -> None:
        """Fill part of an allocated variable; ``region`` gives a slice per dimension of the variable."""
        ds = self.open()
        if name not in ds.data_vars:
            raise StoreError(f"{self.path}: allocate {name!r} before write_region")
        dims = ds[name].dims
        da = xr.DataArray(np.asarray(data), dims=dims)
        sub = xr.Dataset({name: da})
        self._to_zarr(sub, self.path, mode="r+", region={d: region.get(d, slice(None)) for d in dims})

    def update_attrs(self, **attrs) -> None:
        import zarr
        g = zarr.open_group(self.path, mode="r+", zarr_format=ZARR_FORMAT)
        g.attrs.update(attrs)

    # -------------------------------------------------------------- internals
    def _group_attrs(self) -> dict[str, Any]:
        """Appending a Dataset replaces the group attributes, so writes carry the current ones along."""
        import zarr
        return dict(zarr.open_group(self.path, mode="r", zarr_format=ZARR_FORMAT).attrs)

    def _drop(self, name: str) -> None:
        import zarr
        g = zarr.open_group(self.path, mode="r+", zarr_format=ZARR_FORMAT)
        del g[name]

    @staticmethod
    def _to_zarr(ds: xr.Dataset, path: Path, **kw) -> None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*[Cc]onsolidated metadata.*")
            ds.to_zarr(path, zarr_format=ZARR_FORMAT, consolidated=False, **kw)
