"""Golden: native Sentinel-1 burst stack + ps_lite over Mexico City must reproduce the stored reference."""
from pathlib import Path

import pytest

from tests.golden.golden import compare_points, expected_dir, load_case, run_case

CASE = "s1_mexico_native"

pytestmark = [pytest.mark.golden, pytest.mark.slow]


def test_s1_mexico_native_matches_golden(tmp_path):
    case = load_case(CASE)
    exp = expected_dir(CASE)
    if exp is None or not (exp / "ps_run" / "points.parquet").exists():
        pytest.skip("no golden reference (set GEOEYES_TEST_DATA, run tests/golden/make_golden.py)")
    if not Path(case["input"]["archive"]).exists():
        pytest.skip("S1 burst archive not present")
    run_case(case, tmp_path)
    report = compare_points(exp / "ps_run", tmp_path / "ps_run", case["tolerance"])
    print(report)
    assert report.ok, str(report)
