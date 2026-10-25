import json

import numpy as np
import pytest

from geoeyes.controller.phases.build_stack import aoi_burst_ids
from geoeyes.core.errors import DataError
from geoeyes.core.types import BBox


def _burst(fid, lon0, lon1, lat0, lat1):
    return {"full_burst_id": fid, "footprint_wkt": f"POLYGON(({lon0} {lat0},{lon1} {lat0},{lon1} {lat1},{lon0} {lat1},"
                                                   f"{lon0} {lat0}))"}


def _ctx(tmp_path, per_month):
    from types import SimpleNamespace as NS

    from geoeyes.workspace import ProjectLayout
    return NS(cfg=NS(acquire=NS(max_per_month=per_month)), project=ProjectLayout(tmp_path / "p").ensure(),
              track_id="sentinel1-desc-091", cache={})


def test_max_per_month_applies_to_the_shared_archive(tmp_path):
    from datetime import date

    from geoeyes.controller.phase import ProjectState
    from geoeyes.controller.phases.build_stack import _per_month
    days = [date(2026, 1, d) for d in (1, 7, 13, 19, 25)] + [date(2026, 2, d) for d in (6, 12)]
    scenes = {d: tmp_path / str(d) for d in days}
    ctx = _ctx(tmp_path, 2)
    assert sorted(_per_month(ctx, scenes)) == [date(2026, 1, 1), date(2026, 1, 7), date(2026, 2, 6), date(2026, 2, 12)]
    # the dates the project's acquire phase selected win over the archive (another project added 01-07)
    ProjectState(ctx.project).set(ctx.track_id, "acquire", status="done",
                                  result={"dates": ["2026-01-01", "2026-01-13", "2026-02-06"]})
    assert sorted(_per_month(ctx, scenes)) == [date(2026, 1, 1), date(2026, 1, 13), date(2026, 2, 6)]
    assert _per_month(_ctx(tmp_path / "x", 0), scenes) == scenes


def test_orbit_upgrades_when_poeorb_is_published(tmp_path, monkeypatch):
    from datetime import date, timedelta
    from types import SimpleNamespace as NS

    from geoeyes.config.schema import Sensor
    from geoeyes.controller.phases import build_stack as bs
    from geoeyes.io.stack import StackStore
    from geoeyes.sensors.sentinel1 import orbits
    old, new = date.today() - timedelta(days=30), date.today() - timedelta(days=3)
    store = tmp_path / "stack.zarr"
    StackStore.create(store, coords={"date": np.array([old, new], "datetime64[D]")},
                      attrs={"orbit_per_date": {str(old): "RESORB", str(new): "RESORB"}})
    folder = lambda d: tmp_path / f"S1D_IW_SLC__1SDV_{d:%Y%m%d}T225017_{d:%Y%m%d}T225044_x"  # noqa: E731
    ctx = NS(track=NS(sensor=Sensor.SENTINEL1), workspace=NS(cache_dir=lambda k: tmp_path / k), cache={
        "stack": {"path": store, "scenes": {old: folder(old), new: folder(new)}, "reference": old}})
    found = []
    monkeypatch.setattr(orbits.PoeorbProvider, "find", lambda self, m, t0, t1, kind="POEORB": found.append(m) or "x")
    assert bs.orbit_upgrades(ctx) == [str(old)] and found == ["S1D"]     # a 3-day-old date is not even looked up

    """Shared archive (Hanoi S1, 2026-10): another project added IW1 bursts to three dates; taking every burst of
    the archive dropped 24 of 27 dates, the reference among them."""
    scene = tmp_path / "S1D_20260318"
    scene.mkdir()
    bursts = [_burst("091_194264_IW2", 105.4, 106.3, 21.0, 21.2), _burst("091_194265_IW2", 105.4, 106.3, 20.84, 21.03),
              _burst("091_194264_IW1", 106.3, 107.1, 21.0, 21.2), {"full_burst_id": "091_194266_IW3"}]
    (scene / "bursts.json").write_text(json.dumps(bursts))
    aoi = BBox.from_sequence([105.76, 20.97, 105.89, 21.07])
    assert aoi_burst_ids(scene, aoi) == ["091_194264_IW2", "091_194265_IW2", "091_194266_IW3"]   # no footprint: kept
    far = BBox.from_sequence([10.0, 45.0, 10.1, 45.1])
    (scene / "bursts.json").write_text(json.dumps(bursts[:3]))
    with pytest.raises(DataError, match="covers the AOI"):
        aoi_burst_ids(scene, far)
