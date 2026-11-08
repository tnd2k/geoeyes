"""Report figures (matplotlib, Agg): maps as PNG (hundreds of thousands of points), charts as SVG.

Colour by role: the LOS velocity map uses the classes of QGIS and the web app (Pretty Breaks, 10 classes over the
full min-max, jet_r: red away from the satellite, blue toward it); magnitudes on one blue hue; used / not used in
blue / grey with a legend.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, RED, GREY, SURFACE = "#2a78d6", "#e34948", "#898781", "#ffffff"
DIVERGING = ["#7a1c1c", "#c23a39", "#e98a86", "#f0efec", "#86b6ef", "#2a78d6", "#0d366b"]


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial"], "font.size": 8,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlesize": 9, "axes.titlecolor": INK,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
        "legend.frameon": False, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "svg.fonttype": "path", "savefig.bbox": "tight", "savefig.pad_inches": 0.05})
    return plt


def diverging_cmap():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("geoeyes_div", DIVERGING)


def _vlim(v) -> float:
    """Symmetric colour limit covering the full velocity range (no percentile clipping)."""
    return float(max(abs(np.nanmin(v)), abs(np.nanmax(v)), 1e-3))


def _scalebar(ax, lat0: float):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    width_km = (x1 - x0) * 111.32 * np.cos(np.radians(lat0))
    nice = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100]
    km = max([n for n in nice if n <= width_km / 4] or [nice[0]])
    dx = km / (111.32 * np.cos(np.radians(lat0)))
    xs, ys = x0 + 0.05 * (x1 - x0), y0 + 0.05 * (y1 - y0)
    ax.plot([xs, xs + dx], [ys, ys], color=INK, lw=2, solid_capstyle="butt", zorder=5)
    ax.text(xs + dx / 2, ys + 0.015 * (y1 - y0), f"{km:g} km", ha="center", va="bottom", color=INK, fontsize=7,
            zorder=5)
    ax.annotate("N", xy=(x1 - 0.05 * (x1 - x0), y1 - 0.05 * (y1 - y0)),
                xytext=(x1 - 0.05 * (x1 - x0), y1 - 0.15 * (y1 - y0)), ha="center", va="center", color=INK,
                fontsize=8, fontweight="bold", arrowprops={"arrowstyle": "-|>", "color": INK, "lw": 1}, zorder=5)


def _los_inset(ax, heading: float | None, look_side: str):
    """Flight direction and look direction arrows (map view) in the lower-right corner."""
    if heading is None:
        return
    ins = ax.inset_axes([0.80, 0.03, 0.17, 0.17])
    ins.set_xlim(-1.3, 1.3)
    ins.set_ylim(-1.3, 1.3)
    ins.set_aspect("equal")
    ins.axis("off")
    h = np.radians(heading)
    fx, fy = np.sin(h), np.cos(h)
    s = 1 if look_side == "right" else -1
    lx, ly = s * fy, -s * fx
    ins.annotate("", xy=(fx, fy), xytext=(-fx, -fy), arrowprops={"arrowstyle": "-|>", "color": INK2, "lw": 1.2})
    ins.annotate("", xy=(lx * 0.9, ly * 0.9), xytext=(0, 0), arrowprops={"arrowstyle": "-|>", "color": BLUE,
                                                                          "lw": 1.2})
    ins.text(0, -1.3, "flight / look", ha="center", va="top", fontsize=6, color=INK2)


def velocity_map(pts, out: Path, *, reference=None, heading=None, look_side="right", column="vel_los_mm_yr",
                 label="LOS velocity (mm/yr), + toward the satellite", marks=()) -> Path:
    """``marks``: (lon, lat, text) labels drawn over the points (the hot spots of the assessment)."""
    plt = _plt()
    v = pts[column].to_numpy(float)
    lon, lat = pts["lon"].to_numpy(float), pts["lat"].to_numpy(float)
    order = np.argsort(np.abs(v))                        # extremes drawn last
    lim = _vlim(v)
    lat0 = float(np.nanmean(lat))
    aspect = 1 / np.cos(np.radians(lat0))
    w = np.ptp(lon) / aspect
    hgt = np.ptp(lat)
    fig_w = 6.3
    fig, ax = plt.subplots(figsize=(fig_w, min(max(fig_w * hgt / max(w, 1e-9), 3.0), 8.0)))
    size = float(np.clip(2.0e4 / max(len(v), 1), 0.05, 4.0))
    # the classes and colours of QGIS and the web app (Pretty Breaks over min-max, jet_r): one map, one reading
    from matplotlib.colors import BoundaryNorm, ListedColormap

    from geoeyes.export.styles import class_bounds, jet_r
    vmin, vmax = float(np.nanmin(v)), float(np.nanmax(v))
    lowers, uppers = class_bounds(v)
    bounds = [lowers[0], *uppers]
    if len(bounds) < 2 or bounds[-1] <= bounds[0]:
        bounds = [vmin - lim * 1e-3, vmax + lim * 1e-3]
    colors = [tuple(int(c) / 255 for c in rgb.split(",")) for rgb in jet_r(len(bounds) - 1)]
    sc = ax.scatter(lon[order], lat[order], c=v[order], s=size, cmap=ListedColormap(colors),
                    norm=BoundaryNorm(bounds, len(colors)), linewidths=0, rasterized=True)
    ax.set_aspect(aspect)
    ax.grid(False)
    ax.tick_params(labelsize=7)
    if isinstance(reference, dict) and reference.get("lon") is not None:
        ax.scatter([reference["lon"]], [reference["lat"]], marker="*", s=110, color="#ffffff", edgecolors=INK,
                   linewidths=0.8, zorder=6, label="reference area")
        ax.legend(loc="upper left", fontsize=7)
    for x, y, text in marks:
        ax.annotate(text, (x, y), xytext=(6, 6), textcoords="offset points", fontsize=7.5, fontweight="bold",
                    color=INK, zorder=7, bbox={"boxstyle": "round,pad=0.2", "fc": SURFACE, "ec": INK, "lw": 0.6},
                    arrowprops={"arrowstyle": "-", "color": INK, "lw": 0.6})
    _scalebar(ax, lat0)
    _los_inset(ax, heading, look_side)
    cb = fig.colorbar(sc, ax=ax, shrink=0.8, pad=0.02, ticks=bounds, spacing="uniform")
    step = (bounds[2] - bounds[1]) if len(bounds) > 3 else (bounds[-1] - bounds[0])
    dec = 0 if step >= 5 else 1 if step >= 0.5 else 2
    cb.ax.set_yticklabels([f"{b:.{dec}f}" for b in bounds], fontsize=7)
    cb.set_label(label, color=INK2)
    cb.outline.set_visible(False)
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def distributions(stats_pts, out: Path) -> Path:
    """Velocity, its standard error and temporal coherence: three histograms, one hue each."""
    plt = _plt()
    cols = [("vel_los_mm_yr", "LOS velocity (mm/yr)"), ("vel_std_mm_yr", "Velocity standard error (mm/yr)"),
            ("temporal_coherence", "Temporal coherence"), ("dem_err_m", "Height error vs DEM (m)")]
    cols = [(c, t) for c, t in cols if c in stats_pts and stats_pts[c].notna().any()]
    fig, axes = plt.subplots(1, len(cols), figsize=(6.6, 1.9))
    for ax, (c, title) in zip(np.atleast_1d(axes), cols, strict=True):
        a = stats_pts[c].to_numpy(float)
        a = a[np.isfinite(a)]
        lo, hi = np.percentile(a, [0.5, 99.5])           # quality measures: 0.5-99.5 % shown
        if c == "vel_los_mm_yr":                          # velocity: the full range
            lo, hi = float(a.min()), float(a.max())
        ax.hist(np.clip(a, lo, hi), bins=60, range=(lo, hi), color=BLUE, edgecolor=SURFACE, linewidth=0.3)
        med = np.median(a)
        ax.axvline(med, color=INK, lw=0.8)
        ax.text(0.02, 1.0, f"median {med:.2f}", transform=ax.transAxes, ha="left", va="bottom", fontsize=6.5,
                color=INK2)
        ax.set_title(title, fontsize=7.5, pad=10)
        ax.set_yticks([])
        ax.grid(axis="y", visible=False)
        ax.spines["left"].set_visible(False)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def baselines(rows: list[dict], out: Path) -> Path:
    """Perpendicular baseline vs time; every interferogram pairs the reference with one acquisition."""
    plt = _plt()
    from datetime import date
    d = [date.fromisoformat(r["date"]) for r in rows]
    b = np.array([r.get("bperp_m") if r.get("bperp_m") is not None else np.nan for r in rows], float)
    ref = next((i for i, r in enumerate(rows) if r["reference"]), None)
    fig, ax = plt.subplots(figsize=(6.4, 2.3))
    if ref is not None:
        for i in range(len(rows)):
            if i != ref:
                ax.plot([d[ref], d[i]], [b[ref], b[i]], color=GRID, lw=0.8, zorder=1)
    used = np.array([r["used"] for r in rows])
    ax.scatter([x for x, u in zip(d, used, strict=True) if u], b[used], s=28, color=BLUE, edgecolors=SURFACE,
               linewidths=1, zorder=3, label="used")
    if (~used).any():
        ax.scatter([x for x, u in zip(d, used, strict=True) if not u], b[~used], s=28, facecolors=SURFACE,
                   edgecolors=GREY, linewidths=1.2, zorder=3, label="not used (noise test)")
    if ref is not None:
        ax.scatter([d[ref]], [b[ref]], marker="*", s=120, color=INK, zorder=4, label="reference")
    ax.set_ylabel(r"$B_\perp$ (m)")
    ax.legend(loc="upper left", ncol=3, fontsize=7, bbox_to_anchor=(0, 1.18))
    fig.autofmt_xdate()
    fig.savefig(out)
    plt.close(fig)
    return out


def noise(rows: list[dict], out: Path) -> Path | None:
    """Phase noise per interferogram; grey bars: left out of the inversion."""
    rows = [r for r in rows if not r["reference"] and r.get("noise") is not None]
    if not rows:
        return None
    plt = _plt()
    val = np.array([r["noise"] for r in rows], float)
    used = np.array([r["used"] for r in rows])
    fig, ax = plt.subplots(figsize=(6.4, 2.1))
    x = np.arange(len(rows))
    ax.bar(x[used], val[used], width=0.7, color=BLUE, label="used")
    if (~used).any():
        ax.bar(x[~used], val[~used], width=0.7, color=GREY, label="not used")
        ax.legend(fontsize=7, loc="upper left")
    ax.set_ylabel(rows[0].get("noise_unit", ""))
    ax.grid(axis="x", visible=False)
    ax.set_xticks(x, [r["date"][2:] for r in rows], rotation=60, ha="right", fontsize=6.5)
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)
    return out


def clusters(groups: list[dict], out: Path) -> Path | None:
    if not groups:
        return None
    plt = _plt()
    from datetime import date
    colour = {"fastest motion away from the satellite": RED, "fastest motion toward the satellite": BLUE,
              "stable points": INK2}
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    for g in groups:
        d = [date.fromisoformat(x) for x in g["dates"]]
        m, s = np.array(g["mean_mm"]), np.array(g["std_mm"])
        c = colour.get(g["label"], INK2)
        ax.fill_between(d, m - s, m + s, color=c, alpha=0.12, linewidth=0)
        ax.plot(d, m, color=c, lw=2, marker="o", ms=3, label=f"{g['label']} ({g['vel_mm_yr']:+.1f} mm/yr)")
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_ylabel("LOS displacement (mm)")
    ax.legend(fontsize=7, loc="best")
    fig.autofmt_xdate()
    fig.savefig(out)
    plt.close(fig)
    return out


def hotspot_series(h: dict, out: Path, unit: str = "vertical") -> Path:
    """Median series of a hot spot (band: interquartile range of its points) with the rate of each half of the
    period, the reading behind its trend."""
    plt = _plt()
    from datetime import date
    d = [date.fromisoformat(x) for x in h["dates"]]
    m = np.array(h["median_mm"], float)
    lo, hi = (np.array(x, float) for x in h["iqr_mm"])
    c = RED if h["kind"] == "sinking" else BLUE
    fig, ax = plt.subplots(figsize=(3.3, 1.75))
    tr = h.get("trend") or {}
    out_d = np.isin(h["dates"], tr.get("outliers", []))
    ax.fill_between(d, lo, hi, color=c, alpha=0.15, linewidth=0)
    ax.plot(d, m, color=c, lw=1.2, alpha=0.5)
    ax.plot([x for x, o in zip(d, out_d, strict=True) if not o], m[~out_d], ls="", color=c, marker="o", ms=2.6)
    if out_d.any():                                    # dates left out of the trend: hollow
        ax.plot([x for x, o in zip(d, out_d, strict=True) if o], m[out_d], ls="", marker="o", ms=3.2,
                mfc=SURFACE, mec=c, mew=1)
    if "rate_first_mm_yr" in tr:                       # the two half-period rates, through the median
        t = np.array([(x - d[0]).days for x in d], float) / 365.25
        mid = t[0] + (t[-1] - t[0]) / 2
        for sel, key in ((t <= mid, "rate_first_mm_yr"), (t >= mid, "rate_second_mm_yr")):
            ok = sel & np.isfinite(m) & ~out_d
            if ok.sum() >= 2:
                b = float(np.mean(m[ok] - tr[key] * t[ok]))
                ax.plot([d[i] for i in np.flatnonzero(ok)], b + tr[key] * t[ok], color=INK, lw=0.9, ls="--")
    ax.axhline(0, color=AXIS, lw=0.8)
    ax.set_ylabel(f"{'Vertical' if unit == 'vertical' else 'LOS'} motion (mm)", fontsize=7)
    ax.tick_params(labelsize=6.5)
    fig.autofmt_xdate()
    fig.savefig(out)
    plt.close(fig)
    return out


HAZARD_COLOURS = ["#d9ead3", "#f6dc7d", "#f2a65a", "#d9483b", "#7a1c1c"]


def hazard_map(cells, out: Path, *, cell_m: float, marks=()) -> Path:
    """Hazard level of every cell of the zoning (very low to very high), the hot spots labelled."""
    plt = _plt()
    from matplotlib.lines import Line2D

    from geoeyes.report.assess import LEVELS
    lon, lat, lv = cells["lon"].to_numpy(float), cells["lat"].to_numpy(float), cells["hazard"].to_numpy(int)
    lat0 = float(np.nanmean(lat))
    aspect = 1 / np.cos(np.radians(lat0))
    w, hgt = np.ptp(lon) / aspect, np.ptp(lat)
    fig, ax = plt.subplots(figsize=(6.3, min(max(6.3 * hgt / max(w, 1e-9), 2.6), 6.0)))
    # squares about one cell wide at the figure scale
    size = float(np.clip((cell_m / (max(w, 1e-9) * 111_320)) * 6.3 * 72, 0.3, 40)) ** 2
    if (lv < 0).any():
        ax.scatter(lon[lv < 0], lat[lv < 0], s=size, marker="s", color=GRID, linewidths=0, rasterized=True)
    for k in range(len(LEVELS)):
        sel = lv == k
        if sel.any():
            ax.scatter(lon[sel], lat[sel], s=size, marker="s", color=HAZARD_COLOURS[k], linewidths=0,
                       rasterized=True, zorder=2 + k)
    for x, y, text in marks:
        ax.annotate(text, (x, y), xytext=(6, 6), textcoords="offset points", fontsize=7.5, fontweight="bold",
                    color=INK, zorder=9, bbox={"boxstyle": "round,pad=0.2", "fc": SURFACE, "ec": INK, "lw": 0.6},
                    arrowprops={"arrowstyle": "-", "color": INK, "lw": 0.6})
    ax.set_aspect(aspect)
    ax.grid(False)
    ax.tick_params(labelsize=7)
    handles = [Line2D([], [], marker="s", ls="", ms=7, color=c, label=n) for n, c in zip(LEVELS, HAZARD_COLOURS,
                                                                                        strict=True)]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=7, title="Hazard level",
              title_fontsize=7.5, alignment="left")
    _scalebar(ax, lat0)
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out
