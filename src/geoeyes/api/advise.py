"""Site advisor for the web app (site advisor V3): the profile of an AOI, the rules that apply, the suggested values
with their reasons in English and Vietnamese, and for a project the comparison with its configuration. The same
code as ``geoeyes advise``; no language model."""
from __future__ import annotations

import tomllib

from geoeyes.workspace import ProjectLayout, WorkspaceLayout


def _payload(ws: WorkspaceLayout, bbox: list[float], dem: str, project=None, cfg=None, raw=None,
             refresh: bool = False) -> dict:
    from geoeyes.advisor import rules
    from geoeyes.advisor.profile import profile, summary
    p = profile(bbox, cache_root=ws.cache, dem=dem, project=project, cfg=cfg, refresh=refresh)
    advice = rules.evaluate(p)
    _, rs = rules.load()
    by_id = {r.id: r for r in rs}
    cmp = rules.compare(advice, cfg, raw) if cfg is not None else None
    return {
        "profile": p,
        "summary": {"en": summary(p, "en").splitlines(), "vi": summary(p, "vi").splitlines()},
        "matched": [{"id": rid, "why": by_id[rid].why, "source": by_id[rid].source} for rid in advice.matched],
        "skipped": advice.skipped,
        "recipe": [{"path": s.path, "value": s.value, "rule": s.rule, "why": s.why,
                    "replaced": [{"rule": r, "value": v} for r, v in s.replaced]} for s in advice.recipe.values()],
        "notes": [{"rule": rid, "text": note} for rid, note in advice.notes],
        "compare": cmp,
    }


def for_project(ws: WorkspaceLayout, project: ProjectLayout, refresh: bool = False) -> dict:
    from geoeyes.config.loader import load
    from geoeyes.core.errors import ConfigError
    cfg = load(project.config)
    if not (cfg.aoi and cfg.aoi.bbox):
        raise ConfigError("the project has no [aoi] bbox: the advisor needs the area")
    raw = tomllib.loads(project.config.read_text(encoding="utf-8"))
    return _payload(ws, list(cfg.aoi.bbox), str(cfg.stack.dem or "srtm-1"), project, cfg, raw, refresh)


def for_bbox(ws: WorkspaceLayout, bbox: list[float], dem: str = "copernicus-30") -> dict:
    return _payload(ws, [float(v) for v in bbox], dem)
