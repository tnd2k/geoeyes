"""SBAS core (geoeyes.processing.sbas): the network keeps the short pairs and stays connected, the inversion recovers
a known displacement exactly, minimum norm across a gap, closure finds an injected unwrapping error."""
from datetime import date, timedelta

import numpy as np

from geoeyes.processing.sbas import closure as cl
from geoeyes.processing.sbas import invert as iv
from geoeyes.processing.sbas.network import NetworkParams, components, select_pairs


def _dates(n=12, step=12):
    return [date(2021, 1, 1) + timedelta(days=step * k) for k in range(n)]


def test_network_limits_and_connectivity():
    d = _dates()
    b = np.zeros(len(d))
    b[6] = 400.0                                      # one date far in baseline: only the bridge reaches it
    net = select_pairs(d, b, NetworkParams(max_perp_m=150, n_nearest=2, redundant=True, redundant_max_days=24))
    assert all(abs(b[i] - b[j]) <= 150 or (i, j) in net.bridged for i, j in net.pairs)
    assert net.components_before_bridge == 2 and len(components(len(d), net.pairs)) == 1
    assert (0, 1) in net.pairs and (0, 2) in net.pairs        # nearest and redundant (24 days)
    s = net.summary()
    assert s["pairs"] == len(net.pairs) and s["days"]["min"] == 12


def test_inversion_recovers_a_known_series_and_flags_noise():
    d = _dates(10)
    net = select_pairs(d, np.zeros(10), NetworkParams(n_nearest=3, redundant=False))
    t = net.days()
    rng = np.random.default_rng(0)
    truth = np.column_stack([0.01 * t, -0.02 * t + 0.5 * np.sin(t / 30)])       # 2 pixels, phase per date
    phase = np.array([truth[j] - truth[i] for i, j in net.pairs])
    phase = np.column_stack([phase, rng.uniform(-np.pi, np.pi, len(net.pairs))])  # a 3rd pixel of pure noise
    vel, model = iv.invert(phase, net.design())
    series = iv.displacement(vel, t)
    assert np.allclose(series[:, :2], truth - truth[0], atol=1e-9)
    tc = iv.temporal_coherence(phase, model)
    assert tc[0] > 0.999 and tc[1] > 0.999 and tc[2] < 0.8
    v, _ = iv.linear_velocity(series[:, :1], t)
    assert np.isclose(v[0], 0.01)


def test_missing_pairs_and_a_gap_use_the_minimum_norm():
    d = _dates(6)
    pairs = [(0, 1), (1, 2), (3, 4), (4, 5)]              # two subsets, no pair across 2–3
    from geoeyes.processing.sbas.network import Network
    net = Network(d, pairs)
    t = net.days()
    truth = 0.01 * t
    phase = np.array([[truth[j] - truth[i]] for i, j in pairs])
    vel, model = iv.invert(phase, net.design(), min_pairs=2)
    assert np.allclose(model, phase) and np.isfinite(vel).all()
    assert abs(vel[2, 0]) < 1e-12                          # the unobserved interval: minimum norm gives 0
    phase2 = phase.copy()
    phase2[1, 0] = np.nan                                  # one pair missing on this pixel
    vel2, _ = iv.invert(phase2, net.design(), min_pairs=4)
    assert np.isnan(vel2).all()                            # fewer than min_pairs


def _stack(tmp_path, n_dates=8, n=96, lam=0.0555, max_mm=30.0, noise=0.25):
    """A flattened stack (GeoEyes convention: a range increase d gives slc ∝ exp(−4πd/λ)) with a bowl subsiding
    linearly to ``max_mm`` at the last date."""
    from geoeyes.io.stack import StackStore
    rng = np.random.default_rng(1)
    dates = np.array([np.datetime64("2021-01-01") + np.timedelta64(12 * k, "D") for k in range(n_dates)],
                     "datetime64[ns]")
    y, x = np.mgrid[0:n, 0:n].astype(float)
    bowl = np.exp(-((y - n / 2) ** 2 + (x - n / 2) ** 2) / (2 * (n / 6) ** 2))
    psi = rng.uniform(-np.pi, np.pi, (n, n))
    amp = rng.rayleigh(1.0, (n, n)) + 0.5
    frac = np.linspace(0, 1, n_dates)
    slc = np.stack([amp * np.exp(1j * (psi - 4 * np.pi * (max_mm / 1000 * f * bowl) / lam
                                       + rng.normal(0, noise, (n, n)))) for f in frac]).astype(np.complex64)
    s = StackStore.create(tmp_path / "stack.zarr", coords={"date": dates, "y": np.arange(n), "x": np.arange(n)},
                          attrs={"reference_date": "2021-01-01", "wavelength_m": lam, "sensor": "test",
                                 "track": "test-desc", "heading_deg": 190.0, "look_side": "right",
                                 "stack_id": "test-desc"})
    s.write("slc", slc, ("date", "y", "x"))
    s.write("bperp", np.zeros(n_dates), ("date",))
    for k, v in {"hgt": np.zeros((n, n)), "incidence": np.full((n, n), 35.0), "lat": 15 + y * 1e-4,
                 "lon": 108 + x * 1e-4}.items():
        s.write(f"geometry_{k}", v.astype(np.float32), ("y", "x"))
    return s, bowl


def test_sbas_run_recovers_a_subsiding_bowl(tmp_path):
    import pandas as pd

    from geoeyes.config.schema import NetworkSection, SbasSection
    from geoeyes.io.points import read_points
    from geoeyes.processing.sbas.runner import run
    store, bowl = _stack(tmp_path)
    out = tmp_path / "run"
    smy = run(store, out, SbasSection(looks_az=2, looks_rg=2, goldstein_alpha=0.3, reference=(108.0005, 15.0005)),
              NetworkSection(max_temporal_days=36), track_id="test-desc")      # reference: the stable corner
    assert smy["sbas"]["points"] > 1000 and smy["sbas"]["pairs_used"] == smy["sbas"]["pairs"]
    pts = read_points(out / "points.parquet")
    ts = pd.read_parquet(out / "timeseries.parquet")
    last = ts[ts.date == ts.date.max()].set_index("point_uid").disp_mm
    line, sample = pts["line"], pts["sample"]
    centre = pts[(line - 48).abs().le(3) & (sample - 48).abs().le(3)]
    edge = pts[(line < 10) | (sample < 10)]
    # subsidence: away from the satellite, negative; −30 mm at the centre, ~0 near the edges (reference)
    assert abs(last.reindex(centre.point_uid).median() + 30) < 1.5
    assert abs(last.reindex(edge.point_uid).median()) < 1.0
    assert abs(centre.vel_los_mm_yr.median() + 30 / 84 * 365.25) < 8      # −130 mm/yr
    assert (out / "network.json").exists() and (out / "manifest.json").exists()
    # the product builder reads an SBAS run as it reads the point engines
    from geoeyes.products.builder import build_product
    res = build_product(out, tmp_path / "products", project="t", track_id="test-desc")
    assert res


def test_method_sbas_selects_the_sbas_engine():
    from geoeyes.config.loader import load_dict
    from geoeyes.controller.phases.ps import engine_of
    cfg = load_dict({"project": {"name": "t", "method": "sbas"},
                     "tracks": [{"sensor": "sentinel1", "direction": "descending"}],
                     "sbas": {"looks_az": 3}, "network": {"sbas": {"redundant_max_days": 36}}})
    assert engine_of(cfg) == "sbas" and cfg.sbas.looks_az == 3 and cfg.network.sbas.redundant_max_days == 36
    from geoeyes.processing.sbas.runner import network_params
    p = network_params(cfg.network, cfg.sbas)
    assert p.redundant_max_days == 36 and p.max_perp_m == cfg.network.max_perp_m


def test_pixel_mask_and_stratified_troposphere():
    d = _dates(8)
    net = select_pairs(d, np.zeros(8), NetworkParams(n_nearest=3, redundant=False))
    t = net.days()
    truth = np.outer(0.02 * t, np.ones(50))
    phase = np.array([truth[j] - truth[i] for i, j in net.pairs])
    wrong = net.pairs.index((2, 4))
    phase[wrong, :5] += 2 * np.pi                          # a local unwrapping error on 5 pixels
    masked, n = cl.mask_bad_cells(phase, net.pairs)
    assert np.isnan(masked[wrong, :5]).all() and np.isfinite(masked[wrong, 5:]).all()
    assert np.isfinite(np.delete(masked, wrong, axis=0)).all() and n == 5
    h = np.linspace(200, 1800, 500)
    ph = np.vstack([0.3 + 0.002 * h, -0.001 * h + np.sin(h / 50) * 0.01])
    corr, b = iv.remove_stratified(ph, h, np.ones(500, bool))
    assert np.allclose(b, [0.002, -0.001], atol=2e-5) and np.ptp(corr[0]) < 1e-6


def test_unwrap_ties_islands_across_a_gap():
    from geoeyes.processing.sbas import pairs as pr
    from geoeyes.processing.unwrap.components import link_components
    y, x = np.mgrid[0:80, 0:120].astype(float)
    truth = 0.08 * x + 0.02 * y                            # slow, smooth motion: 0.8 rad across the gap
    ifg = np.exp(1j * truth)
    coh = np.ones_like(truth, np.float32)
    coh[:, 55:65] = 0.0                                    # a band without coherence splits the scene in two
    u = pr.unwrap(ifg, coh, 0.2, 0.0, 32, 50, link_islands=True)
    d = u - truth
    assert np.isnan(u[:, 58]).all()
    assert abs(np.nanmedian(d[:, :50]) - np.nanmedian(d[:, 70:])) < 0.5      # one surface across the gap
    broken = u.copy()
    broken[:, 65:] += 2 * np.pi                            # an island one cycle off, as a split IRLS surface gives
    fixed = link_components(broken)
    df = fixed - truth
    assert abs(np.nanmedian(df[:, :50]) - np.nanmedian(df[:, 70:])) < 0.5


def test_closure_finds_the_wrong_pair():
    d = _dates(8)
    net = select_pairs(d, np.zeros(8), NetworkParams(n_nearest=3, redundant=False))
    t = net.days()
    truth = np.outer(0.02 * t, np.ones(50))
    phase = np.array([truth[j] - truth[i] for i, j in net.pairs])
    wrong = net.pairs.index((2, 4))
    phase[wrong, :30] += 2 * np.pi                         # an unwrapping error on 60 % of the pixels
    drop, info = cl.bad_pairs(phase, net.pairs)
    assert drop == [wrong] and info["triplets"] > 0
