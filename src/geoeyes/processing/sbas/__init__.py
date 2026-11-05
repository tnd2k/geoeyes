"""Small-baseline subset (SBAS) time series (docs/en/refactor/TODO.md item 10; Berardino et al. 2002).

    network.py    pairs within the baseline limits, redundant short pairs, connectivity             S1
    pairs.py      multilooked interferograms and coherence, from the SLCs or the phase-linked phase   S2
    closure.py    phase closure of the unwrapped triplets: pairs with unwrapping errors              S3
    invert.py     velocity between dates by SVD (minimum norm across subsets), temporal coherence    S4

Unwrapping uses the refined IRLS solver of the point chain (``processing.ps.unwrap.irls``).
"""
