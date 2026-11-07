"""SBAS pair network (S1): the small-baseline pairs of a stack and their connectivity.

A pair (i, j), i < j, is kept when ``|B⊥ᵢ − B⊥ⱼ| ≤ max_perp_m`` and:

* ``max_temporal_days > 0``: ``tⱼ − tᵢ ≤ max_temporal_days``;
* ``max_temporal_days == 0``: j is one of the ``n_nearest`` next dates of i (a sequential network);

plus, with ``redundant``, every pair within ``redundant_max_days`` and the baseline limit (the short, coherent pairs
that tie the network).
Pairs shorter than ``min_temporal_days`` are never kept (the short-pair phase bias over crops, "fading signal").
Disconnected subsets are reported; with ``bridge`` the last date of each subset is linked to the first later date of
the next one, whatever the baseline (the inversion would otherwise need the minimum-norm SVD across them).
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date

import numpy as np


@dataclass(frozen=True)
class NetworkParams:
    max_perp_m: float = 150.0
    max_temporal_days: int = 0          # 0: a sequential network of n_nearest
    n_nearest: int = 3
    redundant: bool = True
    redundant_max_days: int = 24
    bridge: bool = True
    min_temporal_days: int = 0          # pairs shorter than this are left out (short-pair phase bias)


@dataclass
class Network:
    dates: list[date]
    pairs: list[tuple[int, int]]
    bridged: list[tuple[int, int]] = field(default_factory=list)
    components_before_bridge: int = 1

    @property
    def n(self) -> int:
        return len(self.dates)

    def days(self) -> np.ndarray:
        d0 = self.dates[0]
        return np.array([(d - d0).days for d in self.dates], float)

    def design(self) -> np.ndarray:
        """Berardino design matrix (pairs × intervals): the time spent in each interval between consecutive dates."""
        t = self.days()
        dt = np.diff(t)
        b = np.zeros((len(self.pairs), self.n - 1))
        for k, (i, j) in enumerate(self.pairs):
            b[k, i:j] = dt[i:j]
        return b

    def summary(self) -> dict:
        span = [(self.dates[j] - self.dates[i]).days for i, j in self.pairs]
        return {"dates": self.n, "pairs": len(self.pairs), "bridged": [[str(self.dates[i]), str(self.dates[j])]
                                                                        for i, j in self.bridged],
                "components_before_bridge": self.components_before_bridge,
                "days": {"min": int(min(span)), "median": float(np.median(span)), "max": int(max(span))}
                if span else {}}


def components(n: int, pairs: list[tuple[int, int]]) -> list[list[int]]:
    """Connected subsets of dates (union-find), each sorted, ordered by their first date."""
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, j in pairs:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    groups: dict[int, list[int]] = {}
    for k in range(n):
        groups.setdefault(find(k), []).append(k)
    return sorted(groups.values(), key=lambda g: g[0])


def select_pairs(dates: list[date], bperp_m, p: NetworkParams | None = None) -> Network:
    """The SBAS network of a stack (``dates`` sorted, ``bperp_m`` perpendicular baselines to any common reference)."""
    p = p or NetworkParams()
    order = np.argsort(np.array(dates, dtype="datetime64[D]"))
    if not np.all(order == np.arange(len(dates))):
        raise ValueError("dates must be sorted")
    b = np.asarray(bperp_m, float)
    t = np.array([(d - dates[0]).days for d in dates])
    n = len(dates)
    keep: set[tuple[int, int]] = set()
    for i in range(n):
        later = [j for j in range(i + 1, n) if abs(b[j] - b[i]) <= p.max_perp_m and t[j] - t[i] >= p.min_temporal_days]
        if p.max_temporal_days > 0:
            keep |= {(i, j) for j in later if t[j] - t[i] <= p.max_temporal_days}
        else:
            keep |= {(i, j) for j in later[:p.n_nearest]}
        if p.redundant:
            keep |= {(i, j) for j in later if t[j] - t[i] <= p.redundant_max_days}
    pairs = sorted(keep)
    comps = components(n, pairs)
    net = Network(list(dates), pairs, components_before_bridge=len(comps))
    if p.bridge and len(comps) > 1:
        for a, c in itertools.pairwise(comps):
            i = max(a)
            later = [j for j in c if j > i] or [min(c)]
            pr = tuple(sorted((i, later[0])))
            if pr not in keep:
                net.bridged.append(pr)
                keep.add(pr)
        net.pairs = sorted(keep)
        if len(components(n, net.pairs)) > 1:          # interleaved subsets: link every date to the next
            for i in range(n - 1):
                if (i, i + 1) not in keep:
                    net.bridged.append((i, i + 1))
                    keep.add((i, i + 1))
            net.pairs = sorted(keep)
    return net
