"""Open-data hub: item normalisation, stack grouping and ids, AOI filters, the ICEYE crop window (offline)."""
import json
from pathlib import Path

import numpy as np
import pytest

from geoeyes.opendata import find_stacks, search
from geoeyes.opendata.sources import SOURCES

META = Path(__file__).parents[1] / "sensors" / "data" / "ICEYE_ETH0SK_20260219T021322Z_8871777_X53_SM_SLC.json"


def _scene(day: int, *, source="iceye", platform="iceye-x53", inc=25.9, dx=0.0, orbit="ascending", track="",
           mode="stripmap"):
    w, s = -16.9 + dx, 27.95
    ring = [[w, s], [w + 0.4, s], [w + 0.4, s + 0.6], [w, s + 0.6], [w, s]]
    return {"source": source, "id": f"{source}-{day}", "item": f"https://x/{source}/{day}.json",
            "datetime": f"2026-02-{day:02d}T02:13:00Z", "date": f"2026-02-{day:02d}", "platform": platform,
            "mode": mode, "orbit_state": orbit, "look": "right", "incidence": inc, "look_azimuth": 259.0,
            "polarization": "VV", "track": track, "bbox": [w, s, w + 0.4, s + 0.6], "footprint": ring,
            "product": "SLC-COG", "slc": "", "meta": ""}


def test_iceye_item_normalised():
    item = json.loads(META.read_text())
    item["assets"]["slc-cog"] = {"href": "x_SLC.tif"}
    rec = SOURCES["iceye"].normalize(item, "https://bucket/data/scene/x_SLC.json")
    assert rec["platform"] == "iceye-x53" and rec["mode"] == "stripmap" and rec["orbit_state"] == "ascending"
    assert rec["slc"] == "https://bucket/data/scene/x_SLC.tif" and rec["date"] == "2026-02-19"
    assert rec["footprint"][0] == rec["footprint"][-1] and len(rec["bbox"]) == 4
    item["assets"].pop("slc-cog")
    assert SOURCES["iceye"].normalize(item, "https://bucket/x.json") is None     # GRD-only item: not indexed


def test_stacks_group_by_geometry_and_platform():
    scenes = [_scene(d) for d in range(11, 17)]
    scenes += [_scene(d, inc=26.3, dx=0.05) for d in (17, 18)]                   # other beam, still the stack
    scenes += [_scene(d, platform="iceye-x2") for d in (11, 12, 13)]             # other satellite
    scenes += [_scene(d, orbit="descending") for d in (11, 12)]                  # too few dates
    scenes += [_scene(d, inc=35.0) for d in (20, 21, 22)]                        # other incidence
    st = find_stacks(scenes)
    assert [s["n_dates"] for s in st] == [8, 3, 3]
    assert st[0]["id"] == "iceye:x53-sm-ar-26-28.2n016.7w" and st[0]["median_gap_days"] == 1
    assert len({s["id"] for s in st}) == 3 and st[0]["supported"]


def test_capella_track_groups_satellites_and_names_track():
    scenes = [_scene(d, source="capella", platform=f"capella-{13 + d % 2}", track="606_53.1_44") for d in (1, 4, 7)]
    scenes += [_scene(d, source="capella", platform="capella-13", track="700_1") for d in (2, 5, 8)]
    st = find_stacks(scenes)
    assert len(st) == 2 and {s["n_dates"] for s in st} == {3}
    assert st[0]["id"] != st[1]["id"] and all("-t" in s["id"] for s in st)
    assert sorted(st[0]["platforms"] + st[1]["platforms"]).count("capella-13") == 2


def test_aoi_filter_keeps_the_id():
    scenes = [_scene(d) for d in range(11, 16)] + [_scene(d, dx=0.3) for d in (16, 17)]
    full = find_stacks(scenes, incidence_tol=5, min_overlap=0.2)[0]
    inside = find_stacks(scenes, aoi=(-16.85, 28.0, -16.8, 28.1), incidence_tol=5, min_overlap=0.2)[0]
    assert inside["id"] == full["id"] and inside["n_dates"] == 5 and full["n_dates"] == 7
    assert find_stacks(scenes, aoi=(10, 10, 11, 11)) == []


def test_search_filters():
    scenes = [_scene(d) for d in range(11, 16)]
    assert len(search(scenes, start="2026-02-12", end="2026-02-14")) == 3
    assert len(search(scenes, bbox=(-16.8, 28.0, -16.7, 28.1), covers=True)) == 5
    assert search(scenes, bbox=(0, 0, 1, 1)) == [] and search(scenes, mode="spotlight") == []


def test_iceye_window_holds_the_aoi_at_both_heights():
    from geoeyes.opendata.fetch import iceye_window
    from geoeyes.sensors.iceye.slc_cog import rpc_to_tiff
    p = json.loads(META.read_text())["properties"]
    aoi = (-16.68, 28.24, -16.60, 28.30)
    r0, r1, c0, c1 = iceye_window(p, aoi, (2000.0, 3800.0), 500.0)
    for h in (2000.0, 3800.0):
        r, c = rpc_to_tiff(p, np.array([aoi[1], aoi[3]]), np.array([aoi[0], aoi[2]]), np.full(2, h))
        assert (r0 < r).all() and (r < r1).all() and (c0 < c).all() and (c < c1).all()
    assert 0 <= r0 < r1 <= 18032 and 0 <= c0 < c1 <= 44840
    from geoeyes.core.errors import DataError
    with pytest.raises(DataError):
        iceye_window(p, (10.0, 10.0, 10.1, 10.1), (0.0, 0.0), 0.0)


def test_walk_follows_children_and_items():
    from geoeyes.opendata.crawl import walk
    tree = {"https://h/c.json": {"links": [{"rel": "child", "href": "y/c.json"}, {"rel": "item", "href": "a.json"}]},
            "https://h/y/c.json": {"links": [{"rel": "item", "href": "./b.json"}, {"rel": "parent", "href": "../c.json"},
                                             {"rel": "child", "href": "../c.json"}]}}

    class S:
        def get(self, url, timeout):
            class R:
                def raise_for_status(self):
                    if url not in tree:
                        raise __import__("requests").HTTPError(url)

                def json(self):
                    return tree[url]
            return R()

    assert walk(["https://h/c.json"], S(), workers=2) == ["https://h/a.json", "https://h/y/b.json"]


def test_acquire_opendata_config():
    from geoeyes.config.loader import load_dict
    from geoeyes.core.errors import ConfigError
    base = {"schema": "geoeyes.project/1", "project": {"name": "t", "method": "psi"},
            "aoi": {"bbox": [-16.68, 28.24, -16.6, 28.3]}, "tracks": [{"sensor": "iceye", "direction": "ascending"}]}
    cfg = load_dict({**base, "acquire": {"opendata": "iceye:x53-sm-ar-26-28.2n016.7w"}})
    assert cfg.acquire.opendata.startswith("iceye:") and cfg.network.max_perp_m == 1000.0     # ICEYE preset
    assert cfg.tracks[0].track_id == "iceye-asc"
    with pytest.raises(ConfigError):
        load_dict({**base, "acquire": {"opendata": "no-source"}})


def test_place_label_and_stale(tmp_path):
    from geoeyes.io.manifest import atomic_write_json
    from geoeyes.opendata.index import stale
    from geoeyes.opendata.places import key, label
    from geoeyes.workspace import WorkspaceLayout
    assert label({"county": "Los Angeles", "state": "California", "country": "United States"}) ==         "Los Angeles, California, United States"
    assert label({"county": "Hawaii", "state": "Hawaii", "country": "United States"}) == "Hawaii, United States"
    assert label({"city": "Ciudad de México", "country": "Mexico"}) == "Ciudad de México, Mexico" and label({}) == ""
    assert key(28.239, -16.679) == "28.2,-16.7"
    ws = WorkspaceLayout.at(tmp_path)
    assert stale(ws)
    for sid in ("iceye", "capella", "umbra"):
        atomic_write_json(ws.cache_dir("opendata") / f"{sid}.json", {"synced": "2000-01-01T00:00:00+00:00"})
    assert stale(ws)


def test_window_read_retries_a_failed_strip(tmp_path, monkeypatch):
    """A connection cut mid-tile (truncated body) fails one strip: it is read again, the window is complete."""
    rasterio = pytest.importorskip("rasterio")
    from rasterio.errors import RasterioIOError

    from geoeyes.opendata import fetch
    data = np.arange(2 * 40 * 30, dtype=np.uint16).reshape(2, 40, 30)
    tif = tmp_path / "x.tif"
    with rasterio.open(tif, "w", driver="GTiff", width=30, height=40, count=2, dtype="uint16") as dst:
        dst.write(data)
        dst.update_tags(1, NAME="AMPLITUDE")
    real_open, calls = rasterio.open, {"n": 0}

    def flaky(path, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:                                   # the second strip's first attempt
            raise RasterioIOError("TIFFReadEncodedTile: Read error")
        return real_open(path, *a, **k)

    monkeypatch.setattr(rasterio, "open", flaky)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    out, meta = fetch.read_window_retrying(str(tif), 5, 37, 3, 25, strip=10)
    np.testing.assert_array_equal(out, data[:, 5:37, 3:25])
    assert meta["tags"][0]["NAME"] == "AMPLITUDE" and calls["n"] == 5            # 4 strips + 1 retry
