"""L4 of the landslide study: event rainfall as a spatial predictor (H2).

Rain maps per event from the daily CHIRPS v3 ``sat`` grids (0.05°): totals over 5, 10 and 30 days up to the event
day and the largest daily rain from 6 days before to the day after. Each 30 m cell takes the bilinear value of
the pixel centres. The model columns are the rain **relative to the event's mean over the study grid**
(``rain_*_rel``), so that a pooled model learns where it rained more within an event, not which event it is;
the raw millimetres run as a variant.

Test (the champion data: pooled, reliable polygons, slope domain): out-of-fold AUC with and without the rain
columns on spatial blocks of 10 km (a block holds whole rain pixels) and of the study's first size. Null: the
rain fields replaced by phase-randomised fields (the same amplitude spectrum, hence the same variogram and
cross-correlation between the four layers; Theiler et al. 1992), ``N_NULL`` of them; H2 holds only when the gain
of the real rain exceeds the 95th percentile of the null gains.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CHIRPS_SAT = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/sat/{y}/chirps-v3.0.sat.{y}.{m:02d}.{d:02d}.tif"
RES = 0.05
PAD_DEG = 0.1                      # pixels around the study grid (bilinear edges)
WINDOWS = {"rain_5d": (-4, 0), "rain_10d": (-9, 0), "rain_30d": (-29, 0)}    # days relative to the event day
# 5/10/30 since the L0 gate (2026-11-05); the L4 results on disk were computed with 3/7/30
MAX_WINDOW = (-6, 1)
LAYERS = (*WINDOWS, "rain_max1d")
BLOCK_NULL_M = 10_000.0
N_NULL = 100
DRAWS = 5
MODELS = ("random_forest", "logistic")


# ---------------------------------------------------------------- data
def _box(bounds) -> tuple[float, float, float, float]:
    w, s, e, n = bounds
    return (np.floor((w - PAD_DEG) / RES) * RES, np.floor((s - PAD_DEG) / RES) * RES,
            np.ceil((e + PAD_DEG) / RES) * RES, np.ceil((n + PAD_DEG) / RES) * RES)


def daily_grids(cache: Path, bounds, start: str, end: str) -> tuple[np.ndarray, tuple, list[str]]:
    """Daily CHIRPS v3 ``sat`` rain (mm) on the pixels of the padded box: (days, rows, cols) north up, the box
    (west, south, east, north) and the dates; cached as ``<cache>/chirps3_sat_grid_<start>_<end>_<box>.npz``."""
    import rasterio
    from rasterio.windows import from_bounds

    from geoeyes.ml.layers import _ENV
    box = _box(bounds)
    f = cache / f"chirps3_sat_grid_{start}_{end}_{'_'.join(f'{v:.2f}' for v in box)}.npz"
    if f.exists():
        z = np.load(f)
        return z["mm"], tuple(z["box"]), [str(d) for d in z["dates"]]
    days = pd.date_range(start, end)
    out = []
    for day in days:
        url = CHIRPS_SAT.format(y=day.year, m=day.month, d=day.day)
        with rasterio.Env(**_ENV), rasterio.open("/vsicurl/" + url) as src:
            win = from_bounds(*box, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=win, boundless=True).astype(np.float32)
            if src.nodata is not None:
                a[a == src.nodata] = np.nan
        a[a < 0] = np.nan
        out.append(a)
    mm = np.stack(out)
    dates = [d.date().isoformat() for d in days]
    cache.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(f, mm=mm, box=np.array(box), dates=np.array(dates))
    return mm, box, dates


def event_layers(mm: np.ndarray, dates: list[str], day0: str) -> dict[str, np.ndarray]:
    """The four rain layers (mm) on the pixel grid for an event day."""
    k0 = dates.index(day0)
    out = {name: np.nansum(mm[k0 + a:k0 + b + 1], axis=0) for name, (a, b) in WINDOWS.items()}
    a, b = MAX_WINDOW
    out["rain_max1d"] = np.nanmax(mm[k0 + a:k0 + b + 1], axis=0)
    return out


def sample(field: np.ndarray, box, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Bilinear value of a north-up pixel grid over ``box`` at the points (pixel centres as nodes)."""
    from scipy.ndimage import map_coordinates
    w, _, _, n = box
    col = (np.asarray(lon) - w) / RES - 0.5
    row = (n - np.asarray(lat)) / RES - 0.5
    return map_coordinates(np.asarray(field, np.float64), [row, col], order=1, mode="nearest")


def phase_randomised(fields: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Surrogates of a stack (k, h, w): the same random Fourier phases for every layer, so each keeps its amplitude
    spectrum (variogram) and the layers keep their cross-spectra; the mean is kept."""
    mean = fields.mean(axis=(1, 2), keepdims=True)
    spec = np.fft.fft2(fields - mean)
    theta = np.angle(np.fft.fft2(rng.standard_normal(fields.shape[1:])))     # Hermitian: a real field comes back
    return np.real(np.fft.ifft2(spec * np.exp(1j * theta)[None])) + mean


def relative(t: pd.DataFrame, cols, means: dict) -> pd.DataFrame:
    """Rain columns divided by the event mean over the study grid (``<col>_rel``)."""
    for c in cols:
        t[f"{c}_rel"] = t[c] / t["event"].map(lambda e, c=c: means[e][c])
    return t


# ---------------------------------------------------------------- test
def _auc_jobs(tabs, cols_of, blocks, seed, folds):
    from joblib import delayed

    from geoeyes.landslide.model import _oof_job
    jobs, keys = [], []
    for key, (name, cols) in cols_of.items():
        for d, t in enumerate(tabs):
            for bm in blocks:
                jobs.append(delayed(_oof_job)(name, seed, t[cols], t.label.to_numpy(), t[f"block_{bm:g}"].to_numpy(),
                                              folds))
                keys.append((key, bm, d))
    return jobs, keys


def _scores(tabs, keys, preds) -> dict:
    from geoeyes.landslide.model import scores
    out: dict = {}
    for (key, bm, d), p in zip(keys, preds, strict=True):
        out.setdefault(key, {}).setdefault(f"spatial_{bm:g}", {})[d] = scores(tabs[d].label.to_numpy(), p)["auc"]
    return out


def run_rain(study, cache_root: Path, progress=None, n_null: int = N_NULL) -> dict:
    """L4: ``rain/`` (rain_<event>.parquet, rain.json, l4_report.md, rain_maps.png, manifest)."""
    from geoeyes.io.manifest import InputRef, Manifest, atomic_write_json
    from geoeyes.landslide.labels import grid_for, study_area
    from geoeyes.landslide.model import EventData, PooledData, Spec, run_jobs
    say = progress or (lambda m: log.info("%s", m))
    p = study.models
    area = study_area(study)
    grid = grid_for(area.bounds, study.labels.cell_m)
    main = Spec(aspect=p.aspect, roads=p.roads, reliable=p.reliable, domain_deg=p.domain_deg)
    out_dir = study.step_dir("rain")
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_root / "rainfall"

    pix, cells, means = {}, {}, {}
    for ev, day0 in study.events:
        d0 = pd.Timestamp(day0)
        start = (d0 + pd.Timedelta(days=min(a for a, _ in [*WINDOWS.values(), MAX_WINDOW]))).date().isoformat()
        end = (d0 + pd.Timedelta(days=MAX_WINDOW[1])).date().isoformat()
        say(f"L4 {ev}: CHIRPS v3 daily {start} .. {end}")
        mm, box, dates = daily_grids(cache, area.bounds, start, end)
        lay = event_layers(mm, dates, d0.date().isoformat())
        pix[ev] = (np.stack([lay[c] for c in LAYERS]), box)
        pred = pd.read_parquet(study.step_dir("predictors") / f"predictors_{ev}.parquet",
                               columns=["cell", "lon", "lat"])
        t = pred[["cell"]].copy()
        for i, c in enumerate(LAYERS):
            t[c] = sample(pix[ev][0][i], box, pred.lon.to_numpy(), pred.lat.to_numpy()).astype(np.float32)
        cells[ev] = (t, pred)
        means[ev] = {c: float(t[c].mean()) for c in LAYERS}
        t.to_parquet(out_dir / f"rain_{ev}.parquet", index=False)
        say(f"L4 {ev}: " + ", ".join(f"{c} {t[c].min():.0f}-{t[c].max():.0f} mm" for c in LAYERS)
            + f" ({pix[ev][0].shape[1]} x {pix[ev][0].shape[2]} pixels)")

    data = {ev: EventData(study, ev, grid.nx) for ev, _ in study.events}
    pooled = PooledData(list(data.values()))
    base_cols = {name: pooled.columns(main, "logistic" if name == "logistic" else "trees") for name in MODELS}
    rel = [f"{c}_rel" for c in LAYERS]
    blocks = tuple(dict.fromkeys((BLOCK_NULL_M, p.blocks_m[0])))

    base_tabs = []
    for d in range(min(DRAWS, pooled.draws)):
        t = pooled.rows(main, d)
        for bm in blocks:
            if f"block_{bm:g}" not in t:
                k = max(1, round(bm / study.labels.cell_m))
                ky, kx = np.divmod(t.cell.to_numpy(), grid.nx)
                t[f"block_{bm:g}"] = (ky // k) * 100_000 + kx // k
        base_tabs.append(t)

    def with_rain(t: pd.DataFrame, rain_of: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """The rows with the rain columns of their own event (raw and relative)."""
        r = pd.concat([v.assign(event=ev) for ev, v in rain_of.items()], ignore_index=True)
        return relative(t.merge(r, on=["event", "cell"], how="left"), LAYERS, means)

    real_rain = {ev: cells[ev][0] for ev in cells}
    tabs = [with_rain(t, real_rain) for t in base_tabs]
    say(f"L4: pooled {len(tabs[0])} rows per draw, {len(tabs)} draws; blocks {list(blocks)} m")
    cols_of = {}
    for name in MODELS:
        cols_of[f"{name}:base"] = (name, base_cols[name])
        cols_of[f"{name}:rain_rel"] = (name, base_cols[name] + rel)
        cols_of[f"{name}:rain_mm"] = (name, base_cols[name] + list(LAYERS))
        cols_of[f"{name}:rain_only"] = (name, rel)
    jobs, keys = _auc_jobs(tabs, cols_of, blocks, p.seed, p.folds)
    real = _scores(tabs, keys, run_jobs(jobs))

    def gain(sc: dict, key: str, bm: float) -> np.ndarray:
        b, r = sc[f"{key.split(':')[0]}:base"][f"spatial_{bm:g}"], sc[key][f"spatial_{bm:g}"]
        return np.array([r[d] - b[d] for d in sorted(r)])

    # null: phase-randomised fields per event (the same random phases for the four layers of an event)
    say(f"L4: null test, {n_null} phase-randomised rain fields (random forest, blocks {BLOCK_NULL_M:g} m)")
    rng = np.random.default_rng(p.seed)
    null_gain = []
    for j in range(n_null):
        fake = {}
        for ev, (stack, box) in pix.items():
            sur = phase_randomised(np.nan_to_num(stack, nan=float(np.nanmean(stack))), rng)
            t, pred = cells[ev]
            f = t[["cell"]].copy()
            for i, c in enumerate(LAYERS):
                f[c] = sample(sur[i], box, pred.lon.to_numpy(), pred.lat.to_numpy()).astype(np.float32)
            fake[ev] = f
        d = j % len(tabs)
        null_gain.append((d, with_rain(base_tabs[d], fake)))
        if (j + 1) % 20 == 0:
            say(f"L4: null fields {j + 1}/{n_null}")
    from joblib import delayed

    from geoeyes.landslide.model import _oof_job
    name = "random_forest"
    jobs = [delayed(_oof_job)(name, p.seed, t[base_cols[name] + rel], t.label.to_numpy(),
                              t[f"block_{BLOCK_NULL_M:g}"].to_numpy(), p.folds) for _, t in null_gain]
    from geoeyes.landslide.model import scores
    preds = run_jobs(jobs)
    base_rf = real[f"{name}:base"][f"spatial_{BLOCK_NULL_M:g}"]
    nulls = np.array([scores(t.label.to_numpy(), pr)["auc"] - base_rf[d]
                      for (d, t), pr in zip(null_gain, preds, strict=True)])
    g_real = gain(real, f"{name}:rain_rel", BLOCK_NULL_M)
    q95 = float(np.quantile(nulls, 0.95))
    res = {
        "study": study.name, "source": "CHIRPS v3.0 daily sat (Climate Hazards Center, UC Santa Barbara), 0.05°",
        "events": {ev: {"day": day0, "pixels": list(pix[ev][0].shape[1:]), "grid_mean_mm": means[ev],
                        "range_mm": {c: [float(cells[ev][0][c].min()), float(cells[ev][0][c].max())] for c in LAYERS}}
                   for ev, day0 in study.events},
        "main": asdict(main), "layers": list(LAYERS), "windows": {**WINDOWS, "rain_max1d": MAX_WINDOW},
        "auc": {k: {b: {"mean": round(float(np.mean(list(v.values()))), 4),
                        "sd": round(float(np.std(list(v.values()), ddof=1)), 4) if len(v) > 1 else 0.0}
                    for b, v in s.items()} for k, s in real.items()},
        "gain": {f"{k}@{bm:g}": round(float(gain(real, k, bm).mean()), 4)
                 for k in cols_of if not k.endswith(":base") for bm in blocks},
        "null": {"n": int(len(nulls)), "model": name, "block_m": BLOCK_NULL_M,
                 "gain_real": round(float(g_real.mean()), 4),
                 "gain_real_per_draw": [round(float(x), 4) for x in g_real],
                 "null_mean": round(float(nulls.mean()), 4), "null_q95": round(q95, 4),
                 "p_value": round(float((np.sum(nulls >= g_real.mean()) + 1) / (len(nulls) + 1)), 4),
                 "h2": bool(g_real.mean() > q95)},
    }
    files = plot_rain(pix, nulls, g_real.mean(), out_dir)
    atomic_write_json(out_dir / "rain.json", res)
    (out_dir / "l4_report.md").write_text(report_md(res), encoding="utf-8")
    m = Manifest(kind="landslide_rain", id=f"{study.name}/rain", engine="geoeyes.landslide.rain",
                 inputs=[InputRef("labels", str(study.step_dir("labels"))),
                         InputRef("predictors", str(study.step_dir("predictors")))],
                 params={"layers": list(LAYERS), "windows": res["windows"], "n_null": n_null, "draws": len(tabs),
                         "blocks": list(blocks), "main": asdict(replace(main))},
                 metrics=res["null"])
    m.add_outputs(out_dir, [*files, "rain.json", "l4_report.md", *[f"rain_{ev}.parquet" for ev in cells]])
    m.write(out_dir)
    return res


# ---------------------------------------------------------------- outputs
def plot_rain(pix: dict, nulls: np.ndarray, real_gain: float, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n_ev = len(pix)
    fig, axs = plt.subplots(n_ev + 1, len(LAYERS), figsize=(4 * len(LAYERS), 2.2 * n_ev + 3))
    for r, (ev, (stack, box)) in enumerate(pix.items()):
        for c, name in enumerate(LAYERS):
            ax = axs[r, c]
            im = ax.imshow(stack[c], extent=(box[0], box[2], box[1], box[3]), cmap="Blues")
            plt.colorbar(im, ax=ax, shrink=0.7, label="mm")
            ax.set_title(f"{ev} {name}", fontsize=9)
    for ax in axs[n_ev, 1:]:
        ax.axis("off")
    ax = axs[n_ev, 0]
    ax.hist(nulls, bins=25, color="0.6")
    ax.axvline(real_gain, color="k", lw=2, label="real rain")
    ax.axvline(np.quantile(nulls, 0.95), color="k", ls="--", lw=1, label="null 95 %")
    ax.set_xlabel("Δ AUC (random forest, 10 km blocks)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "rain_maps.png", dpi=110)
    plt.close(fig)
    return ["rain_maps.png"]


def report_md(res: dict) -> str:
    lines = [f"# L4 — event rainfall as a predictor ({res['study']})", "", f"Source: {res['source']}.", ""]
    lines += ["| event | day | pixels | " + " | ".join(f"{c} (mm, grid mean)" for c in res["layers"]) + " |",
              "|---|---|---|" + "---|" * len(res["layers"])]
    for ev, e in res["events"].items():
        lines.append(f"| {ev} | {e['day']} | {e['pixels'][0]} x {e['pixels'][1]} | "
                     + " | ".join(f"{e['grid_mean_mm'][c]:.0f} ({e['range_mm'][c][0]:.0f}–{e['range_mm'][c][1]:.0f})"
                                  for c in res["layers"]) + " |")
    lines += ["", "## Out-of-fold AUC (pooled, champion data)", "", "| model | " +
              " | ".join(sorted({b for s in res["auc"].values() for b in s})) + " |", "|---|---|---|"]
    bs = sorted({b for s in res["auc"].values() for b in s})
    for k, s in res["auc"].items():
        lines.append(f"| {k} | " + " | ".join(f"{s[b]['mean']:.3f} ± {s[b]['sd']:.3f}" if b in s else "" for b in bs)
                     + " |")
    n = res["null"]
    lines += ["", "## Null test", "",
              f"- gain of the real rain (random forest, relative rain, blocks {n['block_m']:g} m): "
              f"{n['gain_real']:+.4f} (per draw {n['gain_real_per_draw']})",
              f"- {n['n']} phase-randomised fields: mean {n['null_mean']:+.4f}, 95th percentile {n['null_q95']:+.4f}, "
              f"p = {n['p_value']}",
              f"- **H2 {'holds' if n['h2'] else 'does not hold'}** "
              "(the real gain must exceed the null 95th percentile)."]
    return "\n".join(lines) + "\n"


def summary(res: dict) -> str:
    return json.dumps(res["null"], indent=1)
