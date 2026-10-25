"""Write the CR identification report: metrics (JSON/CSV), figures (PNG) and a PDF (Typst)."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np

from geoeyes.validation.corner_reflector import trihedral
from geoeyes.validation.corner_reflector.pipeline import TOLERANCE_DB, Observation

TEMPLATE = Path(__file__).with_name("cr_report.typ")
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e1e0d9"


# ── data files ───────────────────────────────────────────────────────────────

def write_data(result: dict, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    obs_rows = [{k: v for k, v in asdict(o).items() if k != "chip"} for o in result["observations"]]
    data = {k: v for k, v in result.items() if k != "observations"}
    data["observations"] = obs_rows
    (out / "cr_report.json").write_text(json.dumps(_finite(data), ensure_ascii=False, indent=2, default=float),
                                        encoding="utf-8")
    _csv(out / "observations.csv", obs_rows)
    _csv(out / "coherence.csv", result["coherence"])
    _csv(out / "pointing.csv", result["pointing"])
    return data


def _finite(x):
    """JSON has no NaN/Infinity (browsers and Typst reject them): write null instead."""
    if isinstance(x, dict):
        return {k: _finite(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_finite(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def _ok(v) -> bool:
    return v is not None and bool(np.isfinite(v))


def _csv(path: Path, rows: list[dict]):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


# ── figures ──────────────────────────────────────────────────────────────────

def _mpl():
    from geoeyes.report.figures import _plt
    return _plt()


def chips_figure(obs: list[Observation], path: Path, half=(6, 22)) -> Path:
    """Beta0 around the reflector for every date, on one grey scale, in metres from the GPS position."""
    plt = _mpl()
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    n = len(obs)
    cols = min(n, 4)
    rows = int(np.ceil(n / cols))
    fig, axs = plt.subplots(rows, cols, figsize=(3.0 * cols + 0.8, 3.0 * rows + 0.7), squeeze=False,
                            constrained_layout=True)
    crops, vals = [], []
    for o in obs:
        c = o.chip
        pl, ps = c["pred"]
        i0, j0 = int(round(pl)) - c["line0"], int(round(ps)) - c["sample0"]
        crop = c["beta0"][max(i0 - half[0], 0):i0 + half[0] + 1, max(j0 - half[1], 0):j0 + half[1] + 1]
        crops.append((crop, max(i0 - half[0], 0) + c["line0"], max(j0 - half[1], 0) + c["sample0"]))
        vals.append(10 * np.log10(np.maximum(crop, 1e-6)))
    allv = np.concatenate([v.ravel() for v in vals])
    vmin, vmax = float(np.percentile(allv, 20)), float(allv.max())
    im = None
    for k, (o, (crop, l0, s0), v) in enumerate(zip(obs, crops, vals, strict=True)):
        a = axs[k // cols][k % cols]
        c = o.chip
        gr = c["range_spacing"] / np.sin(np.radians(c["incidence_deg"]))
        az = c["azimuth_spacing"]
        pl, ps = c["pred"]
        x0, x1 = (s0 - 0.5 - ps) * gr, (s0 + crop.shape[1] - 0.5 - ps) * gr
        y0, y1 = (l0 - 0.5 - pl) * az, (l0 + crop.shape[0] - 0.5 - pl) * az
        im = a.imshow(v, cmap="gray", vmin=vmin, vmax=vmax, extent=[x0, x1, y1, y0], aspect="equal",
                      interpolation="nearest")
        qx, qy = (c["peak"][1] - ps) * gr, (c["peak"][0] - pl) * az
        a.add_patch(Rectangle((qx - 2.5 * gr, qy - 1.5 * az), 5 * gr, 3 * az, fill=False, ec=ORANGE, lw=1.2))
        a.plot(0, 0, "o", mfc="none", mec=BLUE, ms=9, mew=1.8)
        a.plot(qx, qy, "+", color=ORANGE, ms=10, mew=2)
        a.set_title(f"{o.date} · {o.measured_dbsm:.1f} dBsm", fontsize=8.5)
        a.set_xlabel("Range, away from the satellite (m)", fontsize=7.5)
        a.set_ylabel("Azimuth (m)", fontsize=7.5)
        a.grid(False)
    for k in range(n, rows * cols):
        axs[k // cols][k % cols].axis("off")
    cb = fig.colorbar(im, ax=axs, shrink=0.8, pad=0.01)
    cb.set_label("β⁰ (dB), same scale for every date", fontsize=7.5)
    fig.legend(handles=[Line2D([], [], marker="o", ls="", mfc="none", mec=BLUE, ms=8, mew=1.8,
                               label="GPS position of the CR"),
                        Line2D([], [], marker="+", ls="", color=ORANGE, ms=9, mew=2, label="Measured peak"),
                        Rectangle((0, 0), 1, 1, fill=False, ec=ORANGE, lw=1.2,
                                  label="RCS integration cell (3 × 5 pixels)")],
               loc="outside lower center", ncol=3, frameon=False, fontsize=7.5)
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path


def rcs_figure(obs: list[Observation], edge_m: float, wavelength: float, path: Path) -> Path:
    plt = _mpl()
    from matplotlib.lines import Line2D
    from matplotlib.patches import Rectangle
    xs = np.arange(len(obs))
    fig, ax = plt.subplots(figsize=(max(5.5, 1.5 * len(obs) + 2), 3.4), constrained_layout=True)
    peak = trihedral.peak_rcs_dbsm(edge_m, wavelength)
    ax.axhline(peak, color="#c3c2b7", lw=1, ls=(0, (4, 3)))
    ax.text(-0.45, peak + 0.15, f"On boresight: {peak:.1f} dBsm", fontsize=7, color=MUTED, va="bottom")
    vals = [v for o in obs for v in (o.measured_dbsm, o.expected_dbsm) if _ok(v)]
    lo = min([*vals, peak]) - TOLERANCE_DB - 1
    hi = max([*vals, peak]) + 2
    for x, o in zip(xs, obs, strict=True):
        if _ok(o.expected_dbsm):
            ax.add_patch(Rectangle((x - 0.18, o.expected_dbsm - TOLERANCE_DB), 0.36, 2 * TOLERANCE_DB,
                                   color="#ec835a", alpha=0.16, lw=0))
            ax.plot(x, o.expected_dbsm, "D", ms=7, mfc="white", mec=ORANGE, mew=1.8)
            ax.text(x + 0.22, o.expected_dbsm, f"{o.expected_dbsm:.1f}", va="center", fontsize=7, color=ORANGE)
        else:                                   # the satellite looks at the back of the reflector
            ax.text(x, lo + 0.6, "CR faces\naway", ha="center", va="bottom", fontsize=7, color=ORANGE)
        if _ok(o.measured_dbsm):
            ax.plot(x, o.measured_dbsm, "o", ms=8, color=BLUE, mec="white", mew=1.5, zorder=5)
            ax.text(x + 0.22, o.measured_dbsm, f"{o.measured_dbsm:.1f}", va="center", fontsize=8)
        else:                                   # energy in the cell below the clutter level
            ax.text(x, hi - 1.2, "below\nclutter", ha="center", va="top", fontsize=7, color=BLUE)
    ax.set_ylim(np.floor(lo), np.ceil(hi))
    ax.set_xlim(-0.6, len(obs) - 0.2)
    ax.set_xticks(xs, [o.date for o in obs])
    ax.set_ylabel("RCS (dBsm)")
    ax.grid(axis="x", visible=False)
    ax.legend(handles=[Line2D([], [], marker="o", ls="", color=BLUE, ms=7, label="Measured RCS"),
                       Line2D([], [], marker="D", ls="", mfc="white", mec=ORANGE, mew=1.8, ms=6,
                              label="Expected RCS for the set-up"),
                       Rectangle((0, 0), 1, 1, color="#ec835a", alpha=0.25, label=f"Expected ± {TOLERANCE_DB:g} dB")],
              loc="upper left", fontsize=7, ncol=3)
    fig.savefig(path, dpi=170)
    plt.close(fig)
    return path


# ── PDF ──────────────────────────────────────────────────────────────────────

def _summary(result: dict) -> list[str]:
    out = []
    obs: list[Observation] = result["observations"]
    for r in result["reflectors"]:
        n = r["name"]
        oo = [o for o in obs if o.reflector == n]
        if not oo:
            out.append(f"{n}: no acquisition images this position.")
            continue
        ok = sum(o.within_tolerance for o in oo)
        txt = (f"{n}: {len(oo)} acquisition(s). The measured RCS is within ±{TOLERANCE_DB:g} dB of the expected value "
               f"in {ok}/{len(oo)}. The measured peak is {min(o.offset_m for o in oo):.1f}–"
               f"{max(o.offset_m for o in oo):.1f} m from the GPS position.")
        coh = [c["at_reflector"] for c in result["coherence"] if c["reflector"] == n]
        if coh:
            txt += f" Coherence at the reflector between acquisitions: {min(coh):.2f}–{max(coh):.2f}."
        behind = [o for o in oo if not _ok(o.expected_dbsm)]
        if behind:
            txt += (f" {len(behind)} acquisition(s) see the back of the reflector according to the set-up log "
                    "(usually the other pass direction): no expected RCS to compare with.")
        if any(o.setup_source == "assumed" for o in oo):
            txt += (" Some acquisitions have no set-up log entry: their expected RCS assumes the reflector points as "
                    "required.")
        strong = [o for o in oo if o.nearby_dbsm > o.measured_dbsm + 1 and o.nearby_offset_m > o.offset_m + 5]
        if strong:
            txt += (" A stronger scatterer lies near the reflector (" + "; ".join(
                f"{o.date}: {o.nearby_dbsm:.1f} dBsm, {o.nearby_offset_m:.0f} m from the GPS position" for o in strong)
                    + "); the reflector RCS is measured within one resolution cell of the predicted position, so it "
                      "is not mixed in.")
        out.append(txt)
    return out


def write_report(result: dict, out: Path, project: str, pdf: bool = True) -> dict:
    """Write JSON/CSV, figures and (optionally) the PDF into ``out``. Returns the written paths."""
    out = Path(out)
    data = write_data(result, out)
    paths = {"dir": str(out), "json": str(out / "cr_report.json")}
    figures = {}
    for r in result["reflectors"]:
        oo = [o for o in result["observations"] if o.reflector == r["name"]]
        if not oo:
            continue
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in r["name"])
        figures[r["name"]] = {
            "chips": chips_figure(oo, out / f"{safe}_chips.png").name,
            "rcs": rcs_figure(oo, r["edge_m"], oo[0].wavelength_m, out / f"{safe}_rcs.png").name}
    if pdf:
        import typst
        with tempfile.TemporaryDirectory(prefix="geoeyes_cr_") as tmp:
            tmp = Path(tmp)
            for f in figures.values():
                for name in f.values():
                    shutil.copy(out / name, tmp / name)
            doc = {**_finite(data), "project": project, "summary": _summary(result), "figures": figures}
            (tmp / "cr_report.json").write_text(json.dumps(doc, ensure_ascii=False, default=float), encoding="utf-8")
            shutil.copy(TEMPLATE, tmp / "cr_report.typ")
            typst.compile(str(tmp / "cr_report.typ"), output=str(out / "cr_report.pdf"), root=str(tmp))
        paths["pdf"] = str(out / "cr_report.pdf")
    return paths
