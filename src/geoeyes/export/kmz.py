"""Google Earth export of a product: ``exports/<product_id>/<product_id>.kmz``.

Google Earth does not draw hundreds of thousands of placemarks, so the velocity is a ground overlay (the points
rasterised at the marker size, in the classes of the QGIS style and the web app), with a legend, and the fastest
points (both directions) as placemarks that open their numbers and a small displacement chart.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

from geoeyes.export.styles import class_rgb, marker_size_m, velocity_classes
from geoeyes.io.points import read_points, read_timeseries

MAX_PIXELS = 4000                 # longest side of the overlay
HIGHLIGHTS = 1500                 # placemarks: the fastest points, split between both directions


def _overlay(lon, lat, vel, uppers, rgb, cell_m: float) -> tuple[bytes, tuple[float, float, float, float]]:
    from PIL import Image
    lat0 = np.radians(np.mean(lat))
    w, e, s, n = float(lon.min()), float(lon.max()), float(lat.min()), float(lat.max())
    dx = cell_m / (111_320.0 * np.cos(lat0))
    dy = cell_m / 110_540.0
    nx = int(np.ceil((e - w) / dx)) + 1
    ny = int(np.ceil((n - s) / dy)) + 1
    f = max(1.0, max(nx, ny) / MAX_PIXELS)
    dx, dy = dx * f, dy * f
    nx, ny = int(np.ceil((e - w) / dx)) + 1, int(np.ceil((n - s) / dy)) + 1
    img = np.zeros((ny, nx, 4), np.uint8)
    j = np.clip(((lon - w) / dx).astype(int), 0, nx - 1)
    i = np.clip(((n - lat) / dy).astype(int), 0, ny - 1)
    o = np.argsort(np.abs(vel))                     # the fastest point of a pixel drawn last
    img[i[o], j[o], :3] = class_rgb(vel[o], uppers, rgb)
    img[i[o], j[o], 3] = 255
    # gaps of one or two pixels between points take the nearest point's colour (as the markers of the map overlap)
    from scipy.ndimage import distance_transform_edt
    empty = img[:, :, 3] == 0
    dist, (ii, jj) = distance_transform_edt(empty, return_indices=True)
    fill = empty & (dist <= 2.0)
    img[fill] = img[ii[fill], jj[fill]]
    buf = io.BytesIO()
    Image.fromarray(img, "RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue(), (n + dy / 2, s - dy / 2, e + dx / 2, w - dx / 2)


def _legend(uppers, rgb, vmin: float, title: str) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    k = len(uppers)
    fig, ax = plt.subplots(figsize=(2.3, 0.28 * k + 0.7), dpi=110)
    lows = [vmin, *uppers[:-1]]
    for q in range(k):
        y = k - 1 - q
        ax.add_patch(plt.Rectangle((0, y), 0.6, 0.85, color=rgb[q] / 255.0))
        ax.text(0.8, y + 0.42, f"{lows[q]:.0f} … {uppers[q]:.0f}", va="center", fontsize=8.5)
    ax.set_xlim(0, 3.2)
    ax.set_ylim(-0.2, k + 0.9)
    ax.text(0, k + 0.35, title, fontsize=9, weight="bold")
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=False, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _series_table(dates, disp) -> str:
    """The displacement at a few dates, as an HTML table for the placemark balloon."""
    keep = np.linspace(0, len(dates) - 1, min(8, len(dates))).astype(int)
    rows = "".join(f"<tr><td>{dates[k]}</td><td align='right'>{disp[k]:+.1f}</td></tr>" for k in keep
                   if np.isfinite(disp[k]))
    return f"<table><tr><th>date</th><th>mm</th></tr>{rows}</table>"


def export_kmz(product: str | Path, out: str | Path) -> Path:
    product, out = Path(product), Path(out)
    gdf = read_points(product / "points.parquet")
    lon, lat = gdf["lon"].to_numpy(np.float64), gdf["lat"].to_numpy(np.float64)
    vel = gdf["vel_los_mm_yr"].to_numpy(np.float64)
    uppers, rgb = velocity_classes(vel)
    png, (north, south, east, west) = _overlay(lon, lat, vel, uppers, rgb, marker_size_m(lon, lat))
    legend = _legend(uppers, rgb, float(np.nanmin(vel)), "LOS velocity, mm/yr")
    # placemarks: the fastest points in each direction
    o = np.argsort(vel)
    half = HIGHLIGHTS // 2
    pick = np.unique(np.r_[o[:half], o[-half:]]) if vel.size > HIGHLIGHTS else np.arange(vel.size)
    ts = read_timeseries(product / "timeseries.parquet")
    uids = gdf["point_uid"].to_numpy()[pick]
    wide = ts[ts["point_uid"].isin(set(uids))].pivot(index="point_uid", columns="date", values="disp_mm").reindex(uids)
    dates = [str(np.datetime64(d, "D")) for d in wide.columns]
    series = wide.to_numpy(np.float64)
    styles = "".join(
        f"<Style id='c{q}'><IconStyle><color>ff{b:02x}{g:02x}{r:02x}</color><scale>0.6</scale><Icon><href>"
        "http://maps.google.com/mapfiles/kml/shapes/shaded_dot.png</href></Icon></IconStyle>"
        "<LabelStyle><scale>0</scale></LabelStyle></Style>" for q, (r, g, b) in enumerate(rgb))
    k = np.clip(np.searchsorted(uppers, vel[pick], side="left"), 0, len(uppers) - 1)
    cols = [c for c in ("temporal_coherence", "vel_std_mm_yr", "height_m") if c in gdf]
    marks = []
    for row, (p, q) in enumerate(zip(pick, k, strict=True)):
        info = "".join(f"<tr><td>{c}</td><td align='right'>{gdf[c].iloc[p]:.2f}</td></tr>" for c in cols)
        desc = (f"<b>{vel[p]:+.1f} mm/yr</b><table>{info}</table><br/>{_series_table(dates, series[row])}"
                f"<br/>LOS, + toward the satellite, relative to the reference area")
        marks.append(f"<Placemark><name>{vel[p]:+.1f}</name><styleUrl>#c{q}</styleUrl>"
                     f"<description><![CDATA[{desc}]]></description>"
                     f"<Point><coordinates>{lon[p]:.6f},{lat[p]:.6f},0</coordinates></Point></Placemark>")
    name = escape(product.name)
    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>{name}</name>
<description>GeoEyes ground deformation, mean LOS velocity (mm/yr), + toward the satellite. {len(vel):,} points;
classes: Pretty Breaks over the full range (as the QGIS style and the web app).</description>{styles}
<GroundOverlay><name>LOS velocity</name><color>e6ffffff</color><Icon><href>velocity.png</href></Icon>
<LatLonBox><north>{north:.7f}</north><south>{south:.7f}</south><east>{east:.7f}</east><west>{west:.7f}</west></LatLonBox>
</GroundOverlay>
<ScreenOverlay><name>Legend</name><Icon><href>legend.png</href></Icon>
<overlayXY x="0" y="0" xunits="fraction" yunits="fraction"/>
<screenXY x="0.01" y="0.06" xunits="fraction" yunits="fraction"/>
<size x="0" y="0" xunits="pixels" yunits="pixels"/></ScreenOverlay>
<Folder><name>Fastest points ({len(pick):,})</name><open>0</open>{''.join(marks)}</Folder>
</Document></kml>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("doc.kml", kml)
        z.writestr("velocity.png", png)
        z.writestr("legend.png", legend)
    return out
