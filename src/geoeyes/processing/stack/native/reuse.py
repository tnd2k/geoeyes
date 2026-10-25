"""Incremental build: the coregistered dates of a previous build of the same stack are copied, not coregistered again.

Only valid while the previous build used the same reference (master) and the same crop window: a new
reference changes every resampling and every flattening phase, so the whole stack is coregistered again
(the controller then writes a new store, the stack id carries the reference date). The caller lists the dates
whose raw scene is unchanged (``dates``); the others are coregistered.
"""
from __future__ import annotations

import logging
from datetime import date

import numpy as np

from geoeyes.io.stack import StackStore

log = logging.getLogger(__name__)


class Reuse:
    def __init__(self, store: StackStore, index: dict[date, int]):
        self.store = store
        self.index = index                       # date -> position in the previous store

    @classmethod
    def open(cls, store: StackStore | None, dates: set[date] | None, reference: date,
             crop: tuple[int, int, int, int]) -> Reuse | None:
        """``None`` when nothing can be reused (no previous store, other reference or other window)."""
        if store is None or not dates or not store.exists() or not store.has("slc"):
            return None
        a = store.attrs
        if a.get("reference_date") != str(reference):
            log.info("previous stack has reference %s, not %s: coregistering every date",
                     a.get("reference_date"), reference)
            return None
        if list(a.get("crop_rows", ())) != [crop[0], crop[1]] or list(a.get("crop_samples", ())) != [crop[2], crop[3]]:
            log.info("previous stack window %s x %s differs from %s: coregistering every date",
                     a.get("crop_rows"), a.get("crop_samples"), list(crop))
            return None
        old = [d.astype("datetime64[D]").astype(object) for d in store.open()["date"].values]
        index = {d: i for i, d in enumerate(old) if d in dates}
        if not index:
            return None
        log.info("reusing %d coregistered date(s) of the previous build", len(index))
        return cls(store, index)

    def __contains__(self, d: date) -> bool:
        return d in self.index

    def block(self, name: str, d: date, **isel) -> np.ndarray:
        return self.store.read(name, date=self.index[d], **isel)

    def value(self, name: str, d: date, default=0.0):
        """One per-date value (bperp, esd_shift, coreg_residual row) of the previous build."""
        return self.store.read(name, date=self.index[d]) if self.store.has(name) else default
