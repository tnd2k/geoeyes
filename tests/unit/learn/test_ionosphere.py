"""Principles, chapter 6 (geoeyes.learn.ionosphere): per-date ionospheric gradients in mm/km, subswath steps, local
time, and the preview of the removed phase."""
import math

import numpy as np
import pytest

from geoeyes.io.stack import StackStore
from geoeyes.learn import ionosphere as iono

LAM = 0.0555


def _stack(tmp_path, with_iono=True):
    dates = np.array(["2025-10-04", "2025-10-16"], dtype="datetime64[ns]")
    ny, nx = 128, 256
    attrs = {"reference_date": "2025-10-04", "wavelength_m": LAM, "azimuth_pixel_spacing_m": 14.0,
             "range_pixel_spacing_m": 2.33, "track": "sentinel1-asc-128", "pass_direction": "ascending",
             "crop_samples": [1000, 1000 + nx], "subswath_columns": {"IW2": [0, 1100], "IW3": [1100, 5000]},
             "sensing_mid_utc": {"2025-10-04": "2025-10-04T11:06:33", "2025-10-16": "2025-10-16T11:06:33"}}
    if with_iono:
        attrs |= {"ionosphere": "split_spectrum", "ionosphere_model": "local",
                  "ionosphere_per_date": {"2025-10-16": {"rad_per_km_az_rg": [-0.2, 0.1], "se_rad_per_km_az_rg":
                                                         [0.02, 0.01], "kept": 4000}},
                  "subswath_phase_offsets": {"2025-10-16": {"anchor": "IW3", "IW3": {"rad": -2.2, "consistency": 0.9,
                                                                                      "blocks": 32}}}}
    s = StackStore.create(tmp_path / "stack.zarr", coords={"date": dates, "y": np.arange(ny), "x": np.arange(nx)},
                          attrs=attrs)
    y, x = np.mgrid[0:ny, 0:nx].astype(np.float32)
    for k, v in {"lon": 105.8 + 0 * x, "lat": 21.0 + 0 * x, "incidence": 40 + 0 * x}.items():
        s.write(f"geometry_{k}", v, ("y", "x"))
    s.write("esd_shift", np.array([0.0, 0.012]), ("date",))
    if with_iono:
        s.write("iono", np.stack([0 * x, 0.01 * x]), ("date", "y", "x"))
    return tmp_path / "stack.zarr"


def test_summary_per_date(tmp_path):
    s = iono.summary(_stack(tmp_path))
    k = LAM * 1000 / (4 * math.pi)
    assert s["seams"] == [{"col": 100, "subswath": "IW3"}] and s["ionosphere"] == "split_spectrum"
    d0, d1 = s["dates"]
    assert d0["iono_mm_per_km"] is None and d0["seam_rad"] is None           # the reference date
    assert d1["iono_mm_per_km"] == pytest.approx([-0.2 * k, 0.1 * k], abs=1e-3)
    assert d1["seam_rad"] == {"IW3": -2.2} and d1["esd_lines"] == pytest.approx(0.012)
    assert d1["local_hour"] == pytest.approx(11.11 + 105.8 / 15, abs=0.01)    # 18:10 local


def test_field_preview_and_stack_without_ionosphere(tmp_path):
    f = iono.field(_stack(tmp_path / "a"), "2025-10-16")
    assert f["shape"] == [64, 64] and abs(float(np.median(f["mm"]))) < 0.1
    s = iono.summary(_stack(tmp_path / "b", with_iono=False))
    assert s["ionosphere"] == "none" and not s["has_field"]
    with pytest.raises(FileNotFoundError):
        iono.field(tmp_path / "b" / "stack.zarr", "2025-10-16")
