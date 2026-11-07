"""Reliability of mapped landslides (geoeyes.landslide.reliability): the terrain classes."""
import pandas as pd

from geoeyes.landslide import reliability as rl


def test_classes_follow_the_terrain_rules():
    t = pd.DataFrame({
        "max_slope":              [35, 12, 30, 18, 30, 30],
        "max_slope_aw3d30":       [33, 13, 31, 17, 30, 30],
        "max_hand_m":             [40, 30, 2, 40, 40, 40],
        "min_dist_stream_1km2_m": [300, 300, 0, 300, 300, 300],
        "drop_m":                 [40, 20, 30, 30, 4, 40],
        "cleared_before":         [0, 0, 0, 0, 0, 0.8]})
    got = rl.classify(t).tolist()
    assert got == ["reliable", "implausible", "implausible", "doubtful", "doubtful", "doubtful"]
    s = rl.summary(t.assign(reliability=got))
    assert s["share"]["implausible"] == round(2 / 6, 4) and s["polygons"] == 6
