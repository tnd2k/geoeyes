// Base map picker: a square preview in the bottom-left corner of a map (with the zoom buttons and the scale bar,
// as a MapLibre control); hovering or clicking it opens the other base maps as square previews of the current view.
import maplibregl from "maplibre-gl";
import { useEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { t } from "../i18n";
import { BASES, type Base } from "../map";

type Choice = Exclude<Base, "none">;
const CHOICES: Choice[] = ["dark", "light", "satellite"];

class Holder implements maplibregl.IControl {
  el = document.createElement("div");
  onAdd() {
    this.el.className = "maplibregl-ctrl geoeyes-basemap";
    return this.el;
  }
  onRemove() {
    this.el.remove();
  }
}

/** The tile of a base map that holds the centre of the view, one zoom level out (a preview of the place). */
function previewUrl(b: Choice, m: maplibregl.Map): string {
  const c = m.getCenter();
  const z = Math.max(1, Math.min(BASES[b].maxzoom, Math.floor(m.getZoom()) - 1));
  const n = 2 ** z;
  const lat = (Math.max(-85, Math.min(85, c.lat)) * Math.PI) / 180;
  const x = Math.min(n - 1, Math.max(0, Math.floor(((c.lng + 180) / 360) * n)));
  const y = Math.min(n - 1, Math.max(0, Math.floor(((1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2) * n)));
  return BASES[b].tiles[0].replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
}

function Tile({ b, url, on, size, onClick }: { b: Choice; url: string; on: boolean; size: number; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      title={t(BASES[b].label)}
      className={`relative flex-none overflow-hidden rounded-lg border-2 bg-[#1a2740] bg-cover bg-center shadow-lg shadow-black/40 transition-transform hover:scale-[1.04] ${on ? "border-accent" : "border-white/80"}`}
      style={{ width: size, height: size, backgroundImage: url ? `url("${url}")` : undefined }}
    >
      <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-1 pt-3 pb-0.5 text-center text-[10.5px] leading-tight font-medium text-white">
        {t(BASES[b].label)}
      </span>
    </button>
  );
}

export function BasemapPicker({ map, base, onChange }: { map: RefObject<maplibregl.Map | null>; base: Base; onChange: (b: Base) => void }) {
  const [host, setHost] = useState<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const box = useRef<HTMLDivElement>(null);

  // the page creates its map in its own effect, after this one: wait for it, then join its bottom-left corner
  useEffect(() => {
    let m: maplibregl.Map | null = null;
    const holder = new Holder();
    const update = () => m && setUrls(Object.fromEntries(CHOICES.map((b) => [b, previewUrl(b, m!)])));
    let raf = requestAnimationFrame(function wait() {
      if (!map.current) {
        raf = requestAnimationFrame(wait);
        return;
      }
      m = map.current;
      m.addControl(holder, "bottom-left");
      // the corner from top to bottom: zoom buttons, scale bar, then this picker in the very corner
      const corner = holder.el.parentElement;
      if (corner) {
        for (const sel of [".maplibregl-ctrl-group", ".maplibregl-ctrl-scale"]) {
          const c = corner.querySelector(`:scope > ${sel}`);
          if (c) corner.appendChild(c);
        }
        corner.appendChild(holder.el);
      }
      setHost(holder.el);
      update();
      m.on("moveend", update);
    });
    return () => {
      cancelAnimationFrame(raf);
      if (m) {
        m.off("moveend", update);
        try {
          m.removeControl(holder);
        } catch {
          /* the map is already gone */
        }
      }
      setHost(null);
    };
  }, [map]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (!host) return null;
  const current: Choice = base === "none" ? "dark" : base;
  return createPortal(
    <div ref={box} className="flex items-end gap-2" onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        onMouseEnter={() => setOpen(true)}
        aria-expanded={open}
        aria-label={t("Base map")}
        title={t("Base map")}
        className="relative flex-none overflow-hidden rounded-lg border-2 border-white/90 bg-[#1a2740] bg-cover bg-center shadow-lg shadow-black/40"
        style={{ width: 64, height: 64, backgroundImage: urls[current] ? `url("${urls[current]}")` : undefined }}
      >
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden className="absolute top-1 left-1 drop-shadow">
          <path d="M9 2 16 6 9 10 2 6Z" fill="#fff" fillOpacity=".95" />
          <path d="m2 9.5 7 4 7-4M2 12.5l7 4 7-4" fill="none" stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
        </svg>
        <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-1 pt-3 pb-0.5 text-center text-[10.5px] leading-tight font-medium text-white">
          {t(BASES[current].label)}
        </span>
      </button>
      {open && (
        <div className="flex gap-2 rounded-xl border border-line-2 bg-panel/95 p-2 shadow-xl shadow-black/40 backdrop-blur" role="group" aria-label={t("Base map")}>
          {CHOICES.map((b) => (
            <Tile
              key={b}
              b={b}
              url={urls[b] ?? ""}
              on={b === current}
              size={56}
              onClick={() => {
                onChange(b);
                setOpen(false);
              }}
            />
          ))}
        </div>
      )}
    </div>,
    host,
  );
}
