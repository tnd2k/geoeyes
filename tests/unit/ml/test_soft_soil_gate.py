"""Susceptibility: the soft-soil layer is dropped when the open grid sits at its 50 m cap."""
import numpy as np

from geoeyes.ml.susceptibility import SusceptibilityParams, soft_soil_gate


def test_gate_drops_a_saturated_layer():
    v = np.r_[np.full(90, 50.0), np.linspace(5, 45, 10), [np.nan] * 5]
    g = soft_soil_gate(v, 0.8)
    assert g["drop"] and g["cap_share"] == 0.9 and g["cells"] == 100


def test_gate_keeps_an_informative_layer():
    v = np.r_[np.full(50, 50.0), np.linspace(5, 45, 50)]
    g = soft_soil_gate(v, 0.8)
    assert not g["drop"] and g["cap_share"] == 0.5


def test_gate_empty_and_default():
    assert not soft_soil_gate(np.array([np.nan, np.nan]), 0.8)["drop"]
    assert SusceptibilityParams().soft_soil_max_cap_share == 0.8
    assert SusceptibilityParams.from_dict({"soft_soil_max_cap_share": 0.95}).soft_soil_max_cap_share == 0.95
