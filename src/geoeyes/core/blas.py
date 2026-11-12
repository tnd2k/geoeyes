"""Thread count of the BLAS / LAPACK under numpy, for code that calls numpy.linalg from several Python threads.

OpenBLAS (conda-forge 0.3.34 pthreads, Windows) crashes with an access violation when several Python threads call
``matmul`` / ``eigh`` at the same time while it runs its own thread pool (8 workers x 16 BLAS threads: phase linking
on ql6_km124_141, 2026-11-11; reproduced with random matrices). One BLAS thread per Python worker avoids it and
costs nothing there: the parallelism is the workers'. ``threadpoolctl`` does not see the conda-forge OpenBLAS
behind ``libblas.dll``, so OpenBLAS is also driven directly through ``openblas_set_num_threads``.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from contextlib import ExitStack, contextmanager
from functools import lru_cache


@lru_cache(maxsize=1)
def _openblas():
    """The loaded OpenBLAS library with its thread functions, or None."""
    names = [os.path.join(sys.prefix, "Library", "bin", "openblas.dll")] if os.name == "nt" else []
    names += [n for n in (ctypes.util.find_library("openblas"),) if n]
    for name in names:
        try:
            lib = ctypes.CDLL(name)
            lib.openblas_get_num_threads.restype = ctypes.c_int
            lib.openblas_set_num_threads.argtypes = [ctypes.c_int]
            return lib
        except (OSError, AttributeError):
            continue
    return None


@contextmanager
def blas_threads(n: int = 1):
    """Limit the BLAS / LAPACK threads to ``n`` inside the block (threadpoolctl and OpenBLAS directly)."""
    with ExitStack() as stack:
        try:
            from threadpoolctl import threadpool_limits
            stack.enter_context(threadpool_limits(n))
        except ImportError:
            pass
        lib = _openblas()
        before = lib.openblas_get_num_threads() if lib is not None else None
        if lib is not None:
            lib.openblas_set_num_threads(n)
        try:
            yield
        finally:
            if lib is not None and before:
                lib.openblas_set_num_threads(before)
