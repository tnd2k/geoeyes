"""L3c harness: the paired block bootstrap sees a real gain and not a null one; settings grid; verdict rule."""
import numpy as np
import pandas as pd

from geoeyes.landslide import improve as im


def _tab(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 2, n)
    return pd.DataFrame({"label": y, f"block_{im.BLOCK_M:g}": rng.integers(0, 40, n)}), y, rng


def test_paired_bootstrap_detects_a_gain_and_not_noise():
    t, y, rng = _tab()
    weak = y * 0.3 + rng.normal(0, 1, len(y))
    strong = y * 1.0 + rng.normal(0, 1, len(y))
    r = im.paired_bootstrap([t], [weak], [strong], n=200)
    assert r["delta"] > 0.1 and r["ci95"][0] > 0
    same = im.paired_bootstrap([t], [weak], [weak + rng.normal(0, 1e-6, len(y))], n=200)
    assert abs(same["delta"]) < 1e-3 and same["ci95"][0] <= 0 <= same["ci95"][1]


def test_cross_oof_is_oof_on_the_same_rows_and_never_trains_on_test_blocks():
    t, y, rng = _tab(600)
    t["x1"] = y + rng.normal(0, 1, len(y))
    t["x2"] = rng.normal(0, 1, len(y))
    prm = {**im.BASE_RF, "n_estimators": 20}
    col = f"block_{im.BLOCK_M:g}"
    a = im.cross_oof(prm, 0, t, t, ["x1", "x2"], 5)
    b = im._oof(prm, 0, t[["x1", "x2"]], y, t[col].to_numpy(), 5)
    assert np.allclose(a, b)
    other = t.assign(**{col: t[col] + 1000})                    # rows in blocks the test never uses: always trained
    assert np.isfinite(im.cross_oof(prm, 0, other, t, ["x1", "x2"], 5)).all()


def test_cross_oof_never_trains_on_a_test_block(monkeypatch):
    t, y, rng = _tab(600)
    t["x1"] = rng.normal(0, 1, len(y))
    col = f"block_{im.BLOCK_M:g}"
    train = pd.concat([t, t.assign(**{col: t[col] + 1000})], ignore_index=True).assign(weight=1.0)
    seen = []

    class Spy:
        def fit(self, x, yy, **kw):
            seen.append(set(train.loc[x.index, col]))
            assert len(kw["randomforestclassifier__sample_weight"]) == len(x)
            return self

        def predict_proba(self, x):
            seen[-1] = (seen[-1], set(t.loc[x.index, col]))
            return np.full((len(x), 2), 0.5)

    monkeypatch.setattr(im, "rf", lambda *a: Spy())
    im.cross_oof({}, 0, train, t, ["x1"], 5)
    assert len(seen) == 5
    for fit_blocks, test_blocks in seen:
        assert not fit_blocks & test_blocks and {b + 1000 for b in test_blocks} <= fit_blocks


def test_configs_and_verdict():
    c = im.configs({"a": [1, 2], "b": ["x", "y", "z"]})
    assert len(c) == 6 and im.key({"b": 1, "a": 2}) == "a=2,b=1"
    base = {"transfer": {"K->M": 0.70, "M->K": 0.66}}
    ok = im.verdict(base, {"transfer": {"K->M": 0.705, "M->K": 0.655}}, {"delta": 0.012, "ci95": [0.002, 0.02]})
    assert ok["keep"]
    lost = im.verdict(base, {"transfer": {"K->M": 0.68, "M->K": 0.67}}, {"delta": 0.02, "ci95": [0.01, 0.03]})
    assert not lost["keep"]                                      # one transfer fell by 0.02
    small = im.verdict(base, base, {"delta": 0.006, "ci95": [0.001, 0.01]})
    assert not small["keep"]
