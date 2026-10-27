"""Learning path in the web app (page "Principles", route #/learn): one pair of a project's stack, step by step
(geoeyes.learn)."""
from __future__ import annotations

from dataclasses import MISSING, fields
from pathlib import Path

import numpy as np

from geoeyes.core.errors import ConfigError
from geoeyes.learn import PairParams, overview, pair_layers, points_in_crop, thumbnail
from geoeyes.learn.pair import LAYERS, point_series
from geoeyes.workspace import ProjectLayout


def stacks(project: ProjectLayout) -> dict:
    out = []
    for d in sorted((project.root / "stacks").glob("*")):
        if (d / "stack.zarr").exists():
            try:
                out.append(overview(d / "stack.zarr"))
            except Exception as exc:                      # a stack being built, or an old layout
                out.append({"stack_id": d.name, "error": str(exc)})
    return {"stacks": out}


def _stack(project: ProjectLayout, stack_id: str) -> Path:
    p = project.stack_store(stack_id)
    if not p.exists():
        raise FileNotFoundError(f"no stack {stack_id!r}")
    return p


def params(query: dict) -> PairParams:
    types = {"str": str, "int": int, "float": float, "bool": bool}
    kinds = {f.name: types[str(f.type)] for f in fields(PairParams)}
    out = {}
    for k, v in query.items():
        if k not in kinds:
            continue
        t = kinds[k]
        try:
            out[k] = (v.lower() in ("1", "true", "yes")) if t is bool else t(v)
        except ValueError:
            raise ConfigError(f"{k}: {v!r} is not a {t.__name__}") from None
    missing = [f.name for f in fields(PairParams) if f.name not in out and f.default is MISSING]
    if missing:
        raise ConfigError(f"missing {missing}")
    return PairParams(**out)


def thumb(project: ProjectLayout, stack_id: str) -> tuple[dict, bytes]:
    return thumbnail(_stack(project, stack_id))


def pair(project: ProjectLayout, stack_id: str, query: dict) -> tuple[dict, bytes]:
    meta, layers = pair_layers(_stack(project, stack_id), params(query))
    return meta, b"".join(np.ascontiguousarray(layers[k], np.float32).tobytes() for k in LAYERS)


def points(project: ProjectLayout, stack_id: str, query: dict) -> dict:
    return points_in_crop(project.root, _stack(project, stack_id), params(query), query.get("product") or None)


def series(project: ProjectLayout, product_id: str, uid: str) -> dict:
    return point_series(project.root, product_id, uid)


def ionosphere(project: ProjectLayout, stack_id: str, date: str | None = None) -> dict:
    from geoeyes.learn import ionosphere as iono
    p = _stack(project, stack_id)
    return iono.field(p, date) if date else iono.summary(p)
