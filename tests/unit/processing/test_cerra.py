"""CERRA: the Lambert grid (which points it covers), the 3-hourly time bracket, and the delays of a synthetic
atmosphere on the Lambert grid equal to those of the same atmosphere on a lat/lon grid (ERA5 path)."""
from datetime import date, datetime
from pathlib import Path

import numpy as np

from geoeyes.processing.atmosphere import cerra
from geoeyes.processing.atmosphere.era5 import _bracket
from geoeyes.processing.atmosphere.era5.delays import grid_delays
from geoeyes.processing.atmosphere.models import catalogue


def test_domain():
    assert cerra.covers([-16.64], [28.27])                      # Teide (75 cells from the western edge)
    assert cerra.covers([2.35, 24.9], [48.85, 60.2])            # Paris, Helsinki
    assert not cerra.covers([105.8], [21.0])                    # Hanoi
    assert not cerra.covers([-99.1], [19.4])                    # Mexico City
    c, r = cerra.to_grid([8.0], [50.0])                         # projection centre = grid centre
    assert abs(c[0] - (cerra.N - 1) / 2) < 0.6 and abs(r[0] - (cerra.N - 1) / 2) < 0.6
    ring = np.asarray(cerra.outline())
    assert ring[:, 1].min() < 22 and ring[:, 1].max() > 72


def test_bracket_three_hours():
    a, b, w = _bracket(datetime(2026, 2, 11, 2, 13), 3)
    assert a == (datetime(2026, 2, 11).date(), 0) and b == (datetime(2026, 2, 11).date(), 3)
    assert abs(w - 133 / 180) < 1e-9
    a, b, w = _bracket(datetime(2026, 2, 11, 22, 30), 3)
    assert a[1] == 21 and b == (datetime(2026, 2, 12).date(), 0) and abs(w - 0.5) < 1e-9
    assert _bracket(datetime(2026, 2, 11, 2, 13)) [2] == 13 / 60      # ERA5 hourly as before


def test_catalogue():
    rows = {m["key"]: m for m in catalogue([-16.66, -16.62], [28.25, 28.29], [datetime(2026, 2, 11).date()],
                                           today=datetime(2026, 10, 29).date())}
    assert rows["era5"]["usable"] and rows["cerra"]["usable"]
    assert rows["gacos"]["access"] == "manual" and not rows["gacos"]["usable"]
    hanoi = {m["key"]: m for m in catalogue([105.8], [21.0], [datetime(2026, 9, 1).date()],
                                            today=datetime(2026, 10, 29).date())}
    assert not hanoi["cerra"]["covers_area"] and not hanoi["cerra"]["usable"]
    assert hanoi["era5"]["usable"]


def _atmosphere(lat):
    """(T, RH, geopotential) of a standard-ish atmosphere at 10 levels, varying with latitude only."""
    levels = np.array([1000, 950, 900, 850, 800, 700, 600, 500, 300, 100], np.float64)
    z = 7400.0 * np.log(1013.0 / levels) * 9.80665
    t = 288.0 - 6.5e-3 * z / 9.80665 + 0.0 * lat
    rh = np.clip(80.0 - 0.006 * z / 9.80665 + 0.5 * (lat - 28.0), 1, 100)
    return t, rh, np.broadcast_to(z, t.shape), levels


def test_lambert_delays_match_latlon():
    lon_p, lat_p, h = np.array([-16.65, -16.63]), np.array([28.26, 28.28]), np.array([2100.0, 3500.0])
    # lat/lon grid (ERA5 path)
    lats, lons = np.arange(27.5, 29.01, 0.25), np.arange(-17.5, -15.99, 0.25)
    lg = np.broadcast_to(lats[:, None], (lats.size, lons.size))
    t, rh, z, levels = _atmosphere(lg[..., None])
    ref = grid_delays(t, rh, z, levels, lats, lons, lg, lat_p, lon_p, h, np.zeros(2, bool))
    # the same field sampled on the CERRA cells around the points
    c, r = cerra.to_grid(lon_p, lat_p)
    cols, rows = np.arange(int(c.min()) - 3, int(c.max()) + 4), np.arange(int(r.max()) + 3, int(r.min()) - 4, -1)
    gx, gy = np.meshgrid(cerra.X0 + (cols + 0.5) * cerra.DX, cerra.Y0 - (rows + 0.5) * cerra.DX)
    lat_cells = cerra._transformer(inverse=True).transform(gx, gy)[1]
    t2, rh2, z2, _ = _atmosphere(lat_cells[..., None])
    got = grid_delays(t2, rh2, z2, levels, -rows.astype(float), cols.astype(float), lat_cells, -r, c, h,
                      np.zeros(2, bool))
    for a, b in zip(got, ref, strict=True):
        np.testing.assert_allclose(a, b, rtol=2e-3)
    assert np.all(ref[0] > 1.0) and np.all(ref[0] < 2.5)        # hydrostatic delay above 2-3.5 km: 1.5-1.9 m


class _Remote:
    def __init__(self, rid, states):
        self.request_id, self._states = rid, list(states)

    @property
    def status(self):
        return self._states.pop(0) if len(self._states) > 1 else self._states[0]

    def download(self, target):
        Path(target).write_bytes(b"GRIB")


class _Client:
    def __init__(self, states):
        self.states, self.submitted, self.remotes = states, [], {}

    def submit(self, dataset, request):
        r = _Remote(f"id{len(self.submitted)}", self.states)
        self.submitted.append(request)
        self.remotes[r.request_id] = r
        return r

    def get_remote(self, rid):
        return self.remotes[rid]


def test_queued_request_is_kept_for_the_next_run(tmp_path):
    k = (date(2026, 2, 11), 3)
    client = _Client(["accepted"])
    got = cerra.download_all(tmp_path, [k], max_wait_min=0, poll_s=0, client=client)
    assert got == {} and cerra._load_pending(tmp_path) == {"20260211_03": "id0"}
    client.remotes["id0"]._states = ["successful"]        # ready by the next run: collected, not asked again
    got = cerra.download_all(tmp_path, [k], max_wait_min=0, poll_s=0, client=client)
    assert len(client.submitted) == 1 and got[k].read_bytes() == b"GRIB"
    assert cerra._load_pending(tmp_path) == {}
