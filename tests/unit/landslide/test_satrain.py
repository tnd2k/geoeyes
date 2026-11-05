"""IMERG archive: the index box, the cache encoding, and a year read once (only missing days read again)."""
from datetime import date

import numpy as np

from geoeyes.landslide import satrain as sr


def test_box_index_matches_cell_centres():
    i0, i1, j0, j1 = sr.box_index((105.5, 11.0, 110.0, 19.5))
    assert np.isclose(sr.LON0 + sr.RES * i0, 105.55) and np.isclose(sr.LON0 + sr.RES * i1, 109.95)
    assert np.isclose(sr.LAT0 + sr.RES * j0, 11.05) and np.isclose(sr.LAT0 + sr.RES * j1, 19.45)
    assert (i1 - i0 + 1, j1 - j0 + 1) == (45, 85)                 # the probe of 2026-11-03 read (1, 45, 85)


def test_gsmap_subset_lands_on_the_imerg_cells(monkeypatch):
    import gzip
    # a fake GSMaP file whose value (mm/h) encodes the cell: lat * 1000 + lon, stored north first
    lat = 59.95 - 0.1 * np.arange(1200)
    lon = 0.05 + 0.1 * np.arange(3600)
    a = (np.round(lat, 2)[:, None] * 1000 + np.round(lon, 2)[None, :]).astype("<f4")
    blob = gzip.compress(a.tobytes())

    class FakeFTP:
        def retrbinary(self, cmd, write):
            write(blob)

    monkeypatch.setattr(sr, "_gsmap_ftp", lambda: FakeFTP())
    idx = sr.box_index((105.5, 15.0, 105.8, 15.3))
    sub = sr.gsmap_read_day("gsmap_nrt", "x", idx) / 24.0
    i0, _, j0, _ = idx
    lat0, lon0 = sr.LAT0 + sr.RES * j0, sr.LON0 + sr.RES * i0
    assert np.isclose(sub[0, 0], round(lat0, 2) * 1000 + round(lon0, 2), atol=0.5)    # south-west cell
    assert sub[1, 0] > sub[0, 0]                                                        # rows go north


def test_encode_roundtrip():
    mm = np.array([[0.0, 12.34, np.nan, 7000.0]], np.float32)
    back = sr._decode(sr._encode(mm))
    assert np.isnan(back[0, 2]) and np.allclose(back[0, [0, 1, 3]], [0.0, 12.3, 6553.4])


def test_compare_scores_an_underestimating_product():
    rng = np.random.default_rng(0)
    days = [date(2020, 10, 1) + __import__("datetime").timedelta(d) for d in range(60)]
    ref = rng.gamma(0.5, 40.0, (60, 5, 5)).astype(np.float32)
    test = (0.6 * ref).astype(np.float32)                           # a product that sees 60 % of the rain
    lat, lon = np.arange(5.0), np.arange(5.0)
    r = sr.compare(sr.RainArchive("early", days, lat, lon, test), sr.RainArchive("final", days, lat, lon, ref))
    assert abs(r["ratio_totals"] - 0.6) < 1e-3 and r["corr"] > 0.999 and abs(r["p99_ratio"] - 0.6) < 1e-3
    t = r["thresholds"]["100"]
    assert t["pod"] < 1 and t["far"] == 0 and t["freq_bias"] < 1        # misses heavy days, no false alarms


def test_year_read_once_then_only_missing(tmp_path):
    box = (105.0, 15.0, 105.3, 15.2)
    i0, i1, j0, j1 = sr.box_index(box)
    shape = (j1 - j0 + 1, i1 - i0 + 1)
    calls = []

    def lister(run, year, month, s):
        import calendar
        return {date(year, month, d): f"g{month:02d}{d:02d}"
                for d in range(1, calendar.monthrange(year, month)[1] + 1)}

    def reader(run, name, idx, s):
        calls.append(name)
        if name == "g0305":
            return None                                             # one day the server cannot serve
        return np.full(shape, float(int(name[1:3])), np.float32)    # rain = the month number

    a = sr.year_archive("early", 2015, tmp_path, box, reader=reader, lister=lister, threads=2)
    assert len(a.dates) == 365 and a.missing_days() == [date(2015, 3, 5)]
    assert np.allclose(a.mm[a.dates.index(date(2015, 7, 1))], 7.0)
    n = len(calls)
    b = sr.year_archive("early", 2015, tmp_path, box, reader=reader, lister=lister, threads=2)
    assert calls[n:] == ["g0305"] and b.missing_days() == [date(2015, 3, 5)]


def test_storm_table_uses_the_core_box_only():
    lat = np.round(np.arange(13.95, 16.5, 0.1), 2)
    lon = np.round(np.arange(107.05, 109.0, 0.1), 2)
    mm = np.zeros((1, lat.size, lon.size), np.float32)
    mm[0, lat < 14.0, :] = 999.0                                  # outside the core: must be ignored
    mm[0, (lat > 15.0) & (lat < 15.1), (lon > 108.0) & (lon < 108.1)] = 300.0
    a = sr.RainArchive("early", [date(2020, 10, 28)], lat, lon, mm)
    t = sr.storm_table({"early": a})
    assert t["Molave 2020-10-28"]["early"]["max"] == 300.0
    assert t["Molave 2020-10-27"]["early"] is None
