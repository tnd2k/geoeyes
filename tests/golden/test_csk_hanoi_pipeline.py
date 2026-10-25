"""Golden: the COSMO-SkyMed production chain (native stripmap stack, phase linking, ps engine, product) on central
Hanoi must reproduce its reference."""
import tomllib
from pathlib import Path

import pandas as pd
import pytest

from tests.golden.golden import CASES, compare_points, expected_dir, load_case, run_case

CASE = "csk_hanoi_pipeline"

pytestmark = [pytest.mark.golden, pytest.mark.slow]


def test_csk_hanoi_pipeline_matches_golden(tmp_path):
    case = load_case(CASE)
    exp = expected_dir(CASE)
    if exp is None or not (exp / "ps_run" / "points.parquet").exists():
        pytest.skip("no golden reference (set GEOEYES_TEST_DATA, run tests/golden/make_golden.py)")
    raw = tomllib.loads((CASES / case["input"]["config"]).read_text(encoding="utf-8"))
    if not Path(raw["acquire"]["archive"]).exists():
        pytest.skip("CSK scenes not present")
    run_case(case, tmp_path)
    report = compare_points(exp / "ps_run", tmp_path / "ps_run", case["tolerance"])
    # the product too: same points, same velocities (the product adds statistics, not processing)
    e = pd.read_parquet(exp / "product" / "points.parquet", columns=["point_uid", "vel_los_mm_yr"])
    a = pd.read_parquet(tmp_path / "product" / "points.parquet", columns=["point_uid", "vel_los_mm_yr"])
    m = e.merge(a, on="point_uid", suffixes=("_e", "_a"))
    report.check("product_matched_frac", len(m) / max(len(e), 1), case["tolerance"]["match_min_frac"], below=False)
    report.check("product_vel_max_absdiff", float((m["vel_los_mm_yr_a"] - m["vel_los_mm_yr_e"]).abs().max()),
                 case["tolerance"]["vel_rmse_mm_yr"])
    print(report)
    assert report.ok, str(report)
