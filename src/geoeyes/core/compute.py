"""Array backend: NumPy on the CPU, CuPy on an NVIDIA (CUDA) or AMD (ROCm) GPU (ADR-014).

A kernel that has a GPU path asks for the backend of the current run and writes its arithmetic with ``be.xp``
(``numpy`` or ``cupy``) and ``be.fft`` (``scipy.fft`` or ``cupyx.scipy.fft``)::

    be = compute.current()
    z = be.asarray(cpx[s:e])                 # host -> device (no copy on the CPU)
    ...  xp = be.xp; xp.einsum(...); be.fft.fft2(x, **be.fft_kw) ...
    out[s:e] = be.asnumpy(k0)                # device -> host (no copy on the CPU)

On the CPU backend ``xp`` *is* ``numpy``, ``asarray``/``asnumpy`` return their argument and ``fft_kw`` keeps
``workers=-1``, so the CPU path runs the same operations as before the GPU path existed (bit-identical results).
GPU results agree to floating-point rounding, not bit for bit (other FFT and reduction orders).

The backend is chosen once per run (``[compute] backend`` in project.toml; the environment variable
``GEOEYES_COMPUTE_BACKEND`` overrides it):

- ``auto``: CuPy when it imports, sees a device and runs a small test kernel; NumPy otherwise (logged once);
- ``numpy``: always the CPU;
- ``cupy``: the GPU or an error (no silent fallback when the GPU was asked for).
"""
from __future__ import annotations

import contextlib
import contextvars
import logging
import os
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import numpy as np

from geoeyes.core.errors import ConfigError

log = logging.getLogger(__name__)

ENV = "GEOEYES_COMPUTE_BACKEND"
BACKENDS = ("auto", "numpy", "cupy")


@dataclass(frozen=True)
class Backend:
    name: str                          # "numpy" | "cupy"
    xp: ModuleType                     # numpy | cupy
    fft: ModuleType                    # scipy.fft | cupyx.scipy.fft
    fft_kw: dict = field(default_factory=dict)     # {"workers": -1} on the CPU
    device: str = "cpu"
    memory_gb: float = 0.0             # device memory (0 on the CPU)
    batch_rows: int = 0                # rows per batch for the kernels that batch (0 = the kernel's own default)

    @property
    def gpu(self) -> bool:
        return self.name != "numpy"

    def asarray(self, a, dtype=None):
        """Host array -> backend array (the same object on the CPU when the dtype already matches)."""
        return np.asarray(a, dtype) if not self.gpu else self.xp.asarray(a, dtype)

    def asnumpy(self, a) -> np.ndarray:
        """Backend array -> NumPy array (the same object on the CPU)."""
        return a if not self.gpu else self.xp.asnumpy(a)

    def batch(self, default: int) -> int:
        """Rows per batch: the kernel's CPU ``default``, or the larger GPU batch (fewer kernel launches)."""
        return max(default, self.batch_rows) if self.gpu else default

    def free_memory(self) -> None:
        """Return the cached device memory to the driver (after a large kernel)."""
        if self.gpu:
            self.xp.get_default_memory_pool().free_all_blocks()

    def describe(self) -> str:
        return "numpy (CPU)" if not self.gpu else f"cupy on {self.device} ({self.memory_gb:.1f} GB)"


def _numpy_backend() -> Backend:
    import scipy.fft
    return Backend("numpy", np, scipy.fft, {"workers": -1})


NUMPY = _numpy_backend()


def _cupy_backend() -> Backend:
    """The CuPy backend, or an exception saying why it is unavailable."""
    import cupy
    import cupyx.scipy.fft as cfft
    n = cupy.cuda.runtime.getDeviceCount()
    if n < 1:
        raise RuntimeError("no GPU device")
    dev = cupy.cuda.Device()
    props = cupy.cuda.runtime.getDeviceProperties(dev.id)
    name = props.get("name", b"GPU")
    name = name.decode(errors="replace") if isinstance(name, bytes) else str(name)
    total = float(dev.mem_info[1]) / 1e9
    # a small kernel with an FFT: a broken driver or CUDA/ROCm mismatch fails here, not in the middle of a run
    x = cupy.exp(1j * cupy.arange(64, dtype=cupy.float64)).reshape(8, 8)
    float(cupy.abs(cfft.fft2(x)).sum())
    # rows per batch: the topofit temporaries are ~ rows x n_ifg x n_trials x 16 B; 1/8 of the memory is safe
    rows = int(min(262_144, max(8_192, total * 1e9 / 8 / (64 * 64 * 16))))
    return Backend("cupy", cupy, cfft, {}, f"{name} #{dev.id}", total, rows)


def resolve(backend: str | None = "auto") -> Backend:
    """The backend for ``backend`` (``auto`` | ``numpy`` | ``cupy``); ``GEOEYES_COMPUTE_BACKEND`` wins."""
    want = (os.environ.get(ENV) or backend or "auto").strip().lower()
    if want not in BACKENDS:
        raise ConfigError(f"compute backend {want!r}: one of {', '.join(BACKENDS)}")
    if want == "numpy":
        return NUMPY
    try:
        return _cupy_backend()
    except Exception as exc:                          # ImportError, CUDA/ROCm runtime errors, no device
        if want == "cupy":
            raise ConfigError(f"[compute] backend = \"cupy\" but the GPU is not usable: {type(exc).__name__}: "
                              f"{exc}. Install CuPy for the CUDA/ROCm version of the machine (pip install "
                              "\"geoeyes[gpu]\" = cupy-cuda12x) or set backend = \"auto\" / \"numpy\"") from exc
        log.debug("no GPU backend (%s: %s): numpy", type(exc).__name__, exc)
        return NUMPY


_current: contextvars.ContextVar[Backend] = contextvars.ContextVar("geoeyes_compute_backend", default=NUMPY)


def current() -> Backend:
    """The backend of the current run (NumPy unless a run set another one)."""
    return _current.get()


@contextlib.contextmanager
def use(backend: Backend | str | None):
    """Run the enclosed code on ``backend`` (a ``Backend`` or a name for ``resolve``)."""
    be = backend if isinstance(backend, Backend) else resolve(backend)
    token = _current.set(be)
    try:
        yield be
    finally:
        _current.reset(token)
        be.free_memory()


def info(backend: str | None = "auto") -> dict[str, Any]:
    """What ``resolve`` would choose, for ``geoeyes check`` (never raises)."""
    try:
        be = resolve(backend)
        return {"ok": True, "backend": be.name, "describe": be.describe()}
    except ConfigError as exc:
        return {"ok": False, "backend": None, "describe": str(exc)}
