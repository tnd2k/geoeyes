"""InSAR against GNSS (Nevada Geodetic Laboratory) and GNSS calibration of the InSAR series.

Method, sources and results: ``docs/en/research/gnss-insar-calibration.md``.
"""
from __future__ import annotations

from typing import Any

from geoeyes.validation.gnss.compare import GnssParams, compare, correction, read_comparison


def run_gnss(cfg, project, ws, product_id: str, overrides: dict[str, Any] | None = None, progress=None) -> dict:
    """GNSS comparison of one product of ``project`` with ``[validation.gnss]`` (+ ``overrides``)."""
    params = GnssParams.from_dict({**dict(cfg.validation.gnss), **(overrides or {})})
    return compare(project.product(product_id), project.analysis("gnss", product_id), params,
                   ws.cache_dir("gnss") / "ngl", progress=progress)


__all__ = ["GnssParams", "compare", "correction", "read_comparison", "run_gnss"]
