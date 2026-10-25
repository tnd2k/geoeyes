"""Canonical paths inside a GeoEyes workspace. Code and data are separate: the workspace root is
``GEOEYES_WORKSPACE`` (see ``geoeyes.config.settings``), never the repository.

    $GEOEYES_WORKSPACE/
      archive/<sensor>/<track>/<YYYY>/<scene_id>/     raw scenes shared by all projects (immutable)
      projects/<project>/
        project.toml  aoi.geojson
        raw/                                         references to archive scenes
        stacks/<stack_id>/                           stack.zarr, network/, manifest.json      [hot]
        ps_runs/<psrun_id>/                          params.json, state.h5 | tiles/, figures/  [hot]
        products/<product_id>/                       immutable products                        [warm]
        exports/<product_id>/                        derived GIS formats                       [tmp]
        runs/<run_id>/                               manifest.json, log.jsonl, logs/, progress.json
        .state/                                      state.json, locks/
      catalog/                                       catalog.json (STAC), index.duckdb
      cache/                                         dem/, orbits/, era5/, gacos/  (disposable)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from geoeyes.core.errors import ConfigError

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _safe_id(kind: str, value: str) -> str:
    if not _ID_RE.match(value) or ".." in value:
        raise ConfigError(f"invalid {kind} id {value!r}")
    return value


@dataclass(frozen=True)
class WorkspaceLayout:
    root: Path

    @classmethod
    def at(cls, root: str | Path) -> WorkspaceLayout:
        return cls(Path(root).expanduser().resolve())

    @property
    def archive(self) -> Path:
        return self.root / "archive"

    @property
    def projects(self) -> Path:
        return self.root / "projects"

    @property
    def catalog(self) -> Path:
        return self.root / "catalog"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    def cache_dir(self, kind: str) -> Path:
        return self.cache / _safe_id("cache", kind)

    def scene_dir(self, sensor: str, track: str, year: int, scene_id: str) -> Path:
        return self.archive / _safe_id("sensor", sensor) / _safe_id("track", track) / f"{year:04d}" / _safe_id(
            "scene", scene_id)

    def project(self, name: str) -> ProjectLayout:
        return ProjectLayout(self.projects / _safe_id("project", name))

    def list_projects(self) -> list[str]:
        if not self.projects.exists():
            return []
        return sorted(p.name for p in self.projects.iterdir() if (p / "project.toml").exists())


@dataclass(frozen=True)
class ProjectLayout:
    root: Path

    @property
    def name(self) -> str:
        return self.root.name

    @property
    def config(self) -> Path:
        return self.root / "project.toml"

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    def stack(self, stack_id: str) -> Path:
        return self.root / "stacks" / _safe_id("stack", stack_id)

    def stack_store(self, stack_id: str) -> Path:
        return self.stack(stack_id) / "stack.zarr"

    def ps_run(self, psrun_id: str) -> Path:
        return self.root / "ps_runs" / _safe_id("ps_run", psrun_id)

    def product(self, product_id: str) -> Path:
        return self.root / "products" / _safe_id("product", product_id)

    def export(self, product_id: str) -> Path:
        return self.root / "exports" / _safe_id("product", product_id)

    def run(self, run_id: str) -> Path:
        return self.root / "runs" / _safe_id("run", run_id)

    @property
    def state_dir(self) -> Path:
        return self.root / ".state"

    @property
    def state_file(self) -> Path:
        return self.state_dir / "state.json"

    @property
    def locks(self) -> Path:
        return self.state_dir / "locks"

    def ensure(self) -> ProjectLayout:
        for d in (self.raw, self.root / "stacks", self.root / "ps_runs", self.root / "products",
                  self.root / "exports", self.root / "runs", self.locks):
            d.mkdir(parents=True, exist_ok=True)
        return self
