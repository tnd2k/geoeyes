"""3D Tiles export of a product (Cesium, ArcGIS, deck.gl): ``exports/<product_id>/3dtiles/``.

``tileset.json``    3D Tiles 1.0, additive refinement: the root holds a sample of the points, its children (a grid
                    of tiles of at most ``TILE_POINTS``) the rest
``tiles/*.pnts``    point clouds: ECEF positions about a tile centre (RTC_CENTER), the colour of the velocity class
                    (as the QGIS style and the web app), and the velocity, height and coherence per point in the
                    batch table (styling and picking)
``viewer.html``     a CesiumJS page that shows the tileset over OpenStreetMap (served by ``geoeyes serve``; a page
                    opened from disk cannot read the tiles)

Heights are ellipsoidal: the points' height above the geoid (EGM96) plus the geoid undulation.
"""
from __future__ import annotations

import json
import math
import shutil
import struct
from pathlib import Path

import numpy as np

from geoeyes.export.styles import class_rgb, velocity_classes
from geoeyes.io.points import read_points

TILE_POINTS = 150_000
ROOT_POINTS = 40_000
A, F = 6378137.0, 1 / 298.257223563
E2 = F * (2 - F)
CESIUM = "1.120"


def ecef(lon, lat, h) -> np.ndarray:
    lo, la = np.radians(lon), np.radians(lat)
    n = A / np.sqrt(1 - E2 * np.sin(la) ** 2)
    return np.column_stack([(n + h) * np.cos(la) * np.cos(lo), (n + h) * np.cos(la) * np.sin(lo),
                            (n * (1 - E2) + h) * np.sin(la)])


def _pad(b: bytes, start: int, fill: bytes) -> bytes:
    return b + fill * ((8 - (start + len(b)) % 8) % 8)


def pnts(xyz: np.ndarray, rgb: np.ndarray, batch: dict[str, np.ndarray]) -> bytes:
    """A 3D Tiles 1.0 point cloud: positions about their centre (RTC_CENTER), RGB, float32 batch properties."""
    centre = xyz.mean(axis=0)
    pos = (xyz - centre).astype("<f4").tobytes()
    n = len(xyz)
    ft_json = json.dumps({"POINTS_LENGTH": n, "RTC_CENTER": [float(c) for c in centre],
                          "POSITION": {"byteOffset": 0}, "RGB": {"byteOffset": len(pos)}}).encode()
    ft_json = _pad(ft_json, 28, b" ")
    ft_bin = _pad(pos + np.ascontiguousarray(rgb, np.uint8).tobytes(), 0, b"\0")
    meta, blobs, off = {}, b"", 0
    for k, v in batch.items():
        a = np.asarray(v, "<f4").tobytes()
        meta[k] = {"byteOffset": off, "componentType": "FLOAT", "type": "SCALAR"}
        blobs += a
        off += len(a)
    bt_json = _pad(json.dumps(meta).encode(), 28 + len(ft_json) + len(ft_bin), b" ")
    bt_bin = _pad(blobs, 0, b"\0")
    total = 28 + len(ft_json) + len(ft_bin) + len(bt_json) + len(bt_bin)
    header = b"pnts" + struct.pack("<6I", 1, total, len(ft_json), len(ft_bin), len(bt_json), len(bt_bin))
    return header + ft_json + ft_bin + bt_json + bt_bin


def _region(lon, lat, h) -> list[float]:
    return [math.radians(float(lon.min())), math.radians(float(lat.min())), math.radians(float(lon.max())),
            math.radians(float(lat.max())), float(h.min()) - 5.0, float(h.max()) + 5.0]


def export_3dtiles(product: str | Path, out: str | Path) -> Path:
    """Write ``out/tileset.json``, ``out/tiles/*.pnts`` and ``out/viewer.html``; returns the tileset path."""
    from geoeyes.geometry.dem import Geoid
    product, out = Path(product), Path(out)
    gdf = read_points(product / "points.parquet")
    lon, lat = gdf["lon"].to_numpy(np.float64), gdf["lat"].to_numpy(np.float64)
    vel = gdf["vel_los_mm_yr"].to_numpy(np.float64)
    h = gdf["height_m"].to_numpy(np.float64) if "height_m" in gdf else np.zeros(len(gdf))
    h = np.nan_to_num(h) + Geoid().undulation(lat, lon)
    uppers, rgb_cls = velocity_classes(vel)
    rgb = class_rgb(vel, uppers, rgb_cls)
    batch = {"vel_los_mm_yr": vel, "height_m": gdf["height_m"].to_numpy(np.float64) if "height_m" in gdf else h,
             **{c: gdf[c].to_numpy(np.float64) for c in ("temporal_coherence",) if c in gdf}}
    xyz = ecef(lon, lat, h)
    if out.exists():
        shutil.rmtree(out)
    (out / "tiles").mkdir(parents=True)
    n = len(vel)
    rng = np.random.default_rng(0)
    root_ix = np.sort(rng.choice(n, min(n, ROOT_POINTS), replace=False))
    rest = np.setdiff1d(np.arange(n), root_ix)
    k = max(1, math.ceil(math.sqrt(rest.size / TILE_POINTS)))
    lo_e = np.linspace(lon.min(), lon.max() + 1e-9, k + 1)
    la_e = np.linspace(lat.min(), lat.max() + 1e-9, k + 1)
    ci = np.clip(np.searchsorted(lo_e, lon[rest], side="right") - 1, 0, k - 1)
    cj = np.clip(np.searchsorted(la_e, lat[rest], side="right") - 1, 0, k - 1)

    def write(name: str, ix: np.ndarray) -> dict:
        (out / "tiles" / name).write_bytes(pnts(xyz[ix], rgb[ix], {key: v[ix] for key, v in batch.items()}))
        return {"uri": f"tiles/{name}"}

    span_m = max(np.ptp(lon) * 111_320 * math.cos(math.radians(lat.mean())), np.ptp(lat) * 110_540, 1.0)
    children = []
    for a in range(k):
        for b in range(k):
            ix = rest[(ci == a) & (cj == b)]
            if ix.size:
                children.append({"boundingVolume": {"region": _region(lon[ix], lat[ix], h[ix])},
                                 "geometricError": 0.0, "content": write(f"{a}_{b}.pnts", ix)})
    tileset = {"asset": {"version": "1.0", "generator": "GeoEyes", "tilesetVersion": product.name},
               "properties": {"vel_los_mm_yr": {"minimum": float(np.nanmin(vel)), "maximum": float(np.nanmax(vel))}},
               "geometricError": span_m,
               "root": {"boundingVolume": {"region": _region(lon, lat, h)}, "geometricError": span_m / 20,
                        "refine": "ADD", "content": write("root.pnts", root_ix), "children": children}}
    (out / "tileset.json").write_text(json.dumps(tileset), encoding="utf-8")
    legend = [{"lo": float(lo), "hi": float(hi), "rgb": [int(c) for c in col]}
              for lo, hi, col in zip([float(np.nanmin(vel)), *uppers[:-1]], uppers, rgb_cls, strict=True)]
    (out / "viewer.html").write_text(VIEWER.replace("__TITLE__", product.name)
                                     .replace("__LEGEND__", json.dumps(legend)).replace("__CESIUM__", CESIUM),
                                     encoding="utf-8")
    return out / "tileset.json"


VIEWER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cesium.com/downloads/cesiumjs/releases/__CESIUM__/Build/Cesium/Cesium.js"></script>
<link rel="stylesheet"
 href="https://cesium.com/downloads/cesiumjs/releases/__CESIUM__/Build/Cesium/Widgets/widgets.css">
<style>html,body,#map{margin:0;width:100%;height:100%;background:#0b1220;font:12px system-ui,sans-serif}
#legend,#size{position:absolute;left:10px;background:#0b1220e6;color:#e6edf7;padding:8px 10px;border-radius:8px}
#legend{bottom:30px}#size{top:10px}
#legend div{display:flex;align-items:center;gap:6px;margin:2px 0}
#legend span{width:12px;height:12px;display:inline-block;border-radius:3px}</style>
</head><body><div id="map"></div>
<div id="size">point size <input id="ps" type="range" min="1" max="10" value="3"></div>
<div id="legend"><b>LOS velocity, mm/yr</b></div>
<script>
const legend = __LEGEND__;
const box = document.getElementById("legend");
for (const c of legend.slice().reverse()) {
  const d = document.createElement("div");
  d.innerHTML = `<span style="background:rgb(${c.rgb.join(",")})"></span>${c.lo.toFixed(0)} … ${c.hi.toFixed(0)}`;
  box.appendChild(d);
}
const viewer = new Cesium.Viewer("map", {
  baseLayer: new Cesium.ImageryLayer(
    new Cesium.OpenStreetMapImageryProvider({ url: "https://tile.openstreetmap.org/" })),
  baseLayerPicker: false, geocoder: false, timeline: false, animation: false, sceneModePicker: true,
});
viewer.scene.globe.depthTestAgainstTerrain = false;
Cesium.Cesium3DTileset.fromUrl("tileset.json").then((ts) => {
  viewer.scene.primitives.add(ts);
  const style = (s) => (ts.style = new Cesium.Cesium3DTileStyle({ pointSize: s }));
  style(3);
  document.getElementById("ps").oninput = (e) => style(Number(e.target.value));
  viewer.zoomTo(ts, new Cesium.HeadingPitchRange(0, -0.6, 0));
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  handler.setInputAction((m) => {
    const f = viewer.scene.pick(m.position);
    if (f instanceof Cesium.Cesium3DTilePointFeature) {
      viewer.selectedEntity = new Cesium.Entity({ name: `${f.getProperty("vel_los_mm_yr").toFixed(1)} mm/yr`,
        description: `height ${f.getProperty("height_m").toFixed(1)} m` });
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
});
</script></body></html>
"""
