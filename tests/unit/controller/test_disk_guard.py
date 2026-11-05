"""A phase is refused before it starts when the disk is nearly full (the floor is set by GEOEYES_MIN_FREE_GB)."""
import pytest

from geoeyes.controller import pipeline as pl
from geoeyes.core.errors import PhaseError


def test_disk_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOEYES_MIN_FREE_GB", "0")
    assert pl.check_disk(tmp_path, "ps") > 0
    monkeypatch.setenv("GEOEYES_MIN_FREE_GB", "1e9")                # a billion GB: never available
    with pytest.raises(PhaseError, match="GB free on the disk"):
        pl.check_disk(tmp_path, "build_stack")
