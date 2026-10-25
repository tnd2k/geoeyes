"""Load / save ``project.toml``.

Effective configuration = sensor preset (``presets/<sensor>.toml``, for the sensor of the first
track) deep-merged with the user's file; the merged dict is validated into a frozen
``ProjectConfig``. ``resolve_subswath`` applies ``[overrides.<IWx>]`` for subswath-scoped phases.
"""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
from pydantic import ValidationError

from geoeyes.config.schema import ProjectConfig
from geoeyes.core.errors import ConfigError

PRESETS = Path(__file__).resolve().parent / "presets"


def deep_merge(base: dict, over: dict) -> dict:
    """Nested dicts merge key by key; any other value in ``over`` replaces the base value."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def preset(sensor: str) -> dict:
    p = PRESETS / f"{sensor}.toml"
    return tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_dict(data: dict[str, Any], *, apply_preset: bool = True) -> ProjectConfig:
    merged = data
    if apply_preset:
        tracks = data.get("tracks") or []
        sensor = tracks[0].get("sensor") if tracks else None
        if sensor:
            merged = deep_merge(preset(sensor), data)
    try:
        return ProjectConfig.model_validate(merged)
    except ValidationError as exc:
        raise ConfigError(_format(exc)) from None


def load(path: str | Path, *, apply_preset: bool = True) -> ProjectConfig:
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{path}: not found") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from None
    try:
        return load_dict(data, apply_preset=apply_preset)
    except ConfigError as exc:
        raise ConfigError(f"{path}:\n{exc}") from None


def to_dict(cfg: ProjectConfig) -> dict[str, Any]:
    """Plain TOML-ready dict (None dropped, tuples as lists, dates as dates)."""
    return _strip_none(cfg.model_dump(mode="python", by_alias=True))


def dump(cfg: ProjectConfig | dict, path: str | Path) -> Path:
    data = to_dict(cfg) if isinstance(cfg, ProjectConfig) else _strip_none(cfg)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(_tomlable(data)), encoding="utf-8")
    return path


def resolve_subswath(cfg: ProjectConfig, subswath: str) -> ProjectConfig:
    """Configuration with ``[overrides.<subswath>]`` deep-merged on top (lists/scalars replace)."""
    over = cfg.overrides.get(subswath)
    if not over:
        return cfg
    data = deep_merge(to_dict(cfg), over)
    return load_dict(data, apply_preset=False)


def _strip_none(obj):
    if isinstance(obj, dict):
        return {k: _strip_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [_strip_none(v) for v in obj if v is not None]
    return obj


def _tomlable(obj):
    """Enum -> value; TOML has no null, empty tables are fine."""
    from enum import Enum
    if isinstance(obj, dict):
        return {str(k): _tomlable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_tomlable(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj


def _format(exc: ValidationError) -> str:
    lines = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"])
        lines.append(f"  {loc or '<root>'}: {e['msg']}")
    return "invalid project configuration:\n" + "\n".join(lines)
