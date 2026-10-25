"""Phase ``phase_linking``: ``[phase_linking]`` -> ``slc_linked`` in the track's StackStore."""
from __future__ import annotations

import logging

from geoeyes.core.errors import ConfigError
from geoeyes.processing.phase_linking import runner
from geoeyes.processing.phase_linking.runner import PhaseLinkingParams

log = logging.getLogger(__name__)

NATIVE_ESTIMATORS = ("evd", "emi", "mle", "pta", "adaptive")


def params(cfg) -> PhaseLinkingParams:
    sec = cfg.phase_linking
    if sec.estimator not in NATIVE_ESTIMATORS:
        raise ConfigError(f"phase_linking.estimator {sec.estimator!r} not ported yet (native: "
                          f"{', '.join(NATIVE_ESTIMATORS)})")
    if sec.shp_test not in ("ad", "ks"):
        raise ConfigError(f"phase_linking.shp_test {sec.shp_test!r} not ported yet (native: ad, ks)")
    if sec.nlinsar:
        raise ConfigError("phase_linking.nlinsar not ported yet")
    return PhaseLinkingParams.from_section(sec)


def is_done(cfg, store) -> bool:
    return cfg.phase_linking.enabled and runner.is_done(store, params(cfg))


def run(cfg, store, *, force: bool = False) -> dict | None:
    """None when disabled or already done with the same parameters."""
    if not cfg.phase_linking.enabled:
        return None
    p = params(cfg)
    if not force and runner.is_done(store, p):
        log.info("phase linking: up to date in %s, skipped", store.path)
        return None
    return runner.run(store, p, workers=cfg.compute.workers or None)
