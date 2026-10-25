from datetime import date

import pytest

from geoeyes.cli.main import build_parser, main
from geoeyes.config.loader import load_dict
from geoeyes.controller.pipeline import plan
from geoeyes.core.errors import PhaseError
from geoeyes.workspace import WorkspaceLayout


def project(tmp_path, **sections):
    ws = WorkspaceLayout.at(tmp_path / "ws")
    raw = tmp_path / "raw"
    for d in ("20240626", "20240629", "20240702", "20240705", "20240708"):
        (raw / d).mkdir(parents=True, exist_ok=True)
    data = {"project": {"name": "cap", "method": "ps_lite"},
            "tracks": [{"sensor": "capella", "direction": "ascending"}],
            "aoi": {"bbox": [-99.02, 19.34, -98.99, 19.37]}, "acquire": {"archive": str(raw)},
            "stack": {"engine": "native"}}
    data.update(sections)
    return load_dict(data), ws.project("cap").ensure(), ws


def step(p, name):
    return next(s for s in p.steps if s.phase.name == name)


def test_plan_new_project_runs_every_enabled_phase(tmp_path):
    cfg, prj, ws = project(tmp_path)
    p = plan(cfg, prj, ws)
    assert [(s.phase.name, s.action) for s in p.steps] == [
        ("acquire", "disabled"), ("build_stack", "run"), ("phase_linking", "disabled"), ("ps", "run"),
        ("build_product", "run"), ("export", "run"), ("report", "run")]
    from geoeyes.controller.phases.build_stack import target
    t = target(step(p, "build_stack").ctx)
    assert t["reference"] == date(2024, 7, 2)                                   # median date
    assert t["stack_id"] == "capella-asc-ref20240702" and len(t["scenes"]) == 5


def test_plan_blocks_with_reasons(tmp_path):
    cfg, prj, ws = project(tmp_path, stack={"engine": "snap"})
    assert step(plan(cfg, prj, ws), "build_stack").action == "blocked"
    cfg, prj, ws = project(tmp_path, acquire={"archive": str(tmp_path / "missing")})
    s = step(plan(cfg, prj, ws), "build_stack")
    assert s.action == "blocked" and "not found" in s.reason
    cfg, prj, ws = project(tmp_path, network={"reference": "2024-07-01"})
    assert "not an acquisition date" in step(plan(cfg, prj, ws), "build_stack").reason


def test_acquire_sentinel1_bursts(tmp_path, monkeypatch):
    from datetime import datetime

    from geoeyes.controller.phase import ProjectState
    from geoeyes.controller.phases import acquire as acq
    from geoeyes.sensors.sentinel1 import asf
    tracks = [{"sensor": "sentinel1", "direction": "ascending", "relative_orbit": 78}]
    psi = {"name": "cap", "method": "psi"}
    cfg, prj, ws = project(tmp_path, project=psi, tracks=tracks, acquire={})
    assert step(plan(cfg, prj, ws), "acquire").action == "disabled"           # no date_range: archive as is
    cfg, prj, ws = project(tmp_path, project=psi, tracks=tracks,
                           acquire={"date_range": ["2024-05-01", "2024-06-30"]})

    def ref(d, n):
        return asf.BurstRef(file_id=f"S1_1_IW3_{d:%Y%m%d}_VV_{n}-BURST", full_burst_id="078_165499_IW3",
                            relative_burst_id=165499, subswath="IW3", burst_index=n, polarization="VV",
                            start=datetime.combine(d, datetime.min.time()), slc_name=f"SLC_{d:%Y%m%d}",
                            relative_orbit=78, absolute_orbit=1, direction=cfg.tracks[0].direction,
                            platform="Sentinel-1A", data_url="", metadata_url="", bytes=1, footprint_wkt="")

    days = [date(2024, 5, 3), date(2024, 5, 15), date(2024, 5, 27), date(2024, 6, 8)]
    online = {"up": True}

    def fake_search(**kw):
        if not online["up"]:
            raise ConnectionError("offline")
        return [ref(d, 1) for d in days]
    monkeypatch.setattr(asf, "burst_ids_for_aoi", lambda *a, **k: ["078_165499_IW3"])
    monkeypatch.setattr(asf, "search", fake_search)
    s = step(plan(cfg, prj, ws), "acquire")
    assert s.action == "run" and len(acq.catalogue(s.ctx)) == 4
    assert {r.date for r in acq._thin(acq.catalogue(s.ctx), 2)} == {date(2024, 5, 3), date(2024, 5, 15),
                                                                     date(2024, 6, 8)}
    fp = acq.fingerprint(s.ctx)
    ProjectState(prj).set(s.ctx.track_id, "acquire", status="done", fingerprint=fp,
                          result={"dates": [str(d) for d in days[:3]]})
    s = step(plan(cfg, prj, ws), "acquire")
    assert acq.changes(s.ctx) == "1 new acquisition(s) on ASF: 2024-06-08"
    online["up"] = False                                                       # offline: last catalogue
    s = step(plan(cfg, prj, ws), "acquire")
    assert s.action == "up-to-date"


def _mark_built(ctx):
    """Pretend build_stack completed: stack store with its fingerprint + state record (as the runner writes)."""
    import numpy as np

    from geoeyes.controller.phase import ProjectState
    from geoeyes.controller.phases import build_stack as bs
    from geoeyes.io.stack import StackStore
    t = bs.target(ctx)
    fp = bs.fingerprint(ctx)
    st = StackStore.create(t["path"], coords={"date": np.array(list(t["scenes"]), "datetime64[D]")},
                           attrs={bs.FINGERPRINT_ATTR: fp}, overwrite=True)
    ProjectState(ctx.project).set(ctx.track_id, "build_stack", status="done", fingerprint=fp,
                                  result={"reference": str(t["reference"]), "signatures": bs.signatures(ctx)})
    return st


def test_new_or_changed_data_triggers_the_phases_again(tmp_path):
    cfg, prj, ws = project(tmp_path)
    _mark_built(plan(cfg, prj, ws, only=["build_stack"]).steps[0].ctx)
    p = plan(cfg, prj, ws, only=["build_stack"])
    assert p.steps[0].action == "up-to-date"
    for d in ("20240711", "20240714"):                                         # new acquisitions
        (tmp_path / "raw" / d).mkdir()
    p = plan(cfg, prj, ws)
    assert [s.action for s in p.steps] == ["disabled", "run", "disabled", "run", "run", "run", "run"]
    assert step(p, "build_stack").reason == "2 new scene(s): 2024-07-11, 2024-07-14"
    from geoeyes.controller.phases.build_stack import target
    assert target(step(p, "build_stack").ctx)["reference"] == date(2024, 7, 2)  # kept (the median is now 07-05)
    _mark_built(step(p, "build_stack").ctx)
    (tmp_path / "raw" / "20240629" / "product.tif").write_bytes(b"x" * 10)     # a re-delivered scene
    assert plan(cfg, prj, ws, only=["build_stack"]).steps[0].reason == "1 changed scene(s): 2024-06-29"


def test_incremental_build_reuses_unchanged_dates_only_with_the_same_reference(tmp_path):
    import numpy as np

    from geoeyes.controller.phases import build_stack as bs
    cfg, prj, ws = project(tmp_path)
    ctx = plan(cfg, prj, ws, only=["build_stack"]).steps[0].ctx
    st = _mark_built(ctx)
    st.update_attrs(**{bs.SIGNATURES_ATTR: bs.signatures(ctx)})
    assert bs.reusable(ctx) == set()                                            # no slc yet
    st.write("slc", np.zeros((5, 1, 1), np.complex64), ("date", "y", "x"))
    raw = tmp_path / "raw"
    (raw / "20240711").mkdir()
    (raw / "20240629" / "product.tif").write_bytes(b"x")                        # re-delivered
    p = plan(cfg, prj, ws, only=["build_stack"])
    keep = bs.reusable(p.steps[0].ctx)
    assert keep == {date(2024, 6, 26), date(2024, 7, 2), date(2024, 7, 5), date(2024, 7, 8)}
    assert p.steps[0].reason.endswith("incremental: 4 coregistered date(s) kept")
    (raw / "20240702" / "product.tif").write_bytes(b"x")                        # the reference changed
    assert bs.reusable(plan(cfg, prj, ws, only=["build_stack"]).steps[0].ctx) == set()
    cfg2, prj, ws = project(tmp_path, network={"reference": "2024-07-05"})      # other master: other store
    assert bs.reusable(plan(cfg2, prj, ws, only=["build_stack"]).steps[0].ctx) == set()


def test_reuse_requires_same_reference_and_window(tmp_path):
    import numpy as np

    from geoeyes.io.stack import StackStore
    from geoeyes.processing.stack.native.reuse import Reuse
    dates = [date(2024, 1, 1), date(2024, 1, 13), date(2024, 1, 25)]
    st = StackStore.create(tmp_path / "s.zarr", coords={"date": np.array(dates, "datetime64[D]")},
                           attrs={"reference_date": "2024-01-13", "crop_rows": [0, 4], "crop_samples": [2, 6]})
    st.write("slc", np.arange(3, dtype=np.complex64)[:, None, None] * np.ones((3, 4, 4)), ("date", "y", "x"))
    st.write("bperp", np.array([10.0, 0.0, -5.0], np.float32), ("date",))
    r = Reuse.open(st, {dates[0], dates[2]}, dates[1], (0, 4, 2, 6))
    assert dates[2] in r and dates[1] not in r
    assert r.block("slc", dates[2])[0, 0] == 2 and r.value("bperp", dates[0]) == 10.0
    assert r.value("esd_shift", dates[0]) == 0.0
    assert Reuse.open(st, {dates[0]}, dates[0], (0, 4, 2, 6)) is None          # other reference
    assert Reuse.open(st, {dates[0]}, dates[1], (0, 5, 2, 6)) is None          # other window


def test_plan_selection(tmp_path):
    cfg, prj, ws = project(tmp_path)
    assert [s.phase.name for s in plan(cfg, prj, ws, only=["ps"]).steps] == ["ps"]
    assert [s.phase.name for s in plan(cfg, prj, ws, to="phase_linking").steps] == [
        "acquire", "build_stack", "phase_linking"]
    assert plan(cfg, prj, ws, tracks=["other"]).steps == []
    with pytest.raises(PhaseError):
        plan(cfg, prj, ws, only=["unwrap"])


def test_cli_parser_and_plan(tmp_path, capsys):
    cfg, prj, ws = project(tmp_path)
    from geoeyes.config.loader import dump
    dump(cfg, prj.config)
    a = build_parser().parse_args(["--workspace", str(ws.root), "run", "cap", "--only", "ps", "--force", "ps"])
    assert a.only == "ps" and a.force == ["ps"] and a.project == "cap"
    assert main(["--workspace", str(ws.root), "plan", "cap"]) == 0
    out = capsys.readouterr().out
    assert "capella-asc/build_stack" in out and "5 phase(s) to run" in out
    assert main(["--workspace", str(ws.root), "status", "cap"]) == 0
