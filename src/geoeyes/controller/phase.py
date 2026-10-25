"""Phase contract and run context (ARCHITECTURE §6.1).

A phase plans nothing and holds no algorithm: it maps the project configuration and the stores of one track to
a processing runner, tells whether its output is already up to date (``fingerprint`` of the parameters and
inputs it depends on, recorded in the project state when it completes) and runs it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from geoeyes.config.schema import ProjectConfig, TrackConfig
from geoeyes.io.manifest import atomic_write_json, read_json
from geoeyes.workspace import ProjectLayout, WorkspaceLayout


@dataclass
class PhaseContext:
    cfg: ProjectConfig
    project: ProjectLayout
    workspace: WorkspaceLayout
    track: TrackConfig
    run_id: str = ""
    cache: dict[str, Any] = field(default_factory=dict)      # values shared by the phases of one track

    @property
    def track_id(self) -> str:
        return self.track.track_id


class Phase:
    """Base class: ``name``, ``enabled``, ``fingerprint``, ``outputs_exist``, ``run``."""

    name: ClassVar[str] = ""
    optional: ClassVar[bool] = False

    def enabled(self, ctx: PhaseContext) -> bool:
        return True

    def problem(self, ctx: PhaseContext) -> str | None:
        """Why the phase cannot run with this configuration (None = it can)."""
        return None

    def fingerprint(self, ctx: PhaseContext) -> str:
        raise NotImplementedError

    def outputs_exist(self, ctx: PhaseContext) -> bool:
        raise NotImplementedError

    def run(self, ctx: PhaseContext) -> dict[str, Any]:
        raise NotImplementedError

    def is_done(self, ctx: PhaseContext) -> bool:
        rec = ProjectState(ctx.project).get(ctx.track_id, self.name)
        return (rec is not None and rec.get("status") == "done" and rec.get("fingerprint") == self.fingerprint(ctx)
                and self.outputs_exist(ctx))


class ProjectState:
    """``<project>/.state/state.json``: last status of every (track, phase)."""

    def __init__(self, project: ProjectLayout):
        self.path: Path = project.state_file

    def load(self) -> dict:
        if not self.path.exists():
            return {"phases": {}}
        return read_json(self.path)

    def get(self, track: str, phase: str) -> dict | None:
        return self.load()["phases"].get(f"{track}/{phase}")

    def set(self, track: str, phase: str, **record) -> None:
        data = self.load()
        data["phases"][f"{track}/{phase}"] = {**record,
                                              "updated": datetime.now(UTC).isoformat(timespec="seconds")}
        atomic_write_json(self.path, data)
