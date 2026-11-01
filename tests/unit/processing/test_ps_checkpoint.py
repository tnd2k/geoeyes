"""PS engine checkpoints: one per step, reused only with the same chained key, recomputed from ``from_step``,
``stop_after`` pauses the run; the step-2 grid is stored sparse."""
import dataclasses

import numpy as np
import pytest

from geoeyes.core.errors import PhasePaused
from geoeyes.processing.ps.checkpoints import Checkpoints, pack_gamma, status, unpack_gamma
from geoeyes.processing.ps.runner import stack_identity


def _keys(ck, gamma="g1"):
    ck.key(1, stack={"build": "b1"})
    ck.key(2, est_gamma=gamma)
    ck.key(3, select="s1")


def test_steps_reused_with_the_same_keys_only(tmp_path):
    ck = Checkpoints(tmp_path)
    _keys(ck)
    assert not ck.valid(1)
    ck.save(1, {"x": 1}, mean_range=850.0)
    ck.save(2, {"x": 2})
    ck.save(3, {"x": 3})
    again = Checkpoints(tmp_path)
    _keys(again)
    assert all(again.valid(n) for n in (1, 2, 3)) and again.load(3) == {"x": 3}
    assert again.meta(1)["mean_range"] == 850.0
    other = Checkpoints(tmp_path)
    _keys(other, gamma="g2")                     # step 2 changed: step 2 and every later step are not reused
    assert other.valid(1) and not other.valid(2) and not other.valid(3)
    forced = Checkpoints(tmp_path, from_step=2)
    _keys(forced)
    assert forced.valid(1) and not forced.valid(2) and not forced.valid(3)
    assert [s["saved"] is not None for s in status(tmp_path)][:4] == [True, True, True, False]


def test_stop_after_pauses(tmp_path):
    ck = Checkpoints(tmp_path, stop_after=2)
    ck.reached(1)
    with pytest.raises(PhasePaused) as e:
        ck.reached(2)
    assert e.value.step == 2
    with pytest.raises(ValueError):
        Checkpoints(tmp_path, from_step=9)


def test_gamma_grid_packed_sparse():
    @dataclasses.dataclass
    class G:
        ph_grid: np.ndarray
        K: np.ndarray

    grid = np.zeros((6, 7, 3), np.complex64)
    grid[2, 3] = [1 + 1j, 2, 3j]
    grid[5, 0, 1] = 4
    packed = pack_gamma(G(grid, np.arange(3.0)))
    assert packed["grid"][1].size == 2 and packed["g"].ph_grid.size == 0
    back = unpack_gamma(packed)
    assert np.array_equal(back.ph_grid, grid) and np.array_equal(back.K, np.arange(3.0))


def test_stack_identity_tracks_phase_linking():
    attrs = {"build_fingerprint": "b1", "scene_signatures": {"20260211": "s"},
             "phase_linking_done": {"estimator": "adaptive"}}
    assert stack_identity(attrs, "slc")["phase_linking"] is None
    assert stack_identity(attrs, "slc_linked") != stack_identity({**attrs, "phase_linking_done": {}}, "slc_linked")
