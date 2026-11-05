"""Landslide study labels (geoeyes.landslide.labels): the scarp point is the highest cell of the polygon, negatives
keep their distance from every polygon, draws are balanced and reproducible, reactivations are flagged; footprints
and the area–frequency tail (geoeyes.landslide.inventory)."""
import math

import geopandas as gpd
import numpy as np
import pytest
import shapely

from geoeyes.core.errors import ConfigError
from geoeyes.geometry.dem import Dem
from geoeyes.landslide import inventory as inv
from geoeyes.landslide import labels as lb
from geoeyes.landslide.study import LabelParams

LAT0, LON0 = 15.0, 108.0
KX = 111_320.0 * math.cos(math.radians(LAT0 + 0.025))


def _dem(rise_north: bool = True) -> Dem:
    """1″ grid over 15.00–15.05 N, 108.00–108.05 E; height rises 1,000 m to the north (or to the east)."""
    n = 181
    lat = 15.05 - np.arange(n) / 3600.0
    lon = 108.0 + np.arange(n) / 3600.0
    h = (lat[:, None] - 15.0) / 0.05 * 1000.0 + 0 * lon[None, :] if rise_north else \
        0 * lat[:, None] + (lon[None, :] - 108.0) / 0.05 * 1000.0
    return Dem(h.astype(np.float32), 15.05, 108.0, 1 / 3600.0, 1 / 3600.0, "EGM2008", "synthetic")


def _square(cx_m: float, cy_m: float, half_m: float):
    """Square polygon of side 2·half_m centred cx_m, cy_m metres east / north of (108.0, 15.0)."""
    x0, x1 = LON0 + (cx_m - half_m) / KX, LON0 + (cx_m + half_m) / KX
    y0, y1 = LAT0 + (cy_m - half_m) / 110_540.0, LAT0 + (cy_m + half_m) / 110_540.0
    return shapely.box(x0, y0, x1, y1)


def _setup(params=LabelParams(), rise_north=True, earlier=None):
    polys = gpd.GeoDataFrame({"src_fid": [0, 1, 2], "area_m2": [40_000.0, 22_500.0, 400.0]},
                             geometry=[_square(1500, 1500, 100), _square(3000, 3500, 75), _square(4200, 1200, 10)],
                             crs=4326)
    area = shapely.box(108.0, 15.0, 108.05, 15.05)
    dem = _dem(rise_north)
    grid = lb.grid_for(area.bounds, params.cell_m)
    h = dem.orthometric(grid.lat, grid.lon)
    s = lb.grid_slope(grid, h)
    fp = {"near": area.buffer(-0.002), "hull": area}
    t, smy = lb.make_labels(polys, fp, area, grid, h, s, dem, params, "Test", earlier)
    return t, smy, polys, grid, h


def test_scarp_is_the_highest_cell_of_the_polygon():
    t, _, polys, grid, h = _setup()
    sc = t[(t.label == 1) & (t.variant == "scarp")].set_index("src_fid")
    for fid, g in zip(polys.src_fid, polys.geometry):
        inside = lb.cells_in(grid, g)
        top = sc.loc[fid]
        # height rises north: the scarp cell is the northernmost row of the polygon, at least as high as any centre
        if len(inside):
            assert top.height_m >= h[inside].max() - 0.5
        assert g.bounds[3] - 30 / 110_540.0 <= top.lat <= g.bounds[3] + 30 / 110_540.0
    # rising to the east instead: the scarp moves to the east edge
    t2, _, polys, _, _ = _setup(rise_north=False)
    top = t2[(t2.label == 1) & (t2.variant == "scarp") & (t2.src_fid == 0)].iloc[0]
    assert polys.geometry[0].bounds[2] - 30 / KX <= top.lon <= polys.geometry[0].bounds[2] + 30 / KX


def test_upper_cells_lie_in_the_polygon_and_its_top_third():
    t, _, polys, grid, h = _setup()
    up = t[(t.label == 1) & (t.variant == "upper") & (t.src_fid == 0)]
    inside = lb.cells_in(grid, polys.geometry[0])
    assert set(up.cell) <= set(inside)
    assert up.height_m.min() >= h[inside].min() + (2 / 3) * (h[inside].max() - h[inside].min()) - 40
    # the polygon smaller than a cell still gets one positive in every variant
    tiny = t[(t.label == 1) & (t.src_fid == 2)]
    assert set(tiny.variant) == set(lb.VARIANTS)


def test_negatives_keep_their_distance_and_are_balanced_and_reproducible():
    p = LabelParams(draws=3, ratio=2.0)
    t, smy, polys, _, _ = _setup(p)
    neg = t[t.label == 0]
    crs = polys.estimate_utm_crs()
    pts = gpd.GeoSeries(gpd.points_from_xy(neg.lon, neg.lat), crs=4326).to_crs(crs)
    d = pts.distance(shapely.union_all(polys.to_crs(crs).geometry.values))
    assert d.min() > p.negative_buffer_m - 1
    for (f, v, k), g in neg.groupby(["footprint", "variant", "draw"]):
        assert len(g) == round(p.ratio * smy["positives"][v])
        assert g.cell.is_unique
    assert set(neg.footprint) == {"near", "hull"}
    assert set(neg[neg.footprint == "near"].cell) <= set(lb.cells_in(lb.grid_for((108.0, 15.0, 108.05, 15.05), 30.0),
                                                                     shapely.box(108.0, 15.0, 108.05, 15.05).buffer(-0.002)))
    t2, _, _, _, _ = _setup(p)
    assert t.equals(t2)
    d0 = set(neg[(neg.draw == 0) & (neg.variant == "scarp") & (neg.footprint == "hull")].cell)
    d1 = set(neg[(neg.draw == 1) & (neg.variant == "scarp") & (neg.footprint == "hull")].cell)
    assert d0 != d1


def test_reactivated_positives_are_flagged():
    earlier = gpd.GeoDataFrame({"src_fid": [9]}, geometry=[_square(1500, 1450, 60)], crs=4326)
    t, smy, _, _, _ = _setup(earlier=earlier)
    pos = t[(t.label == 1) & (t.variant == "scarp")].set_index("src_fid")
    assert bool(pos.loc[0, "reactivated"]) and not bool(pos.loc[1, "reactivated"])
    assert smy["reactivated_positives"] == 1


def test_label_params_are_checked():
    with pytest.raises(ConfigError):
        LabelParams.from_dict({"draws": 0})
    with pytest.raises(ConfigError):
        LabelParams.from_dict({"unknown": 1})
    assert LabelParams.from_dict({"ratio": 3}).ratio == 3.0


def test_near_footprint_has_no_empty_hull_interior():
    """Two clusters 20 km apart: the hull spans the gap, ``near`` does not."""
    rng = np.random.default_rng(0)
    xy = np.vstack([rng.normal((0, 0), 800, (200, 2)), rng.normal((20_000, 0), 800, (200, 2))])
    pts = gpd.GeoDataFrame({"event": ["E"] * len(xy)}, geometry=gpd.points_from_xy(xy[:, 0], xy[:, 1]), crs=32648)
    fp = inv.footprints(pts).set_index("variant")
    assert fp.loc["hull", "area_km2"] > fp.loc["near", "area_km2"]
    assert not fp.loc["near", "geometry"].contains(shapely.Point(10_000, 0))
    assert fp.loc["near", "n_inside"] == 400


def test_power_tail_recovers_the_exponent():
    rng = np.random.default_rng(1)
    alpha = 2.5
    a = 1000.0 * (1 - rng.random(20_000)) ** (-1 / (alpha - 1))      # Pareto, density ~ A^-alpha above 1,000 m²
    a = np.concatenate([a, rng.uniform(50, 1000, 5_000)])             # a body below the tail
    t = inv.power_tail(a)
    assert abs(t["alpha"] - alpha) < 0.1
    assert 500 <= t["xmin_m2"] <= 2500
