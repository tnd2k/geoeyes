"""Render the report of a product: ``products/<id>/report.pdf`` + ``report.json`` (the data shown) +
``indicators.json`` (the standardised indicators of the assessment, ``geoeyes.indicators/1``).

The product's manifest does not list the report: it is derived, regenerated at any time (``geoeyes report``).
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path

import numpy as np

from geoeyes.report import assess, figures
from geoeyes.report.collect import collect

log = logging.getLogger(__name__)
TEMPLATE = Path(__file__).with_name("templates") / "report.typ"


def _figures(product: Path, data: dict, out: Path) -> dict[str, str]:
    from geoeyes.io.points import read_points
    out.mkdir(parents=True, exist_ok=True)
    pts = read_points(product / "points.parquet")
    a = data["acquisition"]
    made = {
        "velocity_map": figures.velocity_map(pts, out / "velocity_map.png", reference=data["reference"],
                                             heading=a.get("heading_deg"), look_side=a.get("look_side") or "right"),
        "distributions": figures.distributions(pts, out / "distributions.svg"),
        "baselines": figures.baselines(data["dates"], out / "baselines.svg") if data["dates"] else None,
        "noise": figures.noise(data["dates"], out / "noise.svg"),
        "clusters": figures.clusters(data["clusters"], out / "clusters.svg"),
    }
    # Part A: the map in the assessment basis with the hot spots, each hot spot's series, the hazard levels
    asm = data["assessment"]
    marks = [(h["lon"], h["lat"], h["id"]) for h in asm["hotspots"]]
    if asm["basis"] == "vertical":
        with np.errstate(all="ignore"):
            pts["vel_vert_mm_yr"] = pts["vel_los_mm_yr"] / pts["los_u"].where(pts["los_u"].abs() > 0.3)
        made["summary_map"] = figures.velocity_map(
            pts.loc[pts["vel_vert_mm_yr"].notna(), ["lon", "lat", "vel_vert_mm_yr"]], out / "summary_map.png",
            reference=data["reference"], column="vel_vert_mm_yr", label="Vertical velocity (mm/yr), negative = sinking",
            marks=marks)
    else:
        made["summary_map"] = figures.velocity_map(pts, out / "summary_map.png", reference=data["reference"],
                                                   heading=a.get("heading_deg"),
                                                   look_side=a.get("look_side") or "right", marks=marks)
    for h in asm["hotspots"]:
        made[f"hotspot_{h['id']}"] = figures.hotspot_series(h, out / f"hotspot_{h['id']}.svg", asm["basis"])
    hz = asm["impacts"]["hazard"]
    if hz.get("assessed"):
        try:
            made["hazard_map"] = figures.hazard_map(assess.hazard_cells(hz["folder"]), out / "hazard_map.png",
                                                    cell_m=hz["cell_m"], marks=marks)
        except Exception as exc:                          # an old or partial zoning: the table only
            log.warning("hazard map skipped: %s", exc)
    return {k: f"figures/{p.name}" for k, p in made.items() if p is not None}


def _clean(x):
    """JSON for Typst: NaN/inf -> null, numpy scalars -> Python."""
    import math
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def build_report(product: str | Path, *, copy_to: str | Path = "") -> Path:
    import typst
    product = Path(product)
    data = collect(product)
    with tempfile.TemporaryDirectory(prefix="geoeyes_report_") as tmp:
        tmp = Path(tmp)
        data["figures"] = _figures(product, data, tmp / "figures")
        (tmp / "report.json").write_text(json.dumps(_clean(data), indent=1, default=str, allow_nan=False),
                                         encoding="utf-8")
        shutil.copy(TEMPLATE, tmp / "report.typ")
        pdf = product / "report.pdf"
        typst.compile(str(tmp / "report.typ"), output=str(pdf), root=str(tmp))
        shutil.copy(tmp / "report.json", product / "report.json")
    (product / "indicators.json").write_text(json.dumps(_clean(data["indicators"]), indent=1, ensure_ascii=False,
                                                        allow_nan=False), encoding="utf-8")
    if copy_to:
        dest = Path(copy_to)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(pdf, dest / f"{product.name}.pdf")
    log.info("report %s (%s, confidence %s)", pdf, data["product_id"], data["confidence"]["level"])
    return pdf
