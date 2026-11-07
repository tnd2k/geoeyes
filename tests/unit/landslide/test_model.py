"""Landslide study models (geoeyes.landslide.model): spatial folds never split a block, the calibration bins, the
[models] parameters."""
import numpy as np
import pandas as pd
import pytest

from geoeyes.core.errors import ConfigError
from geoeyes.landslide import model as md
from geoeyes.landslide.study import ModelParams


class _Spy:
    """A classifier that records the blocks it is trained on (class attribute: ``clone`` deep-copies parameters)."""

    seen: list[set] = []

    def get_params(self, deep=True):
        return {}

    def set_params(self, **k):
        return self

    def fit(self, x, y):
        _Spy.seen.append(set(x["block"]))
        return self

    def predict_proba(self, x):
        return np.column_stack([np.full(len(x), 0.5), np.full(len(x), 0.5)])


def test_spatial_folds_keep_every_block_on_one_side():
    rng = np.random.default_rng(0)
    n = 600
    x = pd.DataFrame({"block": rng.integers(0, 30, n), "v": rng.normal(size=n)})
    y = rng.integers(0, 2, n)
    _Spy.seen.clear()
    p = md.oof(_Spy(), x, y, x["block"].to_numpy(), 5, 0)
    assert np.isfinite(p).all() and len(_Spy.seen) == 5
    for train in _Spy.seen:
        held = set(x["block"]) - train
        assert held and not (held & train)


def test_calibration_bins_and_spatial_scores():
    o = pd.DataFrame({"p": [0.05, 0.15, 0.95, 0.85, 0.5, 0.55], "label": [0, 0, 1, 1, 0, 1]})
    c = md.calibration(o, bins=10)
    assert sum(c["n"]) == 6 and c["observed"][-1] == 1.0
    s = md.scores([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9])
    assert s["auc"] == 1.0


def test_model_params():
    p = ModelParams.from_dict({"blocks_m": [1000, 3000], "exclude": ["soil_clay"]})
    assert p.blocks_m == (1000.0, 3000.0) and p.exclude == ("soil_clay",) and p.aspect is False
    with pytest.raises(ConfigError):
        ModelParams.from_dict({"folds": 1})
    with pytest.raises(ConfigError):
        ModelParams.from_dict({"bogus": 1})
    v = md.variants(md.Spec(), 1000.0, "hull")
    assert v["with_aspect"].aspect and not v["no_roads"].roads and v["sensitivity_footprint"].footprint == "hull"
    v = md.variants(md.Spec(roads=False), 1000.0, "hull")
    assert v["with_roads"].roads and "no_roads" not in v
    assert set(md.SOIL) <= set(v["no_soil"].drop) and "lith_*" in v["terrain_forest"].drop
    assert md._dropped("lith_pa", v["terrain_forest"].drop) and not md._dropped("slope_deg", v["terrain_forest"].drop)
    assert ModelParams().blocks_m[0] == 5000.0 and ModelParams().roads is False


class _Ed:
    """A stand-in for EventData: rows on a 100-cell-wide grid."""

    def __init__(self, event, cells, study):
        self.event, self.study, self.nx, self.draws = event, study, 100, 2
        self._cells = cells

    def columns(self, spec, kind):
        return ["a", "b"] if self.event == "E1" else ["b", "a", "c"]

    def rows(self, spec, draw):
        t = pd.DataFrame({"cell": self._cells, "label": [1, 0] * (len(self._cells) // 2)})
        return md.add_blocks(t, self.nx, self.study).assign(event=self.event)


def test_pooled_rows_share_blocks_and_columns():
    from types import SimpleNamespace
    st = SimpleNamespace(models=ModelParams(blocks_m=(300.0,)), labels=SimpleNamespace(cell_m=30.0))
    pooled = md.PooledData([_Ed("E1", [0, 5, 1000, 1005], st), _Ed("E2", [0, 15, 1000, 2000], st)])
    t = pooled.rows(md.Spec(), 0)
    assert pooled.columns(md.Spec(), "trees") == ["a", "b"] and pooled.draws == 2
    b = t.groupby("cell")["block_300"].nunique()
    assert (b == 1).all()                                  # a cell is in one block whatever its event
    assert t[t.cell == 0].block_300.iloc[0] == t[t.cell == 5].block_300.iloc[0] != t[t.cell == 15].block_300.iloc[0]


def test_alt_dem_replaces_the_terrain_columns():
    t = pd.DataFrame({"slope_deg": [10.0], "aw3d30_slope_deg": [12.0], "soil_clay": [3.0]})
    md.alt_dem(t, "aw3d30")
    assert t.slope_deg.iloc[0] == 12.0 and t.soil_clay.iloc[0] == 3.0
    assert md.variants(md.Spec(), 1000.0, "hull")["dem_aw3d30"].dem == "aw3d30"


def test_score_test_uses_every_negative_draw():
    t = pd.DataFrame({"cell": [1, 2, 3, 4, 5, 6] * 4, "label": [1] * 6 + [0] * 18,
                      "draw": [-1] * 6 + [0] * 6 + [1] * 6 + [2] * 6})
    t.loc[t.label == 0, "cell"] += 100
    p = pd.Series(np.r_[np.full(6, 0.9), np.full(6, 0.1)], index=np.r_[np.arange(1, 7), np.arange(101, 107)])
    big = pd.concat([t] * 2, ignore_index=True)
    s = md.score_test(big, p, {"all": big.label == 1, "none": big.label == 2})
    assert s["all"]["auc"] == 1.0 and s["all"]["draws"] == 3 and s["none"] == {"positives": 0}
