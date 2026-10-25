"""Phase adapters: project configuration + stores -> processing runners (ARCHITECTURE §6.4).

Until the planner/runner of §6.4 exists, ``run_track`` chains the phases implemented natively for one track:
``phase_linking`` (when enabled) then the point engine (``ps`` or ``ps_lite``).
"""
from __future__ import annotations

from pathlib import Path

from geoeyes.controller.phases import phase_linking, ps


def run_track(cfg, store, out_dir: str | Path, *, engine: str | None = None, run_id: str = "", track_id: str = "",
              psrun_id: str = "", force: bool = False, resume_from: str | Path | None = None) -> dict:
    """Phase linking (skipped when already done with the same parameters, unless ``force``) then PS processing
    (``resume_from``: reuse steps 1-5 of a previous ``ps`` run)."""
    pl = phase_linking.run(cfg, store, force=force)
    out = ps.run(cfg, store, out_dir, engine=engine, run_id=run_id, track_id=track_id, psrun_id=psrun_id,
                 resume_from=resume_from)
    return {"phase_linking": pl, "ps": out}


__all__ = ["phase_linking", "ps", "run_track"]
