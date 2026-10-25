"""Golden: native stripmap stack (Capella Mexico) + ps_lite must reproduce its reference.

CSK Hanoi is not a ps_lite case: its long multi-year X-band series is for the StaMPS engine (Phase 4).
"""
from pathlib import Path

import pytest

from tests.golden.golden import compare_points, expected_dir, load_case, run_case

pytestmark = [pytest.mark.golden, pytest.mark.slow]


@pytest.mark.parametrize("name", ["capella_mexico_native"])
def test_stripmap_native_matches_golden(name, tmp_path):
    case = load_case(name)
    exp = expected_dir(name)
    if exp is None or not (exp / "ps_run" / "points.parquet").exists():
        pytest.skip("no golden reference (set GEOEYES_TEST_DATA, run tests/golden/make_golden.py)")
    if not Path(case["input"]["scenes"]).exists():
        pytest.skip("input scenes not present")
    run_case(case, tmp_path)
    report = compare_points(exp / "ps_run", tmp_path / "ps_run", case["tolerance"])
    print(report)
    assert report.ok, str(report)
