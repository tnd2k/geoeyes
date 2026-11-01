"""Checkpoints of the PS engine, one per step: ``<run>/checkpoints/step<N>.pkl`` and ``step<N>.json`` (its key,
the time). A step is reused when its key is unchanged: the stack and the parameters of that step and of every
step before it (each key chains the previous one). ``from_step`` computes that step and the following ones
again; ``stop_after`` ends the run after that step (``PhasePaused``), the next run resumes from the checkpoints.
A run stopped or killed in the middle resumes from its last finished step."""
from __future__ import annotations

import json
import logging
import pickle
import time
from pathlib import Path

import numpy as np

from geoeyes.core.errors import PhasePaused
from geoeyes.core.hashing import sha256_params
from geoeyes.core.logging import event
from geoeyes.io.manifest import atomic_write_json

log = logging.getLogger(__name__)

STEPS = {1: "candidates", 2: "estimate gamma", 3: "select", 4: "weed", 5: "correct phase", 6: "unwrap, pass 1",
         7: "unwrap, pass 2", 8: "velocity, SCN, outputs"}
DIR = "checkpoints"


class Checkpoints:
    def __init__(self, out: str | Path, *, read_from: str | Path | None = None, from_step: int | None = None,
                 stop_after: int | None = None):
        for n in (from_step, stop_after):
            if n is not None and n not in STEPS:
                raise ValueError(f"PS step {n}: steps are 1-{max(STEPS)}")
        self.dir = Path(out) / DIR
        self.src = Path(read_from) / DIR if read_from else self.dir
        self.from_step, self.stop_after = from_step, stop_after
        self.keys: dict[int, str] = {}
        self.extra: dict = {}                        # merged into the step-5 checkpoint (the step-1 state it needs)

    def key(self, n: int, **parts) -> str:
        """The key of step ``n``: its parameters and the key of step n - 1."""
        self.keys[n] = sha256_params({"prev": self.keys.get(n - 1, ""), **{k: repr(v) for k, v in parts.items()}})
        return self.keys[n]

    def meta(self, n: int) -> dict:
        try:
            return json.loads((self.src / f"step{n}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def valid(self, n: int) -> bool:
        if self.from_step is not None and n >= self.from_step:
            return False
        return (n in self.keys and self.meta(n).get("key") == self.keys[n]
                and (self.src / f"step{n}.pkl").exists())

    def load(self, n: int):
        """The data of step ``n`` (written by this engine; not for untrusted files)."""
        with open(self.src / f"step{n}.pkl", "rb") as f:
            data = pickle.load(f)
        log.info("PS step %d (%s): reused from the checkpoint of %s", n, STEPS[n], self.meta(n).get("saved", "?"))
        return data

    def save(self, n: int, data, **meta) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"step{n}.json").unlink(missing_ok=True)
        if n == 5:
            data = {**self.extra, **data}
        tmp = self.dir / f"step{n}.part"
        with open(tmp, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(self.dir / f"step{n}.pkl")
        atomic_write_json(self.dir / f"step{n}.json", {"step": n, "name": STEPS[n], "key": self.keys[n],
                                                       "saved": time.strftime("%Y-%m-%d %H:%M:%S"), **meta})

    def reached(self, n: int) -> None:
        """Step ``n`` is done (computed or reused): the progress event, and the stop when asked for."""
        event(log, "progress", f"step {n}", stage="ps", done=n + 1, total=9)
        if self.stop_after == n:
            raise PhasePaused("ps", n, f"stopped after step {n} ({STEPS[n]}) as asked; the next run resumes "
                                       f"from step {n + 1}")


def status(run_dir: str | Path) -> list[dict]:
    """The saved checkpoints of a PS run folder: [{step, name, saved}] (the web page shows them)."""
    d = Path(run_dir) / DIR
    out = []
    for n, name in STEPS.items():
        try:
            m = json.loads((d / f"step{n}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            m = None
        out.append({"step": n, "name": name, "saved": m.get("saved") if m and (d / f"step{n}.pkl").exists() else None})
    return out


def pack_gamma(g):
    """Step 2 without a dense (n_i, n_j, n_ifg) grid: the occupied cells only (most of the grid is empty)."""
    import dataclasses
    grid = g.ph_grid
    if not isinstance(grid, np.ndarray):              # already sparse
        return {"g": g, "grid": None}
    flat = grid.reshape(-1, grid.shape[2])
    occ = np.flatnonzero(np.any(flat != 0, axis=1))
    return {"g": dataclasses.replace(g, ph_grid=np.zeros((0, 0, 0), np.complex64)),
            "grid": (grid.shape, occ, flat[occ])}


def unpack_gamma(d):
    import dataclasses
    if d["grid"] is None:
        return d["g"]
    shape, occ, vals = d["grid"]
    grid = np.zeros(shape, np.complex64)
    grid.reshape(-1, shape[2])[occ] = vals
    return dataclasses.replace(d["g"], ph_grid=grid)
