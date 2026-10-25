import json

import pytest

from tests.unit.processing.test_products import fake_run

pytest.importorskip("duckdb")
from geoeyes.catalog import build_catalog, search  # noqa: E402
from geoeyes.products.builder import build_product  # noqa: E402
from geoeyes.workspace import WorkspaceLayout  # noqa: E402

TOML = """schema = "geoeyes.project/1"
[project]
name = "{name}"
method = "psi"
[[tracks]]
sensor = "sentinel1"
direction = "ascending"
relative_orbit = 78
"""


def test_catalog_lists_products_and_counts_points_in_an_area(tmp_path):
    ws = WorkspaceLayout.at(tmp_path / "ws")
    p = ws.project("mx").ensure()
    p.config.write_text(TOML.format(name="mx"), encoding="utf-8")
    run, _ = fake_run(tmp_path)                                  # 60 points near -99.0, 19.3, velocity ~ -20
    for _ in range(2):                                           # two versions: only the last one is "latest"
        r = build_product(run, p.root / "products", project="mx", track_id="sentinel1-asc-078")
    s = build_catalog(ws)
    assert s == {"products": 2, "projects": 1, "path": str(ws.catalog)}
    cat = json.loads((ws.catalog / "catalog.json").read_text(encoding="utf-8"))
    assert [link["href"] for link in cat["links"] if link["rel"] == "child"] == ["./mx/collection.json"]
    coll = json.loads((ws.catalog / "mx" / "collection.json").read_text(encoding="utf-8"))
    assert sum(link["rel"] == "item" for link in coll["links"]) == 2
    rows = search(ws, bbox=[-99.1, 19.2, -98.9, 19.4], vel_below=-20)
    assert [x["id"] for x in rows] == [r["product_id"]]
    assert rows[0]["in_area"]["n"] == 60 and 0 < rows[0]["in_area"]["n_below"] < 60
    assert search(ws, bbox=[10, 45, 11, 46]) == []
    assert len(search(ws, latest_only=False)) == 2 and search(ws, start="2030-01-01") == []
