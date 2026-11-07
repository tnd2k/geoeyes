"""Flood inventory: parsing announced lists, placing rows on streets, velocity around them."""
from __future__ import annotations

import numpy as np

from geoeyes.ancillary import flood_reports as fr

LIST = """Danh sách điểm ngập do mưa lớn:
- Đường Lý Thường Kiệt, đoạn từ số 387 đến cổng Trường Nguyễn Thái Bình
- Ngã tư Bảy Hiền
- Đường Lê Đức Anh - Hồ Học Lãm
- Đường Lê Quang Đạo:
+ Từ giao lộ Võ Thị Hồi đến giao lộ Nguyễn Thị Sóc
+ Giao lộ Lê Quang Đạo - Trần Văn Mười
- Đường Đỗ Mười:
+ Trước số 139 (phường Tam Bình)
+ Hai bên cầu Bình Phước, trước số 2 (phường Hiệp Bình)
- Đường số 2 (phường Thủ Đức)
- Đường 2-9
Danh sách điểm ngập do triều cường:
- Đường Lê Khả Phiêu:
- Đoạn song hành, hướng từ Hưng Nhơn về Dương Đình Cúc
- Giao Hoàng Đạo Thúy, hướng từ Nguyễn Văn Linh đi cầu Bình Điền
- Đường Trần Xuân Soạn, từ Huỳnh Tấn Phát đến Lâm Văn Bền
"""


def test_parse_list_kinds_causes_and_groups():
    rows = fr.parse_list(LIST, reported="2026-10-06", source="PC08")
    by = {r["text"]: r for r in rows}
    assert len(rows) == 12 and [r["cause"] for r in rows].count("tide") == 3
    r = by["Đường Lý Thường Kiệt, đoạn từ số 387 đến cổng Trường Nguyễn Thái Bình"]
    assert (r["kind"], r["street"], r["from"], r["to"]) == ("segment", "Lý Thường Kiệt", "số 387",
                                                             "cổng Trường Nguyễn Thái Bình")
    assert by["Ngã tư Bảy Hiền"]["kind"] == "place"
    assert (by["Đường Lê Đức Anh - Hồ Học Lãm"]["kind"], by["Đường Lê Đức Anh - Hồ Học Lãm"]["cross"]) == \
        ("junction", "Hồ Học Lãm")
    r = by["Từ giao lộ Võ Thị Hồi đến giao lộ Nguyễn Thị Sóc"]           # under "Đường Lê Quang Đạo:"
    assert (r["street"], r["from"], r["to"]) == ("Lê Quang Đạo", "Võ Thị Hồi", "Nguyễn Thị Sóc")
    r = by["Trước số 139 (phường Tam Bình)"]
    assert (r["kind"], r["street"], r["place"], r["ward"]) == ("address", "Đỗ Mười", "số 139", "phường Tam Bình")
    assert by["Hai bên cầu Bình Phước, trước số 2 (phường Hiệp Bình)"]["street"] == "Đỗ Mười"
    assert by["Đường số 2 (phường Thủ Đức)"]["street"] == "số 2"
    assert by["Đường 2-9"]["kind"] == "street"                          # "2-9" is a name, not a junction
    # "- Đoạn ..." / "- Giao ..." right after "- Đường Lê Khả Phiêu:" belong to it
    r = by["Giao Hoàng Đạo Thúy, hướng từ Nguyễn Văn Linh đi cầu Bình Điền"]
    assert (r["kind"], r["street"], r["cross"]) == ("junction", "Lê Khả Phiêu", "Hoàng Đạo Thúy")
    assert len({r["id"] for r in rows}) == len(rows)


def _ways():
    """A grid around (106.7, 10.8): avenue A west-east, streets B and C north-south 1 km apart."""
    lon0, lat0, dl = 106.7, 10.8, 0.009
    return [
        {"id": 1, "tags": {"name": "Đường A"}, "coords": [[lon0 - dl, lat0], [lon0 + 2 * dl, lat0]]},
        {"id": 2, "tags": {"name": "B"}, "coords": [[lon0, lat0 - dl], [lon0, lat0 + dl]]},
        {"id": 3, "tags": {"name": "Đường C"}, "coords": [[lon0 + dl, lat0 - dl], [lon0 + dl, lat0 + dl]]},
    ]


def test_locator_cuts_segment_between_crossings_and_finds_junctions():
    frame = fr._Frame(106.7, 10.8)
    loc = fr.Locator(_ways(), frame, place=lambda q: None)
    g, how = loc.locate({"kind": "segment", "street": "A", "from": "B", "to": "C"})
    assert how == "exact" and g["type"] == "LineString"
    xs = [p[0] for p in g["coordinates"]]
    assert abs(min(xs) - 106.7) < 1e-5 and abs(max(xs) - 106.709) < 1e-5
    g, how = loc.locate({"kind": "junction", "street": "A", "cross": "Đường B"})
    assert how == "exact" and np.allclose(g["coordinates"], [106.7, 10.8], atol=1e-6)
    assert loc.locate({"kind": "junction", "street": "B", "cross": "C"}) == (None, "none")     # parallel
    g, how = loc.locate({"kind": "street", "street": "C"})
    assert how == "approx" and g["type"] == "LineString"
    assert loc.locate({"kind": "street", "street": "Không có"}) == (None, "none")
    g, how = loc.locate({"kind": "street", "street": "C", "geom_wkt": "POINT (106.71 10.81)"})
    assert how == "manual" and g["coordinates"] == (106.71, 10.81)


def test_near_product_contrast():
    rng = np.random.default_rng(0)
    lon = 106.7 + rng.uniform(-0.02, 0.02, 20_000)
    lat = 10.8 + rng.uniform(-0.02, 0.02, 20_000)
    d = np.hypot((lon - 106.7) * 109_000, (lat - 10.8) * 110_600)
    vel = np.where(d < 100, -20.0, -2.0)                                # a subsiding spot at the junction
    fc = {"features": [{"id": "a", "geometry": {"type": "Point", "coordinates": [106.7, 10.8]}},
                       {"id": "b", "geometry": {"type": "Point", "coordinates": [107.5, 11.5]}},
                       {"id": "c", "geometry": None}]}
    s = fr.near_product(fc, lon, lat, vel, radius_m=100)
    a = s["rows"]["a"]
    assert a["n"] > 20 and a["vel_median"] == -20.0 and a["ring_median"] == -2.0 and a["contrast"] == -18.0
    assert a["rank"] == 0.0 and s["rows"]["b"] == {"n": 0} and "c" not in s["rows"]
    assert s["n_located"] == 2 and s["n_with_points"] == 1


def test_outlook_score_weights_cause_tide_and_subsidence():
    from datetime import datetime

    from geoeyes.ancillary.flood_outlook import assess
    times = [f"2026-10-30T{h:02d}:00" for h in range(24)] + [f"2026-10-31T{h:02d}:00" for h in range(24)]
    dry = {"time": times, "mm": [0.0] * 48, "prob": [10] * 48}
    wet = {"time": times, "mm": [0.0] * 14 + [30.0, 25.0] + [0.0] * 32, "prob": [90] * 48}
    tide = {"time": times, "level": [1.0] * 2 + [2.3] + [1.0] * 45, "median_daily_high": 1.9, "highest": 2.4}
    now = datetime(2026, 10, 30, 0, 30)
    t = assess(dry, tide, "tide", now)
    assert t["tide_peak_m"] == 2.3 and t["tide_peak_time"] == "2026-10-30T02:00" and t["parts"]["tide"] == 0.8
    assert t["score"] == 64 and t["level"] == "high" and t["window"] == ["2026-10-30T02:00", "2026-10-30T02:00"]
    r = assess(dry, tide, "rain", now)                                 # same tide, a rain spot: low weight
    assert r["score"] == 16 and r["level"] == "low" and r["window"] is None
    w = assess(wet, tide, "rain", now, velocity=-12.0)
    assert w["rain_24h_mm"] == 55.0 and w["rain_max_mm_h"] == 30.0 and w["parts"]["subsidence_bonus"] == 6
    assert w["score"] == min(100, round(100 * (0.8 * 0.95 + 0.2 * 0.8) + 6)) and w["level"] == "very_high"
    assert w["window"] == ["2026-10-30T14:00", "2026-10-30T15:00"] and len(w["hours"]["time"]) == 24
    n = assess(wet, None, "rain_tide", now)                           # inland city: rain only, no tide
    assert n["tide_peak_m"] is None and n["parts"]["w_rain"] == 1.0 and n["score"] == 95


def test_outlook_city_takes_the_subsidence_of_its_flood_spots(monkeypatch):
    from datetime import datetime

    from geoeyes.ancillary import flood_outlook as fo
    times = [f"2026-10-30T{h:02d}:00" for h in range(24)] + [f"2026-10-31T{h:02d}:00" for h in range(24)]
    dry = {"time": times, "mm": [0.0] * 48, "prob": [10] * 48}
    monkeypatch.setattr(fo, "rain", lambda pts: [dry] * len(pts))
    monkeypatch.setattr(fo, "tide", lambda g: None)
    feats = [{"id": f"r{i}", "geometry": {"type": "Point", "coordinates": [105.8, 21.0]},
              "properties": {"region": "hanoi", "cause": "rain"}} for i in range(4)]
    stats = {"rows": {"r0": {"vel_median": -12.0}, "r1": {"vel_median": -8.0}, "r2": {"vel_median": -2.0}}}
    out = fo.outlook({"features": feats}, stats, datetime(2026, 10, 30, 0, 30))
    a = out["areas"]["hanoi"]
    assert a["subsidence"] == {"locations": 3, "sinking_over_5": 2, "median_mm_yr": -8.0}
    assert a["city"]["velocity_mm_yr"] == -8.0 and a["city"]["parts"]["subsidence_bonus"] == 3
    # fewer than 3 covered spots: no city subsidence
    few = fo.outlook({"features": feats}, {"rows": {"r0": {"vel_median": -30.0}}}, datetime(2026, 10, 30, 0, 30))
    assert few["areas"]["hanoi"]["city"]["parts"]["subsidence_bonus"] == 0


def test_parse_prose_basin_bulletin():
    text = ("Lưu vực sông Nhuệ: Dương Đình Nghệ – Nam Trung Yên (sau Keangnam), Hoa Bằng (ngõ 99), "
            "Yên Nghĩa (từ bến xe Yên Nghĩa đến ngã ba Ba La), khu TT18, phường Phú La, 165 Thái Hà, "
            "nút giao Lương Thế Vinh giao Tố Hữu, phố Đội Cấn và ngõ 100 Đội Cấn…")
    rows = fr.parse_prose(text, reported="2025-10-07", source="Thoát nước Hà Nội")
    k = {r["text"]: r for r in rows}
    assert len(rows) == 7 and all(r["cause"] == "rain" and r["region"] == "hanoi" for r in rows)
    assert k["Dương Đình Nghệ – Nam Trung Yên (sau Keangnam)"]["kind"] == "junction"
    r = k["Hoa Bằng (ngõ 99)"]
    assert (r["kind"], r["street"], r["place"], r["notes"].split(";")[0]) == ("place", "Hoa Bằng", "ngõ 99",
                                                                           "Lưu vực sông Nhuệ")
    r = k["Yên Nghĩa (từ bến xe Yên Nghĩa đến ngã ba Ba La)"]
    assert (r["kind"], r["from"], r["to"]) == ("segment", "bến xe Yên Nghĩa", "Ba La")
    assert k["khu TT18 (phường Phú La)"]["ward"] == "phường Phú La"
    assert (k["165 Thái Hà"]["kind"], k["165 Thái Hà"]["place"]) == ("address", "số 165")
    assert (k["nút giao Lương Thế Vinh giao Tố Hữu"]["street"], k["nút giao Lương Thế Vinh giao Tố Hữu"]["cross"]) == \
        ("Lương Thế Vinh", "Tố Hữu")
    assert k["phố Đội Cấn và ngõ 100 Đội Cấn"]["street"] == "Đội Cấn"
