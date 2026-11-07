"""Space-time unwrapping of a fast, isolated cluster (VINSAR / HCMC Binh Chanh, 2026-11): with the legacy model
(fitted to the wrapped edge phase, IRLS on wrapped gradients) the cluster is a whole cycle off once its phase
difference to the background passes π; the edge rates + model cycle counts keep it right."""
import numpy as np

from geoeyes.processing.ps.unwrap.grid import grid_wrapped
from geoeyes.processing.ps.unwrap.interp import interp
from geoeyes.processing.ps.unwrap.space_time import edge_rates, space_time
from geoeyes.processing.ps.unwrap.spatial import SpatialParams, spatial_unwrap

LAM_MM = 55.465763


def _cluster_cycle_errors(rate_mm: float, cycles: bool) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(3)
    n_img, m = 41, 20
    day = (np.arange(n_img) - m) * 24.0                                   # ±480 days around the master
    bg = rng.uniform([0, 0], [500, 500], (1500, 2))
    cl = rng.uniform([650, 200], [700, 250], (60, 2))                    # 150 m gap: no PS in between
    xy = np.vstack([bg, cl])
    v = np.r_[np.zeros(len(bg)), np.full(len(cl), -30.0)]               # mm/yr LOS
    truth = -4 * np.pi / LAM_MM * v[:, None] * day[None, :] / 365.25
    ph = np.exp(1j * (truth + rng.normal(0, 0.3, truth.shape)))
    ph[:, m] = 1
    g = grid_wrapped(ph, np.column_stack([np.arange(len(xy)), xy]), grid_size=10.0, prefilt_win=16, gold_alpha=0.8,
                     coh=None, prefilter="gaussian")
    ui = interp(g.nzix)
    st = space_time(grid=g, ui=ui, day=day, ifgday_ix=np.column_stack([np.full(n_img, m), np.arange(n_img)]),
                    bperp=np.zeros(n_img), n_trial_wraps=0.1, time_win=730.0, prefilt_win=16, la_flag=False,
                    estimate_K=False, rate_max=4 * np.pi / LAM_MM * rate_mm / 365.25)
    uw = spatial_unwrap(grid=g, ui=ui, st=st, params=SpatialParams(n_jobs=1, model_cycles=cycles)).ph_uw
    icl = np.arange(len(bg), len(xy))
    rel = np.median(uw[icl], 0) - np.median(uw[:len(bg)], 0)
    err = (rel - (np.median(truth[icl], 0) - np.median(truth[:len(bg)], 0))) / (2 * np.pi)
    keep = np.arange(n_img) != m
    return np.abs(day[keep]), err[keep]


def test_legacy_space_time_loses_cycles_of_an_isolated_fast_cluster():
    adt, err = _cluster_cycle_errors(rate_mm=0.0, cycles=False)
    assert np.all(np.abs(err[adt < 150]) < 0.1)                         # below π: right
    assert np.mean(np.abs(err[adt > 300]) > 0.5) > 0.8                  # past π: a whole cycle off


def test_edge_rates_and_model_cycles_keep_the_cluster():
    adt, err = _cluster_cycle_errors(rate_mm=100.0, cycles=True)
    assert np.all(np.abs(err) < 0.1)


def test_edge_rates_finds_a_rate_and_leaves_noise_at_zero():
    rng = np.random.default_rng(0)
    dt = (np.arange(60) - 30) * 12.0
    true = 0.02                                                          # rad/day, ~32 mm/yr on S1
    d = np.vstack([np.exp(1j * (true * dt + rng.normal(0, 0.4, dt.size))),
                   np.exp(1j * rng.uniform(-np.pi, np.pi, dt.size)),    # pure noise
                   np.exp(1j * rng.normal(0, 0.4, dt.size))])           # no motion
    r = edge_rates(d, dt, rate_max=0.06)
    assert abs(r[0] - true) < 0.001 and r[1] == 0 and abs(r[2]) < 0.002
