"""A landslide study: ``<workspace>/studies/<name>/study.toml`` (paths relative to the workspace root).

    schema = "geoeyes.landslide_study/1"
    [study]       name, description
    [inventory]   polygons (GeoPackage, layer "polygons"), citation
    [area]        file, layer, name: the study area (one row of a GeoPackage, by its "name" column)
    [footprints]  file (from ``geoeyes landslide audit``), main, sensitivity: the variants used for negatives
    [[events]]    name, date: the events of the inventory used, oldest first
    [labels]      LabelParams (every key optional)
    [models]      ModelParams (every key optional)
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from geoeyes.core.errors import ConfigError

SCHEMA = "geoeyes.landslide_study/1"
FOOTPRINT_VARIANTS = ("near", "hull", "hull_shrunk")


@dataclass(frozen=True)
class LabelParams:
    """``[labels]`` of study.toml (every key optional)."""

    cell_m: float = 30.0                 # grid of the study (GLO-30, Hansen GFC)
    negative_buffer_m: float = 60.0      # negatives farther than this from any polygon of the event (2 cells)
    ratio: float = 1.0                   # negatives per positive, per draw
    draws: int = 10                      # independent draws of the negatives
    upper_fraction: float = 1 / 3        # variant b: cells in this upper part of the polygon's height range
    seed: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> LabelParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[labels]: unknown key(s) {unknown}; known: {sorted(names)}")
        p = cls(**{f.name: type(getattr(cls, f.name))(d[f.name]) for f in fields(cls) if f.name in d})
        if p.cell_m <= 0 or p.negative_buffer_m < 0 or p.ratio <= 0 or p.draws < 1 or not 0 < p.upper_fraction <= 1:
            raise ConfigError("[labels]: cell_m > 0, negative_buffer_m >= 0, ratio > 0, draws >= 1, "
                              "0 < upper_fraction <= 1")
        return p


@dataclass(frozen=True)
class ModelParams:
    """``[models]`` of study.toml (every key optional): L3 susceptibility models."""

    folds: int = 5
    blocks_m: tuple[float, ...] = (5000.0, 2000.0)    # spatial CV blocks; the first chooses the model (L3 gate: not
    #                                                   smaller than the residual range) and drives interpretation
    exclude: tuple[str, ...] = ("regolith_thick_m",)  # L2 gate: 1 km cells jumping between 0 and the 50 m cap
    aspect: bool = False                              # L2a / L2b gate: an artefact of the inventories
    roads: bool = False                               # L3 gate: today's OSM roads, gain ≤ 0.01, not transferable
    reliable: bool = False                            # L3b.6: positives of reliable polygons only (terrain flags)
    domain_deg: float = 0.0                           # L3b.6: positives and negatives on cells this steep (0: all)
    champion: str = ""                                # "<event | pooled>:<model>" carried into operations (O4)
    challenger: str = ""                              # the model scored beside it each season (L9 R3)
    min_area_m2: float = 1000.0                       # transfer test on the landslides at least this large too
    seed: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> ModelParams:
        d = dict(d or {})
        names = {f.name for f in fields(cls)}
        unknown = sorted(set(d) - names)
        if unknown:
            raise ConfigError(f"[models]: unknown key(s) {unknown}; known: {sorted(names)}")
        out = {}
        for f in fields(cls):
            if f.name in d:
                default = getattr(cls, f.name)
                out[f.name] = tuple(type(default[0])(x) if default else x for x in d[f.name]) \
                    if isinstance(default, tuple) else type(default)(d[f.name])
        p = cls(**out)
        if p.folds < 2 or not p.blocks_m:
            raise ConfigError("[models]: folds >= 2 and at least one block size")
        return p


@dataclass
class Study:
    name: str
    root: Path                           # <workspace>/studies/<name>
    workspace: Path
    inventory: Path
    citation: str
    area_file: Path
    area_layer: str
    area_name: str
    footprints: Path
    footprint_main: str
    footprint_sensitivity: str
    events: list[tuple[str, str]]        # (name, date), oldest first
    labels: LabelParams = field(default_factory=LabelParams)
    models: ModelParams = field(default_factory=ModelParams)
    description: str = ""

    def step_dir(self, step: str) -> Path:
        return self.root / step


def _path(ws: Path, s: str) -> Path:
    p = Path(s)
    return p if p.is_absolute() else ws / p


def load_study(workspace: Path, name: str) -> Study:
    root = Path(workspace) / "studies" / name
    cfg = root / "study.toml"
    if not cfg.exists():
        raise ConfigError(f"no study {name!r}: {cfg} not found")
    d = tomllib.loads(cfg.read_text(encoding="utf-8"))
    if d.get("schema") != SCHEMA:
        raise ConfigError(f"{cfg}: schema must be {SCHEMA!r}")
    try:
        inv, area, fp = d["inventory"], d["area"], d["footprints"]
        events = [(e["name"], e["date"]) for e in d["events"]]
        st = Study(name=d["study"]["name"], root=root, workspace=Path(workspace),
                   inventory=_path(workspace, inv["polygons"]), citation=inv["citation"],
                   area_file=_path(workspace, area["file"]), area_layer=area.get("layer", "pilot"),
                   area_name=area["name"], footprints=_path(workspace, fp["file"]),
                   footprint_main=fp.get("main", "near"), footprint_sensitivity=fp.get("sensitivity", "hull"),
                   events=events, labels=LabelParams.from_dict(d.get("labels")),
                   models=ModelParams.from_dict(d.get("models")),
                   description=d["study"].get("description", ""))
    except KeyError as exc:
        raise ConfigError(f"{cfg}: missing key {exc}") from None
    for v in (st.footprint_main, st.footprint_sensitivity):
        if v not in FOOTPRINT_VARIANTS:
            raise ConfigError(f"{cfg}: footprint variant {v!r} not in {FOOTPRINT_VARIANTS}")
    if not events:
        raise ConfigError(f"{cfg}: at least one [[events]]")
    return st
