// Velocity classes for a range the user chooses: the same Pretty Breaks (10 classes, QGIS) and jet_r colours as the
// server (geoeyes.export.styles), so a chosen range gives the classes QGIS would give over that range.
import type { VelClass } from "./api";

const CLASSES = 10;

/** Upper class bounds of QGIS Pretty Breaks (R's `pretty`); the first class starts at `minimum`. */
export function prettyBreaks(minimum: number, maximum: number, classes = CLASSES): number[] {
  if (classes < 1) return [maximum];
  const minimumCount = Math.floor(classes / 3);
  const shrink = 0.75;
  const h = 1.5;
  const adjustBias = 0.5 + 1.5 * h;
  const dx = maximum - minimum;
  let cell: number;
  let small: boolean;
  if (Math.abs(dx) <= 1e-12 && Math.abs(maximum) <= 1e-12) {
    cell = 1;
    small = true;
  } else {
    cell = Math.max(Math.abs(minimum), Math.abs(maximum));
    const u = adjustBias >= 1.5 * h + 0.5 ? Math.trunc(1 + 1 / (1 + h)) : Math.trunc(1 + 1.5 / (1 + adjustBias));
    small = dx < cell * u * Math.max(1, classes) * 1e-7 * 3;
  }
  if (small) {
    if (cell > 10) cell = 9 + cell / 10;
    cell *= shrink;
    if (minimumCount > 1) cell /= minimumCount;
  } else cell = classes > 1 ? dx / classes : dx;
  cell = Math.max(cell, 20 * 1e-7);
  const base = 10 ** Math.floor(Math.log10(cell));
  let unit = base;
  if (2 * base - cell < h * (cell - unit)) {
    unit = 2 * base;
    if (5 * base - cell < adjustBias * (cell - unit)) {
      unit = 5 * base;
      if (10 * base - cell < h * (cell - unit)) unit = 10 * base;
    }
  }
  let start = Math.floor(minimum / unit + 1e-7);
  let end = Math.ceil(maximum / unit - 1e-7);
  while (start * unit > minimum + 1e-7 * unit) start--;
  while (end * unit < maximum - 1e-7 * unit) end++;
  let k = Math.floor(0.5 + end - start);
  if (k < minimumCount) {
    k = minimumCount - k;
    if (start >= 0) {
      end += Math.floor(k / 2);
      start = start - Math.floor(k / 2) + (k % 2);
    } else {
      start -= Math.floor(k / 2);
      end = end + Math.floor(k / 2) + (k % 2);
    }
  }
  const breaks: number[] = [];
  for (let i = 1; i <= end - start; i++) breaks.push(start * unit + i * unit);
  if (!breaks.length) return breaks;
  breaks[0] = Math.max(breaks[0], minimum);
  breaks[breaks.length - 1] = Math.min(breaks[breaks.length - 1], maximum);
  if (minimum < 0 && 0 < maximum) {
    // the break near zero is exactly zero (as QGIS)
    let pos = 0;
    for (let i = 1; i < breaks.length; i++) if (Math.abs(breaks[i]) < Math.abs(breaks[i - 1])) pos = i;
    breaks[pos] = 0;
  }
  return breaks;
}

// matplotlib's jet (segment data), sampled as its 256-entry lookup table
const JET: [number, number][][] = [
  [[0, 0], [0.35, 0], [0.66, 1], [0.89, 1], [1, 0.5]],
  [[0, 0], [0.125, 0], [0.375, 1], [0.64, 1], [0.91, 0], [1, 0]],
  [[0, 0.5], [0.11, 1], [0.34, 1], [0.65, 0], [1, 0]],
];
// jet_r's segments (matplotlib `reversed()`: x → 1 − x, order reversed)
const JET_R = JET.map((s) => [...s].reverse().map(([x, y]) => [1 - x, y] as [number, number]));
// matplotlib's 256-entry table, with its own arithmetic (numpy linspace k·(1/255), searchsorted, the same
// interpolation order): the last bit decides a .5 rounding of a few channels
const LUT: number[][] = JET_R.map((s) => {
  const step = 1 / 255;
  const xs = s.map(([x]) => x * 255);
  return Array.from({ length: 256 }, (_, k) => {
    if (k === 0) return s[0][1];
    if (k === 255) return s[s.length - 1][1];
    const x = 255 * (k * step);
    let ind = 0;
    while (ind < xs.length && xs[ind] < x) ind++;
    const distance = (x - xs[ind - 1]) / (xs[ind] - xs[ind - 1]);
    return Math.min(1, Math.max(0, distance * (s[ind][1] - s[ind - 1][1]) + s[ind - 1][1]));
  });
});

// Python's round(): a tie goes to the even integer (the server's colours)
function roundHalfEven(x: number): number {
  const f = Math.floor(x);
  const d = x - f;
  if (d !== 0.5) return Math.round(x);
  return f % 2 === 0 ? f : f + 1;
}

/** `n` colours of the reversed jet ramp (as `geoeyes.export.styles.jet_r`). */
export function jetR(n: number): [number, number, number][] {
  return Array.from({ length: n }, (_, j) => {
    const x = n > 1 ? j / (n - 1) : 0;
    const k = Math.min(255, Math.floor(x * 256));
    return LUT.map((c) => roundHalfEven(c[k] * 255)) as [number, number, number];
  });
}

/** Classes over [lo, hi]; counts from `values` (records of `stride` floats, value at `at`), else -1 (unknown). */
export function rangeClasses(lo: number, hi: number, values?: { buf: Float32Array; stride: number; at: number }): VelClass[] {
  const uppers = prettyBreaks(lo, hi);
  const colors = jetR(uppers.length);
  const counts = new Array<number>(uppers.length).fill(values ? 0 : -1);
  if (values) {
    const { buf, stride, at } = values;
    for (let r = at; r < buf.length; r += stride) {
      const v = buf[r];
      if (!Number.isFinite(v)) continue;
      let k = 0;
      while (k < uppers.length - 1 && v > uppers[k]) k++;
      counts[k]++;
    }
  }
  return uppers.map((u, k) => ({ lo: k ? uppers[k - 1] : lo, hi: u, color: colors[k], count: counts[k] }));
}
