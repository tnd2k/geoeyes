"""Readers for the legacy StaMPS layout (``INSAR_<m>_NORMAL_vN``): master ``.rslc.par``, ``diff0/*.base``,
``input/pscphase.in`` and the patch candidate files ``pscands.1.*`` written by the legacy prep, plus the
per-step ``process/PATCH_n/stepK/*.h5`` outputs of the legacy engine. Used by the parity harness of
``geoeyes.processing.ps`` and by the transition; nothing here writes.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import h5py
import numpy as np
import pandas as pd


def read_par(path: Path) -> dict[str, str]:
    """GAMMA-style ``key:<tab>value<tab>unit`` file -> {key: value} (first token only)."""
    out = {}
    for line in Path(path).read_text(encoding="ascii", errors="replace").splitlines():
        key, sep, rest = line.partition(":")
        if sep and rest.split():
            out[key.strip()] = rest.split("\t")[1] if "\t" in rest else rest.split()[0]
    return out


def read_base(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """``initial_baseline(TCN)`` (m) and ``initial_baseline_rate`` (m/s) from a ``.base`` file."""
    vals = {}
    for line in Path(path).read_text(encoding="ascii").splitlines():
        key, _, rest = line.partition(":")
        if key in ("initial_baseline(TCN)", "initial_baseline_rate"):
            vals[key] = np.array([float(x) for x in rest.strip().split("\t")[:3]])
    return vals["initial_baseline(TCN)"], vals["initial_baseline_rate"]


def _ymd(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def read_ifg_list(pscphase_in: Path) -> tuple[date, list[date], list[Path]]:
    """(master, secondaries, diff paths) from ``pscphase.in`` (first line = width); names ``<m>_<s>.diff``.
    The file holds absolute paths: when the run folder was moved, they are re-rooted on its current location."""
    pscphase_in = Path(pscphase_in)
    root = pscphase_in.parent.parent                      # INSAR_<master>_..._vN/
    lines = [ln.strip() for ln in pscphase_in.read_text(encoding="utf-8").splitlines() if ln.strip()]
    paths = [_reroot(Path(p), root) for p in lines[1:]]
    master = _ymd(paths[0].stem[:8])
    return master, [_ymd(p.stem[9:17]) for p in paths], paths


def _reroot(p: Path, root: Path) -> Path:
    if p.exists() or root.name not in p.parts:
        return p
    i = len(p.parts) - 1 - p.parts[::-1].index(root.name)       # last occurrence of the run folder name
    return root.joinpath(*p.parts[i + 1:])


def read_candidates(patch_dir: Path, n_ifg: int) -> dict[str, np.ndarray | None]:
    """``pscands.1.{ij,ll,ph,hgt,da,coh,forced}`` of one patch; optional files are None when absent."""
    p = Path(patch_dir)
    ij = pd.read_csv(p / "pscands.1.ij", sep=r"\s+", header=None, dtype=int, engine="c").to_numpy()
    n = ij.shape[0]
    lonlat = pd.read_csv(p / "pscands.1.ll", sep=r"\s+", header=None, dtype=np.float32,
                         engine="c").to_numpy().reshape(-1, 2)
    raw = np.fromfile(p / "pscands.1.ph", dtype=">f4").reshape(-1, n, 2)
    if raw.shape[0] != n_ifg:
        raise ValueError(f"pscands.1.ph has {raw.shape[0]} interferograms, expected {n_ifg}")
    out: dict[str, np.ndarray | None] = {
        "ij": ij, "lonlat": lonlat,
        "ph": (raw[:, :, 0] + 1j * raw[:, :, 1]).astype(np.complex64).T,
        "hgt": None, "da": None, "coh": None, "forced": None,
    }
    if (p / "pscands.1.hgt").exists():
        out["hgt"] = np.fromfile(p / "pscands.1.hgt", dtype=">f4").astype(np.float32)
    if (p / "pscands.1.da").exists():
        out["da"] = pd.read_csv(p / "pscands.1.da", header=None, engine="c")[0].to_numpy(np.float64)
    if (p / "pscands.1.coh").exists():
        coh = np.fromfile(p / "pscands.1.coh", dtype=">f4").astype(np.float64)
        out["coh"] = coh[:n] if coh.size >= n else np.r_[coh, np.full(n - coh.size, np.nan)]
    if (p / "pscands.1.forced").exists():
        out["forced"] = pd.read_csv(p / "pscands.1.forced", sep=r"\s+", header=None,
                                    engine="c")[0].to_numpy().astype(bool)
    return out


def read_step(path: Path) -> dict[str, np.ndarray]:
    """All datasets of a legacy ``stepK/*.h5``; MATLAB-shaped row vectors (1, n) and scalars (1, 1) are
    flattened to (n,) and 0-d."""
    out = {}
    with h5py.File(path, "r") as h:
        for k, ds in h.items():
            if not isinstance(ds, h5py.Dataset):
                continue
            a = ds[()]
            if isinstance(a, np.ndarray) and a.ndim == 2 and 1 in a.shape:
                a = a.reshape(()) if a.size == 1 else a.reshape(-1)
            out[k] = a
    return out
