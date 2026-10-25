"""Workspace catalog: every product of every project, as a static STAC catalog and a DuckDB index.

    <workspace>/catalog/catalog.json              STAC Catalog -> one Collection per project -> the products'
    <workspace>/catalog/<project>/collection.json   own item.json (left untouched: products are immutable)
    <workspace>/catalog/index.duckdb              table ``products`` (one row per product version, ``latest``
                                                  flag) and view ``points`` over the products' GeoParquet

Rebuilt after every run (``controller.pipeline.run``) and by ``geoeyes catalog build``. ``search`` finds the
products over an area / period / sensor and, with a velocity threshold, counts their points beyond it (DuckDB reads
the GeoParquet ``bbox`` column directly: no spatial extension needed).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from geoeyes.io.manifest import atomic_write_json
from geoeyes.workspace import WorkspaceLayout

log = logging.getLogger(__name__)

STAC_VERSION = "1.0.0"


def _products(ws: WorkspaceLayout) -> list[dict]:
    rows = []
    for name in ws.list_projects():
        proot = ws.project(name).root / "products"
        versions = sorted(proot.glob("*/item.json")) if proot.exists() else []
        latest_by_track: dict[str, tuple[str, str]] = {}      # track -> (created, product id)
        items = []
        for f in versions:
            try:
                item = json.loads(f.read_text(encoding="utf-8"))
                created = json.loads((f.parent / "manifest.json").read_text(encoding="utf-8")).get("created", "")
            except (ValueError, OSError):
                continue
            p = item.get("properties", {})
            items.append((f, item, p))
            tr = p.get("geoeyes:track", "")
            # the latest build wins (a new acquisition starts another id prefix, so not the version number)
            if (created, f.parent.name) > latest_by_track.get(tr, ("", "")):
                latest_by_track[tr] = (created, f.parent.name)
        for f, item, p in items:
            rep = {}
            if (f.parent / "report.json").exists():
                try:
                    rep = json.loads((f.parent / "report.json").read_text(encoding="utf-8"))
                except ValueError:
                    rep = {}
            b = item.get("bbox") or [None] * 4
            rows.append({
                "id": item["id"], "project": name, "track": p.get("geoeyes:track", ""),
                "sensor": p.get("geoeyes:sensor", ""), "engine": p.get("geoeyes:engine", ""),
                "first_date": (p.get("start_datetime") or "")[:10], "last_date": (p.get("end_datetime") or "")[:10],
                "n_points": p.get("geoeyes:n_points"), "epochs": p.get("geoeyes:epochs"),
                "vel_min": p.get("geoeyes:vel_min_mm_yr"), "vel_max": p.get("geoeyes:vel_max_mm_yr"),
                "vel_median": p.get("geoeyes:vel_median_mm_yr"),
                "confidence": (rep.get("confidence") or {}).get("level"),
                "xmin": b[0], "ymin": b[1], "xmax": b[2], "ymax": b[3],
                "latest": latest_by_track.get(p.get("geoeyes:track", ""), ("", ""))[1] == f.parent.name,
                "item": str(f), "points": str(f.parent / "points.parquet"),
                "timeseries": str(f.parent / "timeseries.parquet")})
    return rows


def build_catalog(ws: WorkspaceLayout) -> dict:
    """Write the STAC catalog and the DuckDB index; returns a summary."""
    import duckdb
    import pandas as pd
    rows = _products(ws)
    root = ws.catalog
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    links = [{"rel": "self", "href": "./catalog.json", "type": "application/json"},
             {"rel": "root", "href": "./catalog.json", "type": "application/json"}]
    for name in sorted({r["project"] for r in rows}):
        mine = [r for r in rows if r["project"] == name]
        coll = {"type": "Collection", "stac_version": STAC_VERSION, "id": name,
                "description": f"GeoEyes products of project {name}", "license": "proprietary",
                "extent": {"spatial": {"bbox": [[min(r["xmin"] for r in mine), min(r["ymin"] for r in mine),
                                                 max(r["xmax"] for r in mine), max(r["ymax"] for r in mine)]]},
                           "temporal": {"interval": [[f"{min(r['first_date'] for r in mine)}T00:00:00Z",
                                                      f"{max(r['last_date'] for r in mine)}T23:59:59Z"]]}},
                "links": [{"rel": "self", "href": "./collection.json", "type": "application/json"},
                          {"rel": "root", "href": "../catalog.json", "type": "application/json"},
                          {"rel": "parent", "href": "../catalog.json", "type": "application/json"},
                          *[{"rel": "item", "href": Path(r["item"]).as_uri(), "type": "application/geo+json",
                             "title": r["id"], "geoeyes:latest": r["latest"]} for r in mine]]}
        atomic_write_json(root / name / "collection.json", coll)
        links.append({"rel": "child", "href": f"./{name}/collection.json", "type": "application/json", "title": name})
    atomic_write_json(root / "catalog.json", {"type": "Catalog", "stac_version": STAC_VERSION, "id": "geoeyes",
                                              "description": f"GeoEyes workspace {ws.root} ({now})", "links": links})
    tmp = root / "index.duckdb.tmp"
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        df = pd.DataFrame(rows, columns=["id", "project", "track", "sensor", "engine", "first_date", "last_date",
                                         "n_points", "epochs", "vel_min", "vel_max", "vel_median", "confidence",
                                         "xmin", "ymin", "xmax", "ymax", "latest", "item", "points", "timeseries"])
        con.register("df", df)
        con.execute("CREATE TABLE products AS SELECT * FROM df")
        files = [r["points"] for r in rows if Path(r["points"]).exists()]
        if files:
            lst = ", ".join("'" + f.replace("\\", "/").replace("'", "''") + "'" for f in files)
            pid = "regexp_extract(filename, '([^/\\\\]+)[/\\\\]points\\.parquet$', 1)"
            con.execute(f"CREATE VIEW points AS SELECT {pid} AS product_id, * EXCLUDE (filename) "
                        f"FROM read_parquet([{lst}], filename = true, union_by_name = true)")
    finally:
        con.close()
    out = root / "index.duckdb"
    out.unlink(missing_ok=True)
    tmp.replace(out)
    log.info("catalog: %d product(s) of %d project(s) -> %s", len(rows), len({r["project"] for r in rows}), root)
    return {"products": len(rows), "projects": len({r["project"] for r in rows}), "path": str(root)}


def search(ws: WorkspaceLayout, *, bbox: list[float] | None = None, start: str | None = None,
           end: str | None = None, sensor: str | None = None, project: str | None = None,
           latest_only: bool = True, vel_below: float | None = None, vel_above: float | None = None) -> list[dict]:
    """Products intersecting ``bbox`` and overlapping [start, end]; with a bbox, the points inside it are counted
    (and those beyond the velocity thresholds)."""
    import duckdb
    idx = ws.catalog / "index.duckdb"
    if not idx.exists():
        build_catalog(ws)
    con = duckdb.connect(str(idx), read_only=True)
    try:
        where, args = [], []
        if bbox:
            where.append("xmax >= ? AND xmin <= ? AND ymax >= ? AND ymin <= ?")
            args += [bbox[0], bbox[2], bbox[1], bbox[3]]
        if start:
            where.append("last_date >= ?")
            args.append(start)
        if end:
            where.append("first_date <= ?")
            args.append(end)
        if sensor:
            where.append("sensor = ?")
            args.append(sensor)
        if project:
            where.append("project = ?")
            args.append(project)
        if latest_only:
            where.append("latest")
        sql = "SELECT * FROM products" + (" WHERE " + " AND ".join(where) if where else "") + \
              " ORDER BY last_date DESC, project"
        cur = con.execute(sql, args)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
        if bbox:
            for r in rows:
                cond = ["bbox.xmin BETWEEN ? AND ?", "bbox.ymin BETWEEN ? AND ?"]
                a = [bbox[0], bbox[2], bbox[1], bbox[3]]
                extra = []
                if vel_below is not None:
                    extra.append(f"count(*) FILTER (WHERE vel_los_mm_yr <= {float(vel_below)!r})")
                if vel_above is not None:
                    extra.append(f"count(*) FILTER (WHERE vel_los_mm_yr >= {float(vel_above)!r})")
                q = (f"SELECT count(*), min(vel_los_mm_yr), max(vel_los_mm_yr), median(vel_los_mm_yr)"
                     f"{''.join(', ' + e for e in extra)} FROM read_parquet(?) WHERE {' AND '.join(cond)}")
                res = con.execute(q, [r["points"].replace("\\", "/"), *a]).fetchone()
                r["in_area"] = {"n": res[0], "vel_min": res[1], "vel_max": res[2], "vel_median": res[3]}
                k = 4
                if vel_below is not None:
                    r["in_area"]["n_below"] = res[k]
                    k += 1
                if vel_above is not None:
                    r["in_area"]["n_above"] = res[k]
            rows = [r for r in rows if r["in_area"]["n"]]
        return rows
    finally:
        con.close()


__all__ = ["build_catalog", "search"]
