"""Lidar DSM without the network: the survey chosen over an area, the year of a survey name, and the composite DEM
(the fine heights inside, the coarse ones around)."""
import json

import numpy as np

from geoeyes.geometry.dem import CompositeDem, Dem
from geoeyes.geometry.lidar import _year, surveys_over


def test_year_of_survey_names():
    assert _year("NV_ClarkCo_2_B22") == 2022
    assert _year("USGS_LPC_NV_LasVegas_QL1_2016_LAS_2018") == 2016
    assert _year("NV_LasVegasValley_2010") == 2010
    assert _year("AK_Something") == 0


def test_surveys_over_keeps_covering_ones_newest_first(tmp_path):
    def feat(name, w, s, e, n, count):
        ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
        return {"type": "Feature", "properties": {"name": name, "count": count, "url": f"https://x/{name}/ept.json"},
                "geometry": {"type": "MultiPolygon", "coordinates": [[ring]]}}
    fc = {"type": "FeatureCollection", "features": [
        feat("NV_LasVegasValley_2010", -116, 35, -114, 37, 7e8),
        feat("NV_ClarkCo_2_B22", -116, 35, -114, 37, 4e10),
        feat("NV_ClarkCo_1_B22", -115.1, 35, -114, 37, 1e10)]}            # does not reach the area
    (tmp_path / "resources.geojson").write_text(json.dumps(fc), encoding="utf-8")
    got = surveys_over((-115.19, 36.09, -115.16, 36.12), tmp_path)
    assert [s["name"] for s in got] == ["NV_ClarkCo_2_B22", "NV_LasVegasValley_2010"]


def test_composite_dem_uses_the_fine_heights_where_it_has_them():
    coarse = np.full((11, 11), 600.0)                                    # 0.1 deg cells, 600 m everywhere
    fine = np.full((101, 101), 700.0)                                    # 0.001 deg over the centre, roofs at 700 m
    fd = Dem(fine, 36.15, -115.20, 0.001, 0.001, "EGM96", "lidar")
    d = CompositeDem(coarse, 36.6, -115.7, 0.1, 0.1, "EGM2008", "both", fine=fd)
    h = d.orthometric(np.array([36.10, 36.40]), np.array([-115.15, -115.50]))
    assert np.allclose(h, [700.0, 600.0])
