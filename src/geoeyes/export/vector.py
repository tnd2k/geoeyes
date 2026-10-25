"""GIS exports of a product (derived, re-creatable): ``exports/<product_id>/``.

``<product_id>.gpkg``  layer ``points``: the product columns + one ``DYYYYMMDD`` displacement column per date (the
                       wide layout of the legacy QGIS time-series tools); the velocity style is stored in the
                       GeoPackage ``layer_styles`` table as the layer's default, so QGIS opens it styled.
``<product_id>.qml``   the same style, for other formats / layers.
``<product_id>.csv``   optional: points with the wide time series.
``<product_id>.pmtiles`` vector tiles of the points (``export.pmtiles``): QGIS 3.32+, the web app's large-product mode.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from geoeyes.export.styles import marker_size_m, velocity_qml
from geoeyes.io.points import read_points, read_timeseries


def _wide(product: Path, uids) -> tuple[list[str], np.ndarray]:
    ts = read_timeseries(product / "timeseries.parquet")
    w = ts.pivot(index="point_uid", columns="date", values="disp_mm").reindex(uids)
    cols = [f"D{np.datetime64(d, 'D').astype(object):%Y%m%d}" for d in w.columns]
    return cols, w.to_numpy(np.float32)


def _embed_style(gpkg: Path, layer: str, qml: str, name: str) -> None:
    with sqlite3.connect(gpkg) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS layer_styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT, f_table_schema TEXT, f_table_name TEXT,
            f_geometry_column TEXT, styleName TEXT, styleQML TEXT, styleSLD TEXT, useAsDefault BOOLEAN,
            description TEXT, owner TEXT, ui TEXT, update_time DATETIME)""")
        con.execute("DELETE FROM layer_styles WHERE f_table_name = ?", (layer,))
        con.execute("INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
                    "styleName, styleQML, styleSLD, useAsDefault, description, owner, ui, update_time) "
                    "VALUES ('', '', ?, 'geom', ?, ?, '', 1, 'LOS velocity (mm/yr), GeoEyes', '', '', ?)",
                    (layer, name, qml, datetime.now(UTC).isoformat(timespec="seconds")))
        # register the table as plain attributes so GeoPackage validators accept it
        con.execute("INSERT OR IGNORE INTO gpkg_contents (table_name, data_type, identifier) "
                    "VALUES ('layer_styles', 'attributes', 'layer_styles')")


def export_product(product: str | Path, out_dir: str | Path, formats=("gpkg",)) -> list[Path]:
    product, out_dir = Path(product), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pid = product.name
    gdf = read_points(product / "points.parquet")
    cols, disp = _wide(product, gdf["point_uid"].to_numpy())
    wide = gdf.copy()
    for k, c in enumerate(cols):
        wide[c] = disp[:, k]
    if "type" in wide:
        wide["type"] = wide["type"].astype(str)
    qml = velocity_qml(gdf["vel_los_mm_yr"].to_numpy(), size_m=marker_size_m(gdf["lon"], gdf["lat"]))
    written = []
    (out_dir / f"{pid}.qml").write_text(qml, encoding="utf-8")
    written.append(out_dir / f"{pid}.qml")
    if "gpkg" in formats:
        p = out_dir / f"{pid}.gpkg"
        p.unlink(missing_ok=True)
        wide.to_file(p, layer="points", driver="GPKG", engine="pyogrio")
        _embed_style(p, "points", qml, pid)
        written.append(p)
    if "csv" in formats:
        p = out_dir / f"{pid}.csv"
        wide.drop(columns="geometry").to_csv(p, index=False, float_format="%.4f")
        written.append(p)
    if "pmtiles" in formats:
        from geoeyes.export.pmtiles import product_pmtiles
        p = out_dir / f"{pid}.pmtiles"
        product_pmtiles(product, p)
        written.append(p)
    return written
