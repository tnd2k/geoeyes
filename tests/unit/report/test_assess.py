"""Assessment part of the report (geoeyes.report.assess): areas and hot spots on cells, the trend of a series, the
analyses read when they exist (said when they do not), the standardised indicators."""
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from geoeyes.report import assess


def _pts(seed=0):
    """6 × 6 km of points, stable but for a 1 km sinking bowl (-20 mm/yr vertical) at its centre; l_u = 0.8."""
    rng = np.random.default_rng(seed)
    n = 40_000
    lon, lat = 105.80 + rng.uniform(0, 0.058, n), 21.00 + rng.uniform(0, 0.054, n)
    x, y = (lon - 105.829) * 104_000, (lat - 21.027) * 110_540
    vert = np.where(np.hypot(x, y) < 500, -20.0, 0.0) + rng.normal(0, 1, n)
    return pd.DataFrame({"point_uid": [f"p{i}" for i in range(n)], "lon": lon, "lat": lat,
                         "vel_los_mm_yr": 0.8 * vert, "vel_std_mm_yr": np.full(n, 0.8), "los_u": np.full(n, 0.8)})


def _dates(n=30, step=12):
    return [str(date(2025, 1, 1) + timedelta(days=step * i)) for i in range(n)]


def test_rates_are_vertical_with_the_line_of_sight():
    pts = _pts()
    v, sd, basis = assess.rates(pts)
    assert basis == "vertical" and np.allclose(v, pts["vel_los_mm_yr"] / 0.8) and np.allclose(sd, 1.0)
    assert assess.rates(pts.drop(columns="los_u"))[2] == "los"


def test_areas_and_one_sinking_hot_spot():
    pts = _pts()
    v, _, _ = assess.rates(pts)
    lon, lat = pts["lon"].to_numpy(), pts["lat"].to_numpy()
    cells, inv = assess.grid(lon, lat, v)
    ar = assess.areas(cells)
    bowl = np.pi * 0.5 ** 2                                            # km²
    assert abs(ar["sinking_10"] - bowl) < 0.25 * bowl and ar["sinking_20"] < ar["sinking_10"]
    assert ar["rising_5"] == 0 and ar["stable_km2"] > 0.8 * ar["counted_km2"]
    hot = assess.hotspots(cells, inv, lon, lat, v, 5.0)
    assert [h["kind"] for h in hot] == ["sinking"] and hot[0]["id"] == "H1"
    h = hot[0]
    assert abs(h["rate_mm_yr"] + 20) < 1.5 and abs(h["lon"] - 105.829) < 0.002 and abs(h["lat"] - 21.027) < 0.002


def test_trend_kinds():
    d = _dates()
    t = np.arange(30) * 12 / 365.25
    assert assess.trend(d, -10 * t)["kind"] == "steady"
    acc = assess.trend(d, -5 * t - 15 * t ** 2)
    assert acc["kind"] == "accelerating" and acc["rate_second_mm_yr"] < acc["rate_first_mm_yr"]
    assert assess.trend(d, -20 * t + 8 * t ** 2)["kind"] == "slowing"
    season = assess.trend(d, -5 * t + 6 * np.sin(2 * np.pi * t))
    assert season["kind"] == "seasonal" and abs(season["seasonal_amp_mm"] - 6) < 1
    assert assess.trend(d[:4], [0, 1, 2, 3])["kind"] == "unknown"
    rng = np.random.default_rng(2)
    spiky = -10 * t + rng.normal(0, 1, 30)
    spiky[[20, 28]] -= 40                                          # two images off (atmosphere): not a speed-up
    tr = assess.trend(d, spiky)
    assert tr["kind"] == "steady" and tr["outliers"] == [d[20], d[28]] and abs(tr["rate_mm_yr"] + 10) < 1.5


def _data(tmp_path, pts):
    product = tmp_path / "projects" / "demo" / "products" / "demo_s1_v1"
    product.mkdir(parents=True)
    a = {"first": "2025-01-01", "last": "2025-12-27", "span_days": 360, "n_dates": 30}
    return product, {"product_id": product.name, "project": "demo", "track": "s1", "generated": "now",
                     "bbox": [105.8, 21.0, 105.86, 21.06], "description": "", "acquisition": a,
                     "stats": {"n_points": len(pts), "area_km2": 36.0, "density_per_km2": 1111},
                     "confidence": {"level": "medium", "plain": ["less than a year of images"]},
                     "qc": [], "qc_summary": {"pass": 0, "borderline": 0, "review": 0, "info": 0}}


def _wide(pts, dates):
    def wide_of(uids):
        v = pts.set_index("point_uid").loc[list(uids), "vel_los_mm_yr"].to_numpy()
        t = np.arange(len(dates)) * 12 / 365.25
        return pd.DataFrame(v[:, None] * t[None, :], index=list(uids), columns=pd.to_datetime(dates))
    return wide_of


def test_assess_says_what_was_not_run_and_indicators_keep_their_keys(tmp_path):
    pts = _pts()
    product, data = _data(tmp_path, pts)
    asm = assess.assess(data, pts, product, _wide(pts, _dates()))
    imp = asm["impacts"]
    for k in ("hazard", "behaviour", "buildings", "lines", "floods", "groundwater", "gnss"):
        assert imp[k]["assessed"] is False and imp[k]["run"].startswith("geoeyes ")
    assert f"geoeyes hazard demo --product {product.name}" == imp["hazard"]["run"]
    h = asm["hotspots"][0]
    assert h["trend"]["kind"] == "steady" and abs(h["trend"]["rate_mm_yr"] + 20) < 2 and h["label"].endswith("E")
    assert any("sinks faster than 5 mm per year" in s for s in asm["statements"])
    data["assessment"] = asm
    ind = assess.indicators(data, asm)
    assert list(ind["indicators"]) == list(assess.INDICATORS) and ind["velocity_basis"] == "vertical"
    x = ind["indicators"]
    assert x["hotspots_sinking_n"]["value"] == 1 and x["area_sinking_over_10_mm_yr_km2"]["value"] > 0.5
    assert x["hazard_subsidence_high_km2"]["value"] is None and x["hazard_subsidence_high_km2"]["source"] == "not assessed"
    json.dumps(ind, allow_nan=False)


def test_assess_reads_the_analyses_that_exist(tmp_path):
    pts = _pts()
    product, data = _data(tmp_path, pts)
    an = product.parent.parent / "analyses"
    hz = an / "hazard" / product.name
    hz.mkdir(parents=True)
    levels = {lv: {"cells": c, "km2": c / 100} for lv, c in zip(assess.LEVELS, (3000, 50, 20, 7, 0), strict=True)}
    (hz / "hazard.json").write_text(json.dumps({
        "params": {"cell_m": 100}, "by_level": {"subsidence": levels | {"not assessed": 0},
                                                "landslide": {lv: {"cells": 0, "km2": 0} for lv in assess.LEVELS}},
        "coupling": {"assessed": True, "cells_tested": 3077, "cells_significant": 12, "lag_months_median": 2.0},
        "accelerating_cells": 4, "groundwater": {"used": False, "reason": "no EARTHDATA_TOKEN"}}))
    bh = an / "behaviour" / product.name
    bh.mkdir(parents=True)
    (bh / "behaviour.json").write_text(json.dumps({"counts": {"stable": 3000, "steady": 70, "speeding": 7}}))
    asm = assess.assess(data, pts, product, _wide(pts, _dates()))
    imp = asm["impacts"]
    assert imp["hazard"]["assessed"] and imp["hazard"]["high_km2"] == 0.07 and list(imp["hazard"]["by_level"]) == [
        "subsidence"]
    assert imp["groundwater"]["assessed"] is False and imp["groundwater"]["why"] == "no EARTHDATA_TOKEN"
    assert imp["behaviour"]["assessed"] and any("speeding up" in t for t in imp["behaviour"]["text"])
    data["assessment"] = asm
    x = assess.indicators(data, asm)["indicators"]
    assert x["hazard_subsidence_moderate_km2"]["value"] == 0.2 and x["hazard_accelerating_cells_n"]["value"] == 4
    assert x["motion_speeding_cells_n"]["value"] == 7 and x["motion_onset_cells_n"]["value"] is None
    assert any("hazard zones" in r["text"] for r in asm["recommendations"])
