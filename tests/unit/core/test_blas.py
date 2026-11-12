"""BLAS thread limit (geoeyes.core.blas)."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from geoeyes.core.blas import _openblas, blas_threads


def test_limit_is_applied_and_restored():
    lib = _openblas()
    before = lib.openblas_get_num_threads() if lib is not None else None
    with blas_threads(1):
        if lib is not None:
            assert lib.openblas_get_num_threads() == 1
    if lib is not None:
        assert lib.openblas_get_num_threads() == before


def test_eigh_from_several_threads():
    # crashed (access violation) with OpenBLAS 0.3.34 pthreads on Windows without the limit
    def job(i):
        a = np.random.default_rng(i).normal(size=(256, 40, 6)) * (1 + 1j)
        c = a @ np.conj(np.swapaxes(a, 1, 2))
        return float(np.linalg.eigh(c)[0][:, -1].mean())

    with blas_threads(1), ThreadPoolExecutor(8) as pool:
        out = list(pool.map(job, range(16)))
    assert len(out) == 16 and all(np.isfinite(out))


def test_phase_linking_fits_the_free_memory():
    from geoeyes.processing.phase_linking.runner import PhaseLinkingParams, fit_memory
    p = PhaseLinkingParams(half_window=(3, 9))
    q, w = fit_memory(p, 103, 8, available=8.5e9)        # ql6_km124_141: 8 x 4096 needed ~22 GB
    assert 1 < w <= 8 and 128 <= q.batch < 4096                # padded tiles (~0.7 GB each) also count
    q, w = fit_memory(p, 103, 8, available=200e9)
    assert (q.batch, w) == (4096, 8)
    q, w = fit_memory(p, 103, 8, available=2e9)
    assert w < 8 and q.batch >= 128
