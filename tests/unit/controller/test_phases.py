import numpy as np
import pytest

from geoeyes.config.loader import load_dict
from geoeyes.controller.phases import phase_linking, ps
from geoeyes.core.errors import ConfigError, PhaseError
from geoeyes.io.stack import StackStore


def config(sensor="cosmo_skymed", **sections):
    return load_dict({"project": {"name": "t", "method": "psi"},
                      "tracks": [{"sensor": sensor, "direction": "ascending"}], **sections})


def test_csk_preset_links_phase_and_takes_ds():
    cfg = config()
    assert cfg.phase_linking.enabled and cfg.phase_linking.estimator == "adaptive"
    assert cfg.selection.ds_coherence_min == 0.7
    assert not config("sentinel1").phase_linking.enabled


def test_max_topo_err_auto_is_quarter_median_hoa():
    from geoeyes.processing.ps.params import hoa_max_topo_err
    assert config().ps["max_topo_err"] == "auto"
    bperp = [1010.2, 334.1, 1005.7, -101.8, 0.0, 527.4, 1299.7, -141.5, -462.0, 215.7, 286.0, 29.1, -508.6, 425.9,
             534.3, -584.2, -75.3, -549.2]                                         # CSK Hanoi, legacy value 2.7857
    geom = (0.0312284, 699862.3, np.radians(28.13977))                            # λ, median R, median θ
    assert hoa_max_topo_err(bperp, *geom) == pytest.approx(2.789, abs=0.005)
    assert hoa_max_topo_err(bperp, *geom, max_perp=800) == pytest.approx(3.441, abs=0.005)


def test_legacy_project_without_phase_linking_still_loads():
    cfg = config(phase_linking={"enabled": False})
    assert not cfg.phase_linking.enabled and cfg.selection.ds_coherence_min == 0.7      # DS ignored then


def small_stack(tmp_path):
    rng = np.random.default_rng(0)
    dates = np.array(["2020-01-01", "2020-01-13", "2020-01-25", "2020-02-06", "2020-02-18"], "datetime64[D]")
    st = StackStore.create(tmp_path / "stack.zarr", coords={"date": dates, "y": np.arange(20), "x": np.arange(24)},
                           attrs={"reference_date": "2020-01-25"})
    slc = rng.rayleigh(1.0, (5, 20, 24)) * np.exp(1j * rng.uniform(-np.pi, np.pi, (5, 20, 24)))
    st.write("slc", slc.astype(np.complex64), ("date", "y", "x"))
    return st


def test_phase_linking_phase_runs_once_per_parameters(tmp_path):
    st = small_stack(tmp_path)
    cfg = config(phase_linking={"half_window": [2, 2], "min_shp": 5, "tile_size": 16})
    assert not phase_linking.is_done(cfg, st)
    assert phase_linking.run(cfg, st)["linked"] > 0
    assert phase_linking.is_done(cfg, st) and st.has("pl_temporal_coherence")
    np.testing.assert_allclose(st.read("slc_linked", date=2), st.read("slc", date=2), atol=1e-6)  # reference kept
    assert phase_linking.run(cfg, st) is None                                               # up to date
    cfg2 = config(phase_linking={"half_window": [2, 2], "min_shp": 6, "tile_size": 16})
    assert not phase_linking.is_done(cfg2, st)
    assert phase_linking.run(cfg2, st) is not None
    assert phase_linking.run(config(sensor="sentinel1"), st) is None                        # disabled


def test_phase_linking_rejects_unported_estimator(tmp_path):
    with pytest.raises(ConfigError, match="psds"):
        phase_linking.run(config(phase_linking={"estimator": "psds"}), small_stack(tmp_path))


def test_ps_phase_reads_linked_slc_and_ds(tmp_path, monkeypatch):
    st = small_stack(tmp_path)
    import geoeyes.processing.ps.runner as ps_runner
    import geoeyes.processing.ps_lite.runner as lite_runner
    monkeypatch.setattr(ps_runner, "run", lambda *a, **k: k)
    monkeypatch.setattr(lite_runner, "run", lambda *a, **k: k)
    cfg = config(phase_linking={"half_window": [2, 2], "min_shp": 5, "tile_size": 16})
    with pytest.raises(PhaseError, match="phase linking"):
        ps.run(cfg, st, tmp_path / "run")
    phase_linking.run(cfg, st)
    k = ps.run(cfg, st, tmp_path / "run")
    assert k["slc_var"] == "slc_linked" and k["ds_tcoh_min"] == 0.7 and k["da_max"] == 0.4
    assert ps.run(cfg, st, tmp_path / "run", engine="ps_lite")["slc_var"] == "slc_linked"
    k = ps.run(config("sentinel1"), st, tmp_path / "run2")
    assert k["slc_var"] == "slc" and k["ds_tcoh_min"] is None
