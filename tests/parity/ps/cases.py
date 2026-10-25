"""Legacy StaMPS runs used as parity fixtures: the new step K takes the legacy step K-1 output (or the
prep files for step 1) and is compared with the legacy step K output."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pytest

from geoeyes.io.legacy import stamps
from geoeyes.processing.ps.params import EngineParams, engine_params
from geoeyes.processing.ps.steps.est_gamma import EstGamma
from geoeyes.processing.ps.steps.select import Select

RESULTS = Path(r"D:\projects\geoeyes_workspace\legacy\results")       # legacy StaMPS runs (outside the repo)


@dataclass(frozen=True)
class Case:
    name: str
    root: Path                      # INSAR_<m>_NORMAL_vN
    rho: float                      # mean slant range hard-coded in that sensor's legacy flow.py
    rerun: Path | None = None       # legacy steps 6-8 re-run with the pass-1 step6/step7 kept in PATCH_1/pass1
    stack: Path | None = None       # native StackStore the legacy run was exported from (former stamps_bridge)
    engine: tuple = ()              # [ps] keys selecting that sensor's legacy engine variant
    patch: str = "PATCH_1"
    uw_failed: tuple = ()           # 0-based interferograms the legacy pass-1 unwrap failed on (legacy bug)

    @cached_property
    def parms(self) -> dict:
        return json.loads((self.root / "process" / "parms.json").read_text(encoding="utf-8"))

    @property
    def patch_dir(self) -> Path:
        return self.root / "process" / self.patch

    def step(self, k: int, name: str) -> dict:
        return stamps.read_step(self.patch_dir / f"step{k}" / name)

    @cached_property
    def master_par(self) -> dict[str, str]:
        master, _, _ = stamps.read_ifg_list(self.root / "input" / "pscphase.in")
        return stamps.read_par(self.root / "raw" / "rslc" / f"{master:%Y%m%d}.rslc.par")


def params(case: Case) -> EngineParams:
    return engine_params({**case.parms, **dict(case.engine), "legacy_quirks": "y"},
                         wavelength=float(case.parms["lambda"]), rho=case.rho)


def legacy_gamma(case: Case) -> EstGamma:
    """Step-2 result rebuilt from the legacy ``step2/pm1.h5``."""
    pm = case.step(2, "pm1.h5")
    flat = (lambda k: np.asarray(pm[k], np.float64).reshape(-1))  # noqa: E731
    return EstGamma(ph_patch=pm["ph_patch"], ph_res=pm["ph_res"].real.astype(np.float32), ph_grid=pm["ph_grid"],
                    ph_weight=pm["ph_weight"], K=flat("K_ps"), C=flat("C_ps"), coh=flat("coh_ps"),
                    Q=flat("Q_ps") if "Q_ps" in pm else np.ones(flat("K_ps").size),
                    grid_ij=pm["grid_ij"], low_pass=pm["low_pass"], n_trial_wraps=float(pm["n_trial_wraps"]),
                    Nr=flat("Nr"), Nr_max_nz_ix=int(pm["Nr_max_nz_ix"]), coh_bins=flat("coh_bins"),
                    n_iter=int(pm["i_loop"]))


def legacy_select(case: Case) -> Select:
    """Step-3 result rebuilt from the legacy ``step3/select1.h5``."""
    sl = case.step(3, "select1.h5")
    flat = (lambda k: np.asarray(sl[k], np.float64).reshape(-1))  # noqa: E731
    return Select(ix=sl["ix"], keep_ix=sl["keep_ix"].astype(bool), ph_patch2=sl["ph_patch2"],
                  ph_res2=sl["ph_res2"].real.astype(np.float32), K2=flat("K_ps2"), C2=flat("C_ps2"),
                  coh2=flat("coh_ps2"), Q2=flat("Q_ps2") if "Q_ps2" in sl else np.ones(flat("K_ps2").size), coh_thresh=np.ravel(sl["coh_thresh"]),
                  coh_thresh_coeffs=np.ravel(sl["coh_thresh_coeffs"]), ifg_index=np.ravel(sl["ifg_index"]),
                  max_percent_rand=float(sl["max_percent_rand"]))


FIXTURES = Path(r"D:\projects\geoeyes_workspace\fixtures\stamps")

CASES = [Case("csk_hanoi_native", RESULTS / "hanoi_csk_native" / "INSAR_20120206_NORMAL_v1", rho=780_000.0,
              rerun=FIXTURES / "csk_hanoi_native" / "INSAR_20120206_NORMAL_v1",
              stack=Path(r"D:\projects\geoeyes_workspace\projects\hanoi_csk\stacks\csk-asc-ref20120206\stack.zarr"),
              engine=(("dem_error_ambiguity", "y"), ("select_nr_scaling", "population"),
                      ("unwrap_grid_filter", "goldstein"))),
         Case("s1_mexico_snap", RESULTS / "mexico_s1" / "INSAR_20240714_NORMAL_v2", rho=831_000.0,
              rerun=FIXTURES / "s1_mexico_snap" / "INSAR_20240714_NORMAL_v2",
              # S1 _uw_stat_costs: the 2-ahead prefetch breaks after the skipped master column (KeyError)
              uw_failed=(6, 8, 10, 12))]


def stack_cases():
    return [pytest.param(c, id=c.name, marks=pytest.mark.skipif(
        c.stack is None or not c.stack.exists(), reason=f"stack of {c.name} not present")) for c in CASES]


def rerun_step(case: Case, k: int, name: str, pass1: bool = False) -> dict:
    """A ``stepK`` file of the re-run (``pass1``: the snapshot taken before pass 2 overwrote it)."""
    base = case.rerun / "process" / case.patch
    return stamps.read_step((base / "pass1" if pass1 else base) / f"step{k}" / name)


def rerun_cases():
    return [pytest.param(c, id=c.name, marks=pytest.mark.skipif(
        c.rerun is None or not (c.rerun / "process" / c.patch / "pass1").exists(),
        reason=f"pass-1 fixtures of {c.name} not present")) for c in CASES]


def cases():
    return [pytest.param(c, id=c.name, marks=pytest.mark.skipif(
        not (c.patch_dir / "step1").exists(), reason=f"legacy run {c.name} not present")) for c in CASES]
