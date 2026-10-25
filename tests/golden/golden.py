"""Golden-output harness: run a case with the current code and compare it to the stored reference.

Golden data lives outside the repo under ``$GEOEYES_TEST_DATA/golden/<case>/expected/``. A case file
(``tests/golden/cases/<case>.json``) names the input, the processing parameters and the tolerances.
Comparisons match points by their pixel position (line, sample) and report RMSE / bias of the
values on the common points, so a refactor may reorder points without failing.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
CASES = Path(__file__).resolve().parent / "cases"


def load_case(name: str) -> dict:
    return json.loads((CASES / f"{name}.json").read_text(encoding="utf-8"))


def data_root() -> Path | None:
    """``GEOEYES_TEST_DATA`` from the environment, else from the repo's ``.env``."""
    root = os.environ.get("GEOEYES_TEST_DATA")
    if not root and (REPO / ".env").exists():
        from dotenv import dotenv_values
        root = dotenv_values(REPO / ".env").get("GEOEYES_TEST_DATA")
    return Path(root) if root else None


def expected_dir(name: str) -> Path | None:
    root = data_root()
    return root / "golden" / name / "expected" if root else None


def run_case(case: dict, out_dir: Path) -> dict:
    """Run the case with the code currently in the repo; returns the engine's summary."""
    if case["engine"] == "s1_native_ps_lite":
        return _run_s1_native(case, Path(out_dir))
    if case["engine"] == "stripmap_native_ps_lite":
        return _run_stripmap_native(case, Path(out_dir))
    if case["engine"] == "pipeline":
        return _run_pipeline(case, Path(out_dir))
    raise ValueError(f"unknown engine {case['engine']!r}")


def _run_pipeline(case: dict, out: Path) -> dict:
    """A frozen project configuration run by the controller (every phase as in production) in a scratch
    workspace, AOI replaced by the case's; the PS run's points and the product are kept under ``out``."""
    import shutil
    import tomllib

    from geoeyes.config.loader import dump, load_dict
    from geoeyes.controller.pipeline import run
    from geoeyes.workspace import WorkspaceLayout
    inp = case["input"]
    raw = tomllib.loads((CASES / inp["config"]).read_text(encoding="utf-8"))
    raw["project"]["name"] = "golden"
    raw["aoi"] = {"bbox": inp["aoi"]}
    raw.setdefault("report", {})["copy_to"] = ""
    ws = WorkspaceLayout.at(out / "ws")
    project = ws.project("golden").ensure()
    cfg = load_dict(raw)                                  # with the sensor preset, as `geoeyes run` loads it
    dump(cfg, project.config)
    res = run(cfg, project, ws, to=inp.get("to", "build_product"), log_level="WARNING")
    if res["status"] != "ok":
        raise RuntimeError(f"golden pipeline failed: {res['phases']}")
    track = cfg.tracks[0].track_id
    shutil.copytree(project.ps_run(track), out / "ps_run",
                    ignore=shutil.ignore_patterns("state.h5", "checkpoint_*", "figures"))
    products = sorted((project.root / "products").glob("*"))
    if products:
        shutil.copytree(products[-1], out / "product", ignore=shutil.ignore_patterns("rasters"))
    from geoeyes.core.logging import configure
    configure("WARNING")                                  # closes the run's JSON log so the scratch dir can go
    shutil.rmtree(out / "ws", ignore_errors=True)
    return res


def _run_stripmap_native(case: dict, out: Path) -> dict:
    """Raw scenes (Capella / CSK) -> native stripmap stack -> ps_lite."""
    from datetime import date
    from functools import partial

    from geoeyes.config.schema import PsLiteSection
    from geoeyes.core.types import BBox
    from geoeyes.geometry.dem import load_dem
    from geoeyes.processing.ps_lite.runner import run as run_ps_lite
    from geoeyes.processing.stack.native.stripmap import Scene, build_stripmap_stack

    inp = case["input"]
    scenes = {}
    for d in sorted(p for p in Path(inp["scenes"]).iterdir() if p.is_dir()):
        day = date(int(d.name[:4]), int(d.name[4:6]), int(d.name[6:8]))
        if case["sensor"] == "capella":
            from geoeyes.sensors.capella import slc as rdr
            tif, js = rdr.find_files(d)
            scenes[day] = Scene(rdr.read_metadata(js), partial(rdr.read_slc, tif))
        elif case["sensor"] == "cosmo_skymed":
            from geoeyes.sensors.cosmo_skymed import hdf5 as rdr
            h5 = rdr.find_h5(d)
            scenes[day] = Scene(rdr.read_metadata(h5), partial(rdr.read_slc, h5))
        else:
            raise ValueError(f"unsupported sensor {case['sensor']!r}")
    s, n, w, e = inp["dem_box"]
    st = build_stripmap_stack(scenes, date.fromisoformat(inp["reference"]), load_dem(None, s, n, w, e),
                              out / "stack.zarr", aoi=BBox.from_sequence(inp["aoi"]), track_id=inp["track"],
                              overwrite=True)
    return run_ps_lite(st, out / "ps_run", PsLiteSection(**case["params"]), track_id=inp["track"])


def _run_s1_native(case: dict, out: Path) -> dict:
    """Burst archive -> native stack (POEORB) -> ps_lite."""
    import json as _json
    from datetime import date

    from geoeyes.config.schema import PsLiteSection
    from geoeyes.core.types import BBox
    from geoeyes.geometry.dem import load_dem
    from geoeyes.processing.ps_lite.runner import run as run_ps_lite
    from geoeyes.processing.stack.native.s1_stack import build_s1_stack
    from geoeyes.sensors.sentinel1.orbits import PoeorbProvider

    inp = case["input"]
    arch = Path(inp["archive"])
    scenes = {}
    for d in sorted(arch.iterdir()):
        day = d.name.split("_")[5][:8]
        scenes[date(int(day[:4]), int(day[4:6]), int(day[6:]))] = d
    ids = sorted({r["full_burst_id"] for d in scenes.values()
                  for r in _json.loads((d / "bursts.json").read_text())})
    s, n, w, e = inp["dem_box"]
    dem = load_dem(None, s, n, w, e)
    orbits = PoeorbProvider(inp["orbit_cache"], token=os.environ.get("EARTHDATA_TOKEN"))
    st = build_s1_stack(scenes, ids, date.fromisoformat(inp["reference"]), dem, out / "stack.zarr",
                        aoi=BBox.from_sequence(inp["aoi"]), track_id=inp["track"], orbits=orbits, overwrite=True)
    return run_ps_lite(st, out / "ps_run", PsLiteSection(**case["params"]), track_id=inp["track"])


@dataclass
class Report:
    metrics: dict = field(default_factory=dict)
    failures: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def check(self, name: str, value: float, limit: float, *, below: bool = True) -> None:
        self.metrics[name] = value
        bad = (value > limit) if below else (value < limit)
        if bad or not np.isfinite(value):
            self.failures.append(f"{name} = {value:.4g} ({'>' if below else '<'} limit {limit:g})")

    def __str__(self) -> str:
        lines = [f"{k:28s} {v:.4g}" for k, v in self.metrics.items()]
        if self.failures:
            lines += ["FAILED:"] + [f"  {f}" for f in self.failures]
        return "\n".join(lines)


def _match(a_line, a_sample, b_line, b_sample):
    """Indices (ia, ib) of points present in both sets, matched on (line, sample)."""
    key_a = np.asarray(a_line, np.int64) * 1_000_000 + np.asarray(a_sample, np.int64)
    key_b = np.asarray(b_line, np.int64) * 1_000_000 + np.asarray(b_sample, np.int64)
    _, ia, ib = np.intersect1d(key_a, key_b, assume_unique=False, return_indices=True)
    return ia, ib


def _rmse(x):
    x = x[np.isfinite(x)]
    return float(np.sqrt(np.mean(x ** 2))) if x.size else float("nan")


def compare_points(expected: Path, actual: Path, tol: dict) -> Report:
    """Compare two ps_lite runs through their ``points.parquet`` (matched on stack line/sample)."""
    import pandas as pd
    r = Report()
    e = pd.read_parquet(expected / "points.parquet")
    a = pd.read_parquet(actual / "points.parquet")
    r.check("kept_rel_diff", abs(len(a) - len(e)) / max(len(e), 1), tol["kept_rel"])
    ie, ia = _match(e["line"], e["sample"], a["line"], a["sample"])
    r.check("matched_frac", ie.size / max(len(e), 1), tol["match_min_frac"], below=False)
    dv = a["vel_los_mm_yr"].values[ia] - e["vel_los_mm_yr"].values[ie]
    r.check("vel_rmse_mm_yr", _rmse(dv), tol["vel_rmse_mm_yr"])
    r.check("vel_bias_mm_yr", abs(float(np.nanmean(dv))), tol["vel_bias_mm_yr"])
    r.check("dh_rmse_m", _rmse(a["dem_err_m"].values[ia] - e["dem_err_m"].values[ie]), tol["dh_rmse_m"])
    r.check("tcoh_median_absdiff", float(np.nanmedian(np.abs(a["temporal_coherence"].values[ia]
                                                            - e["temporal_coherence"].values[ie]))),
            tol["tcoh_median_absdiff"])
    return r
