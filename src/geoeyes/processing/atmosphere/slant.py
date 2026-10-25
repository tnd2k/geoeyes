"""Zenith delay -> interferometric phase (TRAIN ``aps_weather_model_InSAR.m``).

The stacks are flattened as ``slc[ref]·conj(slc[k])`` with SLC phase exp(-j4πR/λ), so a delay d (m) of an
acquisition is a SAR phase -4π·d/λ and enters interferogram k as ph_SAR[ref] - ph_SAR[k] — the same sign as
the linear APS, which is fitted to the unwrapped phase directly.
"""
from __future__ import annotations

import numpy as np


def zenith_to_slant(zenith_m: np.ndarray, incidence_rad: np.ndarray) -> np.ndarray:
    return zenith_m / np.cos(np.clip(incidence_rad, 0.05, np.pi / 2 - 0.01))


def sar_phase(slant_m: np.ndarray, wavelength: float) -> np.ndarray:
    return -4.0 * np.pi / float(wavelength) * slant_m


def interferogram_phase(ph_sar: np.ndarray, master_ix: int) -> np.ndarray:
    """(n, n_epoch) phase of every epoch's interferogram with the master (master column 0); NaN where either
    acquisition has no weather data."""
    return ph_sar[:, master_ix:master_ix + 1] - ph_sar


def zenith_to_ifg_phase(zenith_m: np.ndarray, incidence_rad: np.ndarray, wavelength: float,
                        master_ix: int) -> np.ndarray:
    """``zenith_m`` (n, n_epoch) delays per epoch, ``incidence_rad`` (n,) -> (n, n_epoch) phase (rad)."""
    slant = zenith_to_slant(np.asarray(zenith_m, np.float64), np.asarray(incidence_rad, np.float64)[:, None])
    return interferogram_phase(sar_phase(slant, wavelength), master_ix)
