// The map shared by the Results, Thematic analysis and Machine learning pages: the base map (with its picker), the
// zoom buttons and the scale bar, the deck.gl overlay, and the move to the data. What every map does is written
// once here; a page adds its layers and panels.
import { MapboxOverlay } from "@deck.gl/mapbox";
import maplibregl from "maplibre-gl";
import { useEffect, useRef, useState, type MutableRefObject, type RefObject } from "react";
import { DEFAULT_BASE, mapStyle, type Base } from "../map";
import { BasemapPicker } from "./BasemapPicker";

export interface BaseMap {
  el: RefObject<HTMLDivElement>;
  map: MutableRefObject<maplibregl.Map | null>;
  overlay: MutableRefObject<MapboxOverlay | null>;
  /** The map exists (effects that need it list this). */
  ready: boolean;
  base: Exclude<Base, "none">;
  setBase: (b: Base) => void;
}

/** A MapLibre map with a deck.gl overlay. `override`: a style drawn in place of the chosen base map (3D: "none",
 * the terrain carries the base map); `rotate` / `pitch`: the initial 3D state (the page toggles them after). */
export function useBaseMap({ override, rotate = false, pitch = 0 }: { override?: Base; rotate?: boolean; pitch?: number } = {}): BaseMap {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const overlay = useRef<MapboxOverlay | null>(null);
  const [ready, setReady] = useState(false);
  const [base, setBase] = useState<Exclude<Base, "none">>(DEFAULT_BASE);

  useEffect(() => {
    if (!el.current) return;
    const m = new maplibregl.Map({
      container: el.current,
      style: mapStyle(override ?? DEFAULT_BASE),
      center: [105.82, 21.02],
      zoom: 10,
      attributionControl: { compact: true },
      dragRotate: rotate,
      pitchWithRotate: rotate,
      maxPitch: 75,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");
    // narrow: a bottom dock starts beside this column of controls
    m.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 72 }), "bottom-left");
    const ov = new MapboxOverlay({ interleaved: false, layers: [] });
    m.addControl(ov as unknown as maplibregl.IControl);
    map.current = m;
    overlay.current = ov;
    if (pitch) m.setPitch(pitch);
    setReady(true);
    return () => {
      m.remove();
      map.current = null;
      overlay.current = null;
      setReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    map.current?.setStyle(mapStyle(override ?? base));
  }, [base, override]);

  // the picker offers only real base maps; "none" is the 3D background, set through `override`
  const choose = (b: Base) => b !== "none" && setBase(b);
  return { el, map, overlay, ready, base, setBase: choose };
}

/** Go to `bounds` [w, s, e, n] whenever `key` changes (a new product, a new run); with `onlyIfOutside`, only when
 * the current view shows none of it (the user's own view is kept otherwise). */
export function useFitTo(m: BaseMap, bounds: number[] | null | undefined, key: string | null | undefined, onlyIfOutside = false) {
  const done = useRef<string | null>(null);
  useEffect(() => {
    const map = m.map.current;
    if (!map || !bounds || bounds.length !== 4 || !key || done.current === key) return;
    const first = done.current === null;
    done.current = key;
    const [w, s, e, n] = bounds;
    if (onlyIfOutside && !first) {                // the page's first data: always shown
      const v = map.getBounds();
      if (w < v.getEast() && e > v.getWest() && s < v.getNorth() && n > v.getSouth()) return;
    }
    map.fitBounds([w, s, e, n], { padding: 60, duration: 600 });
  }, [m.ready, key, bounds, onlyIfOutside, m.map]);
}

/** The map's container (fills its parent) and the base map picker. */
export function MapCanvas({ m }: { m: BaseMap }) {
  return (
    <>
      {/* maplibre-gl.css sets the map container to position: relative, hence the wrapper */}
      <div className="absolute inset-0">
        <div ref={m.el} className="h-full w-full" />
      </div>
      <BasemapPicker map={m.map} base={m.base} onChange={m.setBase} />
    </>
  );
}
