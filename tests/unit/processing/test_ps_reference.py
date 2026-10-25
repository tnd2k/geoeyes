import numpy as np

from geoeyes.processing.ps.params import engine_params
from geoeyes.processing.ps.steps.reference import ReferenceParams, reference_ps


def grid_lonlat(n=21):
    lon, lat = np.meshgrid(np.linspace(105.80, 105.82, n), np.linspace(21.00, 21.02, n))
    return np.column_stack([lon.ravel(), lat.ravel()])


def test_box_and_radius():
    ll = grid_lonlat()
    box = reference_ps(ll, ReferenceParams(lon=(105.805, 105.807), lat=(21.005, 21.007)))
    assert box.size and np.all((ll[box, 0] > 105.805) & (ll[box, 0] < 105.807))
    circle = reference_ps(ll, ReferenceParams(centre_lonlat=(105.81, 21.01), radius=150.0))
    d = np.hypot((ll[circle, 0] - 105.81) * 111320 * np.cos(np.radians(21.01)), (ll[circle, 1] - 21.01) * 110574)
    assert 0 < circle.size < 20 and np.all(d < 160)
    assert reference_ps(ll, ReferenceParams(lon=(0, 1), lat=(0, 1))).size == ll.shape[0]     # empty -> all


def test_auto_takes_coherent_periphery():
    ll = grid_lonlat()
    coh = np.random.default_rng(0).uniform(0.3, 0.9, ll.shape[0])
    ref = reference_ps(ll, ReferenceParams(auto=True), coh=coh)
    centre = np.abs(ll - ll.mean(axis=0)).max(axis=1)
    assert np.min(centre[ref]) > 0.6 * centre.max()
    assert np.median(coh[ref]) > np.median(coh)


def test_params_default_is_scene_mean():
    assert engine_params({}, wavelength=0.03, rho=7e5).reference.is_default
    p = engine_params({"ref_auto": "y"}, wavelength=0.03, rho=7e5).reference
    assert p.auto and not p.is_default
