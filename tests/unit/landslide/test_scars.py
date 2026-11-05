"""Sentinel-2 scars (geoeyes.landslide.scars): the reflectance offset of the processing baselines, one item per tile
and day, objects, precision / recall against an inventory raster, the UTM grid."""
import numpy as np

from geoeyes.landslide import scars as sc


def _item(tile, day, created, cloud, applied=None, baseline="05.00"):
    p = {"s2:mgrs_tile": tile, "datetime": f"{day}T03:00:00Z", "created": created, "eo:cloud_cover": cloud,
         "s2:processing_baseline": baseline}
    if applied is not None:
        p["earthsearch:boa_offset_applied"] = applied
    return {"id": f"S2A_{tile}_{day}", "properties": p}


def test_offset_is_not_applied_twice():
    asset = {"raster:bands": [{"scale": 0.0001, "offset": -0.1}]}
    assert sc._scale(_item("48PYB", "2025-12-02", "", 1, applied=True), asset) == (0.0001, 0.0)
    assert sc._scale(_item("48PYB", "2025-12-02", "", 1, applied=False), asset) == (0.0001, -0.1)
    assert sc._scale(_item("48PYB", "2020-12-02", "", 1, applied=False, baseline="02.14"), asset) == (0.0001, 0.0)


def test_pick_keeps_the_latest_processing_then_the_clearest():
    items = [_item("48PYB", "2021-02-16", "2022-11-06", 3), _item("48PYB", "2021-02-16", "2026-08-18", 4),
             _item("48PYB", "2021-02-17", "2022-11-06", 50), _item("48PZB", "2021-02-16", "2022-11-06", 10)]
    out = sc.pick(items, max_scenes=1)
    assert len(out) == 2
    assert {(it["properties"]["s2:mgrs_tile"], it["properties"]["created"]) for it in out} == \
        {("48PYB", "2026-08-18"), ("48PZB", "2022-11-06")}


def test_objects_and_match():
    m = np.zeros((40, 40), bool)
    m[5:10, 5:10] = True                       # 25 px, on a polygon
    m[20:22, 20:22] = True                     # 4 px, away from any polygon
    m[30, 30] = True                           # 1 px: too small
    lab, n = sc.objects(m, 3)
    assert n == 2 and lab[30, 30] == 0
    inv = np.zeros((40, 40), np.int32)
    inv[6:12, 6:12] = 1                        # polygon 1: 36 px = 3600 m², hit
    inv[30:35, 0:4] = 2                        # polygon 2: 2000 m², missed
    r = sc.match(lab, n, inv, np.array([3600.0, 2000.0]), np.ones((40, 40), bool))
    assert r["objects"] == 2 and r["precision"] == 0.5 and r["recall"] == 0.5 and r["f1"] == 0.5


def test_local_drop_removes_a_regional_shift_and_keeps_a_scar():
    pre = np.full((3, 200, 200), 0.85, np.float32)
    post = pre.copy()
    post[0, :, 100:] -= 0.10                   # a hazy half: a regional shift, not a scar
    post[0, 20:24, 20:24] -= 0.40              # a scar in the clear half
    post[0, 150:154, 150:154] -= 0.40          # a scar in the hazy half
    d = sc.local_drop(pre, post, block=50)
    assert abs(float(np.median(d[:, 120:180]))) < 0.02
    assert d[21, 21] > 0.35 and d[151, 151] > 0.35


def test_forest_mask_leaves_out_a_swidden_mosaic():
    pre = np.full((3, 60, 60), 0.85, np.float32)
    pre[0, :, 30:] = np.where((np.indices((60, 30)).sum(0) // 4) % 2 == 0, 0.85, 0.45)   # fields among trees
    f = sc.forest_mask(pre)
    assert f[30, 10] and not f[30, 50].any()


def test_utm_grid_is_aligned_and_covers_the_box():
    g = sc.UtmGrid.around((107.60, 15.00, 108.20, 15.21))
    assert g.epsg == 32648 and g.x0 % 20 == 0 and g.y1 % 20 == 0
    lon, lat = g.lonlat(slice(0, 1))
    assert lon.min() < 107.61 and lon.max() > 108.19 and lat.max() > 15.209
