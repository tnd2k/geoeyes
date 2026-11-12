// Slopes under the products: the relief (hillshade of the Terrarium elevation tiles, as the 3D view and the rivers
// tool) and the slope steepness in classes, computed in the browser from the same tiles, so that the hillsides read on
// a satellite image that looks flat from above.
import { BitmapLayer } from "@deck.gl/layers";
import { TileLayer } from "@deck.gl/geo-layers";
import type maplibregl from "maplibre-gl";
import { useEffect, type RefObject } from "react";
import { t } from "../i18n";
import { TERRAIN_TILES } from "../map";

const DEM_SRC = "slopes-dem";
const SHADE = "slopes-hillshade";

/** Slope classes (degrees, lower bound) and their colours (RGBA): below the first, nothing is drawn. */
export const SLOPE_CLASSES: { lo: number; color: [number, number, number, number] }[] = [
  { lo: 15, color: [255, 237, 160, 95] },
  { lo: 25, color: [254, 178, 76, 125] },
  { lo: 35, color: [240, 59, 32, 150] },
  { lo: 45, color: [128, 0, 38, 170] },
];
export const SLOPE_CREDIT = "Relief and slopes: Mapzen Terrain Tiles";

/** Relief under the products while ``on`` (added again after a base-map change, below the first label layer). */
export function useSlopeRelief(map: RefObject<maplibregl.Map | null>, ready: boolean, on: boolean) {
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const add = () => {
      if (!on || !m.isStyleLoaded() || m.getLayer(SHADE)) return;
      if (!m.getSource(DEM_SRC))
        m.addSource(DEM_SRC, { type: "raster-dem", tiles: [TERRAIN_TILES], tileSize: 256, maxzoom: 14, encoding: "terrarium" });
      const label = m.getStyle().layers?.find((l) => l.type === "symbol")?.id;
      m.addLayer(
        {
          id: SHADE,
          type: "hillshade",
          source: DEM_SRC,
          // stronger than the rivers tool: the hillsides must read through a satellite image
          paint: { "hillshade-exaggeration": 0.75, "hillshade-shadow-color": "#1e1e30", "hillshade-highlight-color": "#ffffff", "hillshade-accent-color": "#44445a", "hillshade-illumination-direction": 315 },
        },
        label,
      );
    };
    const remove = () => {
      if (m.getLayer(SHADE)) m.removeLayer(SHADE);
      if (m.getSource(DEM_SRC)) m.removeSource(DEM_SRC);
    };
    if (on) {
      add();
      m.on("styledata", add);
      return () => {
        m.off("styledata", add);
        try {
          remove();
        } catch {
          /* map already removed */
        }
      };
    }
    try {
      remove();
    } catch {
      /* style not loaded */
    }
  }, [map, ready, on]);
}

/** Slope (degrees) of every pixel of a Terrarium tile, coloured by ``SLOPE_CLASSES``. */
function slopeImage(img: ImageData, z: number, y: number): ImageData {
  const w = img.width;
  const h = img.height;
  const d = img.data;
  const H = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) H[i] = d[i * 4] * 256 + d[i * 4 + 1] + d[i * 4 + 2] / 256 - 32768;
  // ground size of a pixel at the tile's centre latitude (web mercator)
  const n = Math.PI - (2 * Math.PI * (y + 0.5)) / 2 ** z;
  const lat = Math.atan(Math.sinh(n));
  const px = (156_543.03 * Math.cos(lat)) / 2 ** z / (w / 256);
  const out = new ImageData(w, h);
  const o = out.data;
  const at = (c: number, r: number) => H[Math.min(h - 1, Math.max(0, r)) * w + Math.min(w - 1, Math.max(0, c))];
  for (let r = 0; r < h; r++)
    for (let c = 0; c < w; c++) {
      // Horn's 3 x 3 gradient
      const gx = (at(c + 1, r - 1) + 2 * at(c + 1, r) + at(c + 1, r + 1) - at(c - 1, r - 1) - 2 * at(c - 1, r) - at(c - 1, r + 1)) / (8 * px);
      const gy = (at(c - 1, r + 1) + 2 * at(c, r + 1) + at(c + 1, r + 1) - at(c - 1, r - 1) - 2 * at(c, r - 1) - at(c + 1, r - 1)) / (8 * px);
      const s = (Math.atan(Math.hypot(gx, gy)) * 180) / Math.PI;
      let k = -1;
      while (k + 1 < SLOPE_CLASSES.length && s >= SLOPE_CLASSES[k + 1].lo) k++;
      if (k < 0) continue;
      const col = SLOPE_CLASSES[k].color;
      const q = (r * w + c) * 4;
      o[q] = col[0];
      o[q + 1] = col[1];
      o[q + 2] = col[2];
      o[q + 3] = col[3];
    }
  return out;
}

async function slopeTile(z: number, x: number, y: number, signal?: AbortSignal): Promise<ImageBitmap | null> {
  const url = TERRAIN_TILES.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
  const r = await fetch(url, { signal });
  if (!r.ok) return null;
  const bmp = await createImageBitmap(await r.blob());
  const cv = new OffscreenCanvas(bmp.width, bmp.height);
  const ctx = cv.getContext("2d")!;
  ctx.drawImage(bmp, 0, 0);
  return createImageBitmap(slopeImage(ctx.getImageData(0, 0, bmp.width, bmp.height), z, y));
}

/** Deck layer of the slope classes (under the products). Terrarium tiles reach ~30 m at zoom 12 and stop at 14:
 * beyond, the zoom-14 tiles are stretched. */
export function slopeLayer(opts: { three: boolean; extensions: unknown[] }) {
  return new TileLayer<ImageBitmap | null>({
    id: `slopes${opts.three ? "-3d" : ""}`,
    minZoom: 9,
    maxZoom: 14,
    tileSize: 256,
    getTileData: ({ index, signal }: { index: { x: number; y: number; z: number }; signal?: AbortSignal }) =>
      slopeTile(index.z, index.x, index.y, signal),
    renderSubLayers: (props: { id: string; data: ImageBitmap | null; tile: { boundingBox: [number[], number[]] } }) => {
      const { boundingBox } = props.tile;
      if (!props.data) return null;
      return new BitmapLayer({
        id: `${props.id}-bmp`,
        image: props.data,
        bounds: [boundingBox[0][0], boundingBox[0][1], boundingBox[1][0], boundingBox[1][1]],
        extensions: opts.extensions as never,
        ...(opts.three ? { terrainDrawMode: "drape" } : {}),
      } as never);
    },
  } as never);
}

/** The legend of the slope classes (map overlay while the tool is on). */
export function SlopeLegend() {
  const cls = SLOPE_CLASSES;
  return (
    <div className="rounded-lg border border-line-2 bg-panel/95 px-2.5 py-2 text-[11px] text-ink-2 shadow-lg shadow-black/30 backdrop-blur">
      <div className="mb-1 font-semibold text-ink">{t("Slope")}</div>
      {cls.map((c, i) => (
        <div key={c.lo} className="flex items-center gap-2">
          <span className="h-3 w-4 flex-none rounded-sm" style={{ background: `rgba(${c.color[0]},${c.color[1]},${c.color[2]},${Math.min(1, (c.color[3] / 255) * 1.6)})` }} />
          <span className="font-mono">{i + 1 < cls.length ? `${c.lo}–${cls[i + 1].lo}°` : `≥ ${c.lo}°`}</span>
        </div>
      ))}
      <div className="mt-1 max-w-[180px] leading-snug text-faint">{t("From zoom 9; ~30 m elevation tiles: a cut or a fill narrower than that does not show.")}</div>
    </div>
  );
}
