"""geoeyes.core.compute (ADR-014): backend choice, and the GPU code path of the kernels that have one.

Without a GPU the GPU path is exercised with a stand-in backend: NumPy behind the CuPy-style interface (no
``workers`` for the FFT, explicit host/device copies, GPU batch sizes). With CuPy and a device, the real GPU
results are compared with the CPU ones.
"""
from __future__ import annotations

import types

import numpy as np
import pytest
import scipy.fft

from geoeyes.core import compute
from geoeyes.core.errors import ConfigError
from geoeyes.processing.ps.clap import clap_at_points, low_pass
from geoeyes.processing.ps.topofit import topofit, topofit_full


def _has_gpu() -> bool:
    try:
        return compute._cupy_backend() is not None
    except Exception:
        return False


GPU = _has_gpu()


class _FakeXp(types.ModuleType):
    """NumPy with the CuPy extras the backend uses."""

    def __init__(self):
        super().__init__("fake_cupy")
        self.freed = 0

    def __getattr__(self, name):
        return getattr(np, name)

    def asarray(self, a, dtype=None):
        return np.array(a, dtype, copy=True)          # a real copy, as host -> device

    def asnumpy(self, a):
        return np.array(a, copy=True)

    def get_default_memory_pool(self):
        outer = self

        class Pool:
            def free_all_blocks(self):
                outer.freed += 1
        return Pool()


def _fake_gpu(rows: int = 512) -> compute.Backend:
    return compute.Backend("fake", _FakeXp(), scipy.fft, {}, "fake #0", 4.0, rows)


def _data(n=900, k=12, seed=3):
    rng = np.random.default_rng(seed)
    z = np.exp(1j * rng.uniform(-np.pi, np.pi, (n, k))) * (rng.random((n, k)) > 0.05)
    return z, rng.normal(0, 120, (n, k))


def _grid(seed=4, k=10):
    rng = np.random.default_rng(seed)
    g = (rng.normal(size=(80, 70, k)) + 1j * rng.normal(size=(80, 70, k))).astype(np.complex64)
    g[rng.random((80, 70)) > 0.35] = 0
    cells = np.column_stack([rng.integers(0, 80, 400), rng.integers(0, 70, 400)])
    return g, cells


def test_resolve_numpy_and_errors(monkeypatch):
    monkeypatch.delenv(compute.ENV, raising=False)
    assert compute.resolve("numpy") is compute.NUMPY
    assert not compute.NUMPY.gpu and compute.NUMPY.fft_kw == {"workers": -1}
    with pytest.raises(ConfigError):
        compute.resolve("opencl")


def test_auto_falls_back_and_cupy_fails_loudly(monkeypatch):
    monkeypatch.delenv(compute.ENV, raising=False)

    def broken():
        raise ImportError("No module named 'cupy'")
    monkeypatch.setattr(compute, "_cupy_backend", broken)
    assert compute.resolve("auto") is compute.NUMPY
    with pytest.raises(ConfigError, match="GPU is not usable"):
        compute.resolve("cupy")
    assert compute.info("cupy")["ok"] is False
    assert compute.info("auto")["backend"] == "numpy"


def test_env_overrides_config(monkeypatch):
    monkeypatch.setenv(compute.ENV, "numpy")
    monkeypatch.setattr(compute, "_cupy_backend", lambda: _fake_gpu())
    assert compute.resolve("cupy") is compute.NUMPY


def test_use_sets_and_restores():
    be = _fake_gpu()
    assert compute.current() is compute.NUMPY
    with compute.use(be):
        assert compute.current() is be
    assert compute.current() is compute.NUMPY
    assert be.xp.freed == 1                            # device memory handed back at the end of the run


def test_batch_sizes():
    assert compute.NUMPY.batch(200) == 200
    assert _fake_gpu(4096).batch(200) == 4096


@pytest.mark.parametrize("fit", [topofit, topofit_full])
def test_topofit_gpu_path_matches_cpu(fit):
    z, bp = _data()
    cpu = fit(z, bp, 1.3)
    with compute.use(_fake_gpu(rows=256)):             # other batch boundaries than the CPU's 200
        gpu = fit(z, bp, 1.3)
    for a in ("K", "C", "coh", "Q", "residual"):
        np.testing.assert_allclose(getattr(gpu, a), getattr(cpu, a), rtol=1e-12, atol=1e-12, err_msg=a)


def test_clap_at_points_gpu_path_matches_cpu():
    g, cells = _grid()
    lp = low_pass(32, 50, 800)
    cpu = clap_at_points(g, cells, 32, 1.0, 0.3, lp, osf_r=1, batch=64)
    with compute.use(_fake_gpu()):
        gpu = clap_at_points(g, cells, 32, 1.0, 0.3, lp, osf_r=1, batch=64)
    np.testing.assert_allclose(gpu, cpu, rtol=1e-5, atol=1e-6)


@pytest.mark.skipif(not GPU, reason="no CuPy / GPU on this machine")
def test_real_gpu_matches_cpu():
    z, bp = _data(n=5000)
    g, cells = _grid()
    lp = low_pass(32, 50, 800)
    cpu_t, cpu_c = topofit(z, bp, 1.3), clap_at_points(g, cells, 32, 1.0, 0.3, lp)
    with compute.use("cupy"):
        gpu_t, gpu_c = topofit(z, bp, 1.3), clap_at_points(g, cells, 32, 1.0, 0.3, lp)
    # the ambiguity search picks the same trial; the refined values agree to rounding
    assert np.mean(np.isclose(gpu_t.K, cpu_t.K, rtol=1e-9, atol=1e-12)) > 0.999
    np.testing.assert_allclose(gpu_t.coh, cpu_t.coh, atol=1e-9)
    np.testing.assert_allclose(gpu_c, cpu_c, rtol=1e-4, atol=1e-5)
