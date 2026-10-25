"""geoeyes.core: types, time conversions, hashing, logging."""
import io
import json
import logging
from datetime import date

import numpy as np
import pytest

from geoeyes.core import hashing, timeutil
from geoeyes.core.errors import ConfigError, GeoEyesError, PhaseError
from geoeyes.core.logging import configure, event, file_log, log_context
from geoeyes.core.types import BBox, OrbitDirection


def test_orbit_direction_aliases():
    assert OrbitDirection.parse("ASCENDING") is OrbitDirection.ASCENDING
    assert OrbitDirection.parse("desc") is OrbitDirection.DESCENDING
    assert OrbitDirection.DESCENDING.short == "desc"
    with pytest.raises(ConfigError):
        OrbitDirection.parse("sideways")


def test_bbox_validates_and_buffers():
    b = BBox.from_sequence([-99.03, 19.30, -98.98, 19.42])
    assert b.contains(-99.0, 19.35) and not b.contains(-99.1, 19.35)
    assert b.buffered(0.01).west == pytest.approx(-99.04)
    with pytest.raises(ConfigError):
        BBox(10, 0, 5, 1)


def test_errors_share_a_base():
    e = PhaseError("unwrap", "no PS")
    assert isinstance(e, GeoEyesError) and e.phase == "unwrap" and "unwrap: no PS" in str(e)


def test_datenum_roundtrip_and_datetime64():
    d = date(2024, 7, 11)
    assert timeutil.to_datenum(d) == d.toordinal() + 366
    assert timeutil.from_datenum(timeutil.to_datenum(d)) == d
    arr = timeutil.to_datetime64(["20240626", date(2024, 7, 11), "2024-08-15"])
    assert arr.dtype == np.dtype("datetime64[D]")
    assert timeutil.format_yyyymmdd(arr[1]) == "20240711"
    t = timeutil.decimal_years(arr)
    assert t[0] == 0 and t[-1] == pytest.approx(50 / 365.25)


def test_hashing_is_stable_and_order_independent_for_dicts():
    a = {"b": 1, "a": [1.0, 2.0], "c": np.float32(0.5)}
    b = {"c": 0.5, "a": [1.0, 2.0], "b": 1}
    assert hashing.sha256_params(a) == hashing.sha256_params(b)
    x = np.arange(6, dtype=np.float32)
    assert hashing.sha256_array(x) != hashing.sha256_array(x.reshape(2, 3))
    assert hashing.combine("a", "b") != hashing.combine("b", "a")


def test_sha256_file(tmp_path):
    import hashlib
    p = tmp_path / "f.bin"
    p.write_bytes(b"geoeyes" * 10_000)
    assert hashing.sha256_file(p) == hashlib.sha256(b"geoeyes" * 10_000).hexdigest()


def test_logging_context_jsonl_and_phase_file(tmp_path):
    jsonl = tmp_path / "run" / "log.jsonl"
    console = io.StringIO()
    configure("INFO", jsonl=jsonl, console_stream=console)
    log = logging.getLogger("geoeyes.test")
    try:
        with log_context(run_id="r1", phase="unwrap"), file_log(tmp_path / "unwrap.log"):
            with log_context(track="capella-asc"):
                log.info("hello %s", "world")
            event(log, "phase_end", status="ok", duration_s=1.5, name="clash")
        log.debug("debug only in jsonl")
    finally:
        configure(console=False)
    recs = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
    hello = next(r for r in recs if r["msg"] == "hello world")
    assert hello["run_id"] == "r1" and hello["phase"] == "unwrap" and hello["track"] == "capella-asc"
    end = next(r for r in recs if r.get("event") == "phase_end")
    assert end["status"] == "ok" and end["duration_s"] == 1.5 and end["name_"] == "clash"
    assert "track" not in end
    assert any(r["msg"] == "debug only in jsonl" for r in recs)
    assert "[unwrap/capella-asc] hello world" in console.getvalue()
    assert "debug only" not in console.getvalue()
    text = (tmp_path / "unwrap.log").read_text(encoding="utf-8")
    assert "hello world" in text and "debug only" not in text
