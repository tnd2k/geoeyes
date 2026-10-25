// Map composition: one layout (in sheet units, 1000 wide) drawn on a canvas, at screen size for the preview and at
// print size for the export (PNG, or a one-page PDF holding the image).
import type { LayerMeta } from "./api";

export interface Paper {
  id: string;
  label: string;
  w: number;          // mm (or px for screen formats)
  h: number;
  screen?: boolean;   // w/h are pixels, no dpi
}

export const PAPERS: Paper[] = [
  { id: "a4l", label: "A4 landscape", w: 297, h: 210 },
  { id: "a4p", label: "A4 portrait", w: 210, h: 297 },
  { id: "a3l", label: "A3 landscape", w: 420, h: 297 },
  { id: "a3p", label: "A3 portrait", w: 297, h: 420 },
  { id: "hd", label: "Slide 16:9 (1920 × 1080)", w: 1920, h: 1080, screen: true },
  { id: "4k", label: "Slide 16:9 (3840 × 2160)", w: 3840, h: 2160, screen: true },
  { id: "sq", label: "Square (2000 × 2000)", w: 2000, h: 2000, screen: true },
];

export interface Options {
  title: string;
  subtitle: string;
  legend: "right" | "inside" | "none";
  scale: boolean;
  north: boolean;
  meta: boolean;
  credits: boolean;
  frame: boolean;      // coordinate frame: lon / lat ticks and labels around the map, light grid inside
  geometry: boolean;   // satellite flight and look directions
  theme: "light" | "dark";
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Layout {
  W: number;
  H: number;
  map: Rect;
  panel: Rect | null;
  title: { y: number; sub: number } | null;
  footer: number | null;
}

const M = 26;

export function layout(p: Paper, o: Options): Layout {
  const W = 1000;
  const H = (W * p.h) / p.w;
  const head = o.title ? (o.subtitle ? 76 : 54) : 0;
  const foot = o.credits ? 24 : 0;
  const side = o.legend === "right" || (o.meta && o.legend !== "inside") ? (p.h > p.w ? 0 : 236) : 0;
  const bottom = side === 0 && (o.legend === "right" || o.meta) ? 150 : 0;     // portrait: panel under the map
  const gap = 16;
  const fl = o.frame ? 30 : 0;               // room for the latitude labels (left) and longitude labels (bottom)
  const fb = o.frame ? 16 : 0;
  const map: Rect = {
    x: M + fl,
    y: M + head,
    w: W - 2 * M - fl - (side ? side + gap : 0),
    h: H - 2 * M - head - foot - fb - (bottom ? bottom + gap : 0),
  };
  const panel = side
    ? { x: map.x + map.w + gap, y: map.y, w: side, h: map.h }
    : bottom
      ? { x: M, y: map.y + map.h + fb + gap, w: W - 2 * M, h: bottom }
      : null;
  return { W, H, map, panel, title: o.title ? { y: M + 30, sub: M + 60 } : null, footer: foot ? H - M + 2 : null };
}

const THEMES = {
  light: { bg: "#ffffff", ink: "#111827", muted: "#4b5563", faint: "#9ca3af", frame: "#9ca3af", box: "rgba(255,255,255,0.88)" },
  dark: { bg: "#0b1220", ink: "#e6edf7", muted: "#93a4bf", faint: "#6f7f99", frame: "#22324d", box: "rgba(11,18,32,0.86)" },
};

export interface SheetData {
  legend: Pick<LayerMeta, "classes" | "vel_min" | "vel_max"> | null;
  legendTitle: string;
  meta: [string, string][];
  credits: string;
  metresPerUnit: number | null;      // ground metres per sheet unit across the map (scale bar)
  ticks: { lon: Tick[]; lat: Tick[] } | null;   // positions in sheet units along the map edges
  geometry: { heading: number; look: number | null; pass: string } | null;
}

export interface Tick {
  at: number;         // sheet units (x for longitudes, y for latitudes)
  label: string;
}

/** Nice graticule step (degrees) for a span, about `n` lines. */
export function graticuleStep(span: number, n = 6): number {
  const raw = span / n;
  const p = 10 ** Math.floor(Math.log10(raw));
  for (const k of [1, 2, 2.5, 5, 10]) if (k * p >= raw) return k * p;
  return 10 * p;
}

export function degLabel(v: number, step: number, pos: string, neg: string): string {
  const dec = Math.min(4, (String(+step.toFixed(6)).split(".")[1] ?? "").length);    // as many as the step needs
  return `${Math.abs(v).toFixed(dec)}°${v >= 0 ? pos : neg}`;
}

function niceLength(maxM: number): number {
  const p = 10 ** Math.floor(Math.log10(maxM));
  for (const k of [5, 2, 1]) if (k * p <= maxM) return k * p;
  return p;
}

function decimals(classes: { lo: number; hi: number }[]): number {
  const step = classes.length > 2 ? classes[1].hi - classes[1].lo : 1;
  return step >= 5 ? 0 : step >= 0.5 ? 1 : 2;
}

/** Draw the sheet at `s` pixels per sheet unit. `mapImage` null: the map rectangle is left transparent (preview,
 *  the live map shows through). */
export function drawSheet(ctx: CanvasRenderingContext2D, s: number, L: Layout, o: Options, d: SheetData, mapImage: CanvasImageSource | null) {
  const t = THEMES[o.theme];
  const font = (px: number, weight = 400, mono = false) =>
    `${weight} ${px * s}px ${mono ? "'JetBrains Mono', Consolas, monospace" : "Inter, 'Segoe UI', system-ui, sans-serif"}`;
  ctx.save();
  ctx.fillStyle = t.bg;
  ctx.fillRect(0, 0, L.W * s, L.H * s);
  const m = L.map;
  if (mapImage) ctx.drawImage(mapImage, m.x * s, m.y * s, m.w * s, m.h * s);
  else ctx.clearRect(m.x * s, m.y * s, m.w * s, m.h * s);
  if (o.frame && d.ticks) {
    // light graticule inside, ticks on all four sides, labels left (latitude) and below (longitude)
    ctx.save();
    ctx.beginPath();
    ctx.rect(m.x * s, m.y * s, m.w * s, m.h * s);
    ctx.clip();
    ctx.strokeStyle = o.theme === "light" ? "rgba(17,24,39,0.18)" : "rgba(230,237,247,0.16)";
    ctx.lineWidth = Math.max(0.5, 0.5 * s);
    ctx.setLineDash([3 * s, 3 * s]);
    for (const k of d.ticks.lon) {
      ctx.beginPath();
      ctx.moveTo(k.at * s, m.y * s);
      ctx.lineTo(k.at * s, (m.y + m.h) * s);
      ctx.stroke();
    }
    for (const k of d.ticks.lat) {
      ctx.beginPath();
      ctx.moveTo(m.x * s, k.at * s);
      ctx.lineTo((m.x + m.w) * s, k.at * s);
      ctx.stroke();
    }
    ctx.restore();
    ctx.strokeStyle = t.ink;
    ctx.fillStyle = t.ink;
    ctx.lineWidth = Math.max(1, 0.7 * s);
    ctx.font = font(8.5);
    const tk = 4;
    ctx.textAlign = "center";
    for (const k of d.ticks.lon) {
      ctx.beginPath();
      ctx.moveTo(k.at * s, (m.y + m.h) * s);
      ctx.lineTo(k.at * s, (m.y + m.h + tk) * s);
      ctx.moveTo(k.at * s, m.y * s);
      ctx.lineTo(k.at * s, (m.y - tk) * s);
      ctx.stroke();
      ctx.fillText(k.label, k.at * s, (m.y + m.h + tk + 10) * s);
    }
    for (const k of d.ticks.lat) {
      ctx.beginPath();
      ctx.moveTo(m.x * s, k.at * s);
      ctx.lineTo((m.x - tk) * s, k.at * s);
      ctx.moveTo((m.x + m.w) * s, k.at * s);
      ctx.lineTo((m.x + m.w + tk) * s, k.at * s);
      ctx.stroke();
      ctx.save();
      ctx.translate((m.x - tk - 4) * s, k.at * s);
      ctx.rotate(-Math.PI / 2);
      ctx.fillText(k.label, 0, 0);
      ctx.restore();
    }
    ctx.textAlign = "left";
  }
  ctx.strokeStyle = t.frame;
  ctx.lineWidth = Math.max(1, 0.8 * s);
  ctx.strokeRect(m.x * s, m.y * s, m.w * s, m.h * s);

  if (o.geometry && d.geometry) {
    // flight (grey, through the centre) and look (blue, from the centre) directions; north up on the map
    const g = d.geometry;
    const R = 26;
    const cx = (o.legend === "inside" ? m.x + R + 18 : m.x + m.w - R - 18) * s;
    const cy = (o.legend === "inside" ? m.y + R + 18 : m.y + m.h - R - 30) * s;
    ctx.fillStyle = t.box;
    ctx.fillRect(cx - (R + 12) * s, cy - (R + 10) * s, (2 * R + 24) * s, (2 * R + 30) * s);
    const arrow = (az: number, from: number, to: number, color: string, width: number) => {
      const dx = Math.sin((az * Math.PI) / 180);
      const dy = -Math.cos((az * Math.PI) / 180);
      const x0 = cx + dx * from * s, y0 = cy + dy * from * s;
      const x1 = cx + dx * to * s, y1 = cy + dy * to * s;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = width * s;
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1 - dx * 5 * s, y1 - dy * 5 * s);
      ctx.stroke();
      ctx.beginPath();                                    // head
      ctx.moveTo(x1, y1);
      ctx.lineTo(x1 - dx * 8 * s - dy * 4 * s, y1 - dy * 8 * s + dx * 4 * s);
      ctx.lineTo(x1 - dx * 8 * s + dy * 4 * s, y1 - dy * 8 * s - dx * 4 * s);
      ctx.closePath();
      ctx.fill();
    };
    arrow(g.heading, -R, R, t.ink, 1.6);
    if (g.look != null) arrow(g.look, 0, R * 0.8, "#2a78d6", 1.6);
    ctx.textAlign = "center";
    ctx.font = font(7);
    ctx.fillStyle = t.muted;
    ctx.fillText(g.look != null ? "flight · look" : "flight", cx, cy + (R + 8) * s);
    ctx.fillStyle = t.ink;
    ctx.font = font(8, 700);
    ctx.fillText(g.pass, cx, cy + (R + 17) * s);
    ctx.textAlign = "left";
  }

  if (L.title) {
    ctx.fillStyle = t.ink;
    ctx.textBaseline = "alphabetic";
    ctx.font = font(26, 700);
    ctx.fillText(o.title, M * s, L.title.y * s, (L.W - 2 * M) * s);
    if (o.subtitle) {
      ctx.fillStyle = t.muted;
      ctx.font = font(14);
      ctx.fillText(o.subtitle, M * s, L.title.sub * s, (L.W - 2 * M) * s);
    }
  }

  // ---------------------------------------------------------------- inside the map
  if (o.north) {
    const cx = (m.x + m.w - 30) * s;
    const cy = (m.y + 34) * s;
    ctx.fillStyle = t.box;
    ctx.beginPath();
    ctx.arc(cx, cy, 20 * s, 0, 2 * Math.PI);
    ctx.fill();
    ctx.fillStyle = t.ink;
    ctx.beginPath();
    ctx.moveTo(cx, cy - 14 * s);
    ctx.lineTo(cx + 7 * s, cy + 9 * s);
    ctx.lineTo(cx, cy + 4 * s);
    ctx.lineTo(cx - 7 * s, cy + 9 * s);
    ctx.closePath();
    ctx.fill();
    ctx.font = font(9, 700);
    ctx.textAlign = "center";
    ctx.fillText("N", cx, cy - 16 * s - 1);
    ctx.textAlign = "left";
  }
  if (o.scale && d.metresPerUnit) {
    const maxM = d.metresPerUnit * m.w * 0.25;
    const len = niceLength(maxM);
    const wU = len / d.metresPerUnit;
    const x0 = (o.legend === "inside" ? m.x + m.w - wU - 26 : m.x + 18) * s;
    const y0 = (m.y + m.h - 24) * s;
    ctx.fillStyle = t.box;
    ctx.fillRect(x0 - 8 * s, y0 - 20 * s, (wU + 16) * s + 30 * s, 32 * s);
    const seg = 4;
    for (let k = 0; k < seg; k++) {
      ctx.fillStyle = k % 2 ? t.bg : t.ink;
      ctx.fillRect(x0 + (k * wU * s) / seg, y0, (wU * s) / seg, 5 * s);
    }
    ctx.strokeStyle = t.ink;
    ctx.lineWidth = Math.max(1, 0.6 * s);
    ctx.strokeRect(x0, y0, wU * s, 5 * s);
    ctx.fillStyle = t.ink;
    ctx.font = font(9.5);
    const km = len >= 1000;
    const lab = (v: number) => (km ? `${v / 1000}` : `${v}`);
    ctx.textAlign = "center";
    ctx.fillText("0", x0, y0 - 5 * s);
    ctx.fillText(lab(len / 2), x0 + (wU * s) / 2, y0 - 5 * s);
    ctx.fillText(`${lab(len)} ${km ? "km" : "m"}`, x0 + wU * s + 8 * s, y0 - 5 * s);
    ctx.textAlign = "left";
  }

  // ---------------------------------------------------------------- legend and metadata
  const drawLegend = (x: number, y: number, w: number, boxed: boolean): number => {
    if (!d.legend) return y;
    const cls = [...d.legend.classes].reverse();
    const row = 15;
    const h = 44 + cls.length * row + 30;
    if (boxed) {
      ctx.fillStyle = t.box;
      ctx.fillRect(x * s, y * s, w * s, h * s);
      x += 10;
      y += 6;
      w -= 20;
    }
    ctx.fillStyle = t.ink;
    ctx.font = font(12.5, 700);
    ctx.fillText(d.legendTitle, x * s, (y + 16) * s, w * s);
    ctx.fillStyle = t.muted;
    ctx.font = font(9.5);
    ctx.fillText("mm/yr, Pretty Breaks over min–max", x * s, (y + 31) * s, w * s);
    const dec = decimals(d.legend.classes);
    cls.forEach((c, i) => {
      const yy = y + 44 + i * row;
      ctx.fillStyle = `rgb(${c.color.join(",")})`;
      ctx.beginPath();
      ctx.arc((x + 6) * s, (yy + 5) * s, 5 * s, 0, 2 * Math.PI);
      ctx.fill();
      ctx.fillStyle = t.ink;
      ctx.font = font(10.5, 400, true);
      ctx.fillText(`${c.lo.toFixed(dec)} … ${c.hi.toFixed(dec)}`, (x + 18) * s, (yy + 9) * s);
    });
    const yb = y + 44 + cls.length * row + 8;
    ctx.fillStyle = t.muted;
    ctx.font = font(9);
    ctx.fillText(`min ${d.legend.vel_min.toFixed(1)} · max ${d.legend.vel_max.toFixed(1)}`, x * s, (yb + 4) * s, w * s);
    ctx.fillText("+ toward the satellite, − away", x * s, (yb + 16) * s, w * s);
    return (boxed ? y + h - 6 : yb + 22) + 10;
  };
  const drawMeta = (x: number, y: number, w: number, bottom: number) => {
    if (!o.meta || !d.meta.length || y + 58 > bottom) return;
    ctx.fillStyle = t.ink;
    ctx.font = font(12, 700);
    ctx.fillText("Product", x * s, (y + 12) * s);
    let yy = y + 30;
    for (const [k, v] of d.meta) {
      if (yy + 16 > bottom) break;                         // what does not fit is left out, never drawn outside
      ctx.fillStyle = t.muted;
      ctx.font = font(9);
      ctx.fillText(k, x * s, yy * s, w * s);
      ctx.fillStyle = t.ink;
      ctx.font = font(10.5);
      ctx.fillText(v, x * s, (yy + 13) * s, w * s);
      yy += 30;
    }
  };
  if (o.legend === "inside") drawLegend(m.x + 14, m.y + m.h - (d.legend ? 44 + d.legend.classes.length * 15 + 30 : 0) - 14, 190, true);
  if (L.panel) {
    const p = L.panel;
    if (p.w > p.h) {                                     // panel under the map (portrait)
      if (o.legend === "right") drawLegend(p.x, p.y, p.w / 2 - 10, false);
      drawMeta(o.legend === "right" ? p.x + p.w / 2 + 10 : p.x, p.y, p.w / 2 - 10, p.y + p.h);
    } else {
      const y = o.legend === "right" ? drawLegend(p.x, p.y, p.w, false) : p.y;
      drawMeta(p.x, y + 6, p.w, p.y + p.h);
    }
  }
  if (L.footer && o.credits) {
    ctx.fillStyle = t.faint;
    ctx.font = font(8.5);
    ctx.fillText(d.credits, M * s, L.footer * s, (L.W - 2 * M) * s);
  }
  ctx.restore();
}

/** Ground metres per CSS pixel at the map centre (MapLibre: 512 px tiles). */
export function metresPerPixel(lat: number, zoom: number): number {
  return (40075016.686 * Math.cos((lat * Math.PI) / 180)) / (512 * 2 ** zoom);
}

/** One-page PDF holding a JPEG (page size in points). No dependency: JPEG goes in as a DCTDecode image. */
export function pdfFromJpeg(jpeg: Uint8Array, wPx: number, hPx: number, wPt: number, hPt: number): Blob {
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  const offsets: number[] = [];
  let len = 0;
  const push = (b: Uint8Array | string) => {
    const u = typeof b === "string" ? enc.encode(b) : b;
    parts.push(u);
    len += u.length;
  };
  const obj = (n: number, body: string | (() => void)) => {
    offsets[n] = len;
    push(`${n} 0 obj\n`);
    if (typeof body === "string") push(body);
    else body();
    push("\nendobj\n");
  };
  push("%PDF-1.4\n%\xE2\xE3\xCF\xD3\n");
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
  obj(3, `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${wPt.toFixed(2)} ${hPt.toFixed(2)}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`);
  obj(4, () => {
    push(`<< /Type /XObject /Subtype /Image /Width ${wPx} /Height ${hPx} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`);
    push(jpeg);
    push("\nendstream");
  });
  const content = `q ${wPt.toFixed(2)} 0 0 ${hPt.toFixed(2)} 0 0 cm /Im0 Do Q`;
  obj(5, `<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
  const xref = len;
  push(`xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("")}`);
  push(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`);
  return new Blob(parts as BlobPart[], { type: "application/pdf" });
}
