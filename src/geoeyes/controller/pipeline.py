"""Planner and runner (ARCHITECTURE §6.3-6.4): the phases implemented natively, per track:

    [acquire] -> build_stack -> [phase_linking] -> ps -> build_product -> export -> report
    (ps = StaMPS-type engine or ps_lite, steps 1-8; product = immutable versioned point product; export = GIS)

``plan`` lists, per track and phase, whether it runs, is up to date (same fingerprint, outputs present) or is
disabled; ``run`` executes the plan under the project lock, with a run record (``runs/<run_id>/``: manifest,
log.jsonl, one text log per phase) and the phase status in ``.state/state.json``.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from geoeyes.config.schema import ProjectConfig
from geoeyes.controller.phase import Phase, PhaseContext, ProjectState
from geoeyes.controller.phases import acquire as acq
from geoeyes.controller.phases import build_stack as bs
from geoeyes.controller.phases import phase_linking as pl
from geoeyes.controller.phases import ps as psp
from geoeyes.core.errors import PhaseError
from geoeyes.core.hashing import sha256_params
from geoeyes.core.logging import event, file_log, log_context
from geoeyes.io.manifest import Manifest
from geoeyes.workspace import ProjectLayout, WorkspaceLayout

log = logging.getLogger(__name__)


def _store(ctx):
    from geoeyes.io.stack import StackStore
    return StackStore(bs.target(ctx)["path"])


class Acquire(Phase):
    """Sentinel-1 bursts from ASF into the workspace archive (``controller.phases.acquire``)."""

    name = "acquire"
    optional = True

    def enabled(self, ctx):
        return acq.enabled(ctx)

    def problem(self, ctx):
        return acq.problem(ctx)

    def fingerprint(self, ctx):
        return acq.fingerprint(ctx)

    def outputs_exist(self, ctx):
        return acq.outputs_exist(ctx)

    def changes(self, ctx):
        return acq.changes(ctx)

    def run(self, ctx):
        return acq.run(ctx)


class BuildStack(Phase):
    name = "build_stack"

    def problem(self, ctx):
        why = bs.problem(ctx)
        if why:
            return why
        try:
            bs.target(ctx)                           # scenes found, reference date valid
        except Exception as exc:
            return str(exc)
        return None

    def fingerprint(self, ctx):
        return bs.fingerprint(ctx)

    def outputs_exist(self, ctx):
        return bs.outputs_exist(ctx)

    def changes(self, ctx):
        return bs.changes(ctx)

    def run(self, ctx):
        return bs.run(ctx)


class PhaseLinking(Phase):
    name = "phase_linking"
    optional = True

    def enabled(self, ctx):
        return ctx.cfg.phase_linking.enabled

    def problem(self, ctx):
        try:
            pl.params(ctx.cfg)
        except Exception as exc:                     # unported estimator / SHP test
            return str(exc)
        return None

    def fingerprint(self, ctx):
        from geoeyes.processing.phase_linking.runner import fingerprint
        return sha256_params({"stack": bs.fingerprint(ctx), "params": fingerprint(pl.params(ctx.cfg))})

    def outputs_exist(self, ctx):
        st = _store(ctx)
        return st.exists() and pl.is_done(ctx.cfg, st)

    def run(self, ctx):
        return pl.run(ctx.cfg, _store(ctx), force=True) or {}


class PointEngine(Phase):
    """``ps`` engine or ``ps_lite`` (project method), output ``ps_runs/<track_id>/``."""

    name = "ps"

    def out_dir(self, ctx) -> Path:
        return ctx.project.ps_run(ctx.track_id)

    def fingerprint(self, ctx):
        from geoeyes.processing.ps.params import DEFAULTS
        from geoeyes.processing.ps.runner import ENGINE, UNCHANGED_WITHOUT_WEATHER
        from geoeyes.processing.ps_lite.runner import ENGINE as LITE_VERSION
        c = ctx.cfg
        engine = psp.engine_of(c)
        # ps/3 only changes runs with a weather-model APS: a run with the linear APS is not repeated for it
        PS_VERSION = ENGINE if psp.weather_params(c, ctx.workspace.cache) is not None else UNCHANGED_WITHOUT_WEATHER
        # [ps] merged with the engine defaults: writing a default value explicitly does not change the result;
        # the engine version: a fix that changes the output re-runs the phase
        return sha256_params({"stack": bs.fingerprint(ctx), "engine": engine,
                              "version": LITE_VERSION if engine == "ps_lite" else PS_VERSION,
                              # [ps] (with its defaults) only for the ps engine: a [ps] default change does not
                              # re-run ps_lite
                              "ps": {**DEFAULTS, **c.ps} if engine == "ps" else None,
                              "ps_lite": c.ps_lite.model_dump(mode="json"),
                              "selection": c.selection.model_dump(mode="json"),
                              "atmosphere": c.atmosphere.model_dump(mode="json"),
                              "phase_linking": c.phase_linking.model_dump(mode="json")
                              if c.phase_linking.enabled else None})

    def outputs_exist(self, ctx):
        return (self.out_dir(ctx) / "points.parquet").exists()

    def run(self, ctx):
        return psp.run(ctx.cfg, _store(ctx), self.out_dir(ctx), run_id=ctx.run_id, track_id=ctx.track_id,
                       psrun_id=ctx.track_id, cache_root=ctx.workspace.cache)


def _last_result(ctx, phase: str) -> dict:
    rec = ProjectState(ctx.project).get(ctx.track_id, phase) or {}
    return (rec.get("result") or {}) if rec.get("status") == "done" else {}


class BuildProduct(Phase):
    """Immutable product ``products/<project>_<track>_<first>_<last>_v<N>/`` from the track's PS run."""

    name = "build_product"

    def fingerprint(self, ctx):
        from geoeyes.products.builder import ENGINE
        from geoeyes.products.schema import SCHEMA
        return sha256_params({"ps": PointEngine().fingerprint(ctx), "schema": SCHEMA, "builder": ENGINE})

    def outputs_exist(self, ctx):
        pid = _last_result(ctx, self.name).get("product_id")
        return bool(pid) and (ctx.project.product(pid) / "manifest.json").exists()

    def run(self, ctx):
        from geoeyes.products.builder import build_product
        return build_product(PointEngine().out_dir(ctx), ctx.project.root / "products", project=ctx.cfg.project.name,
                             track_id=ctx.track_id, run_id=ctx.run_id)


class Export(Phase):
    """GIS formats of the latest product (``[export] formats``; GeoPackage styled for QGIS)."""

    name = "export"

    def fingerprint(self, ctx):
        from geoeyes.export.styles import STYLE
        return sha256_params({"product": BuildProduct().fingerprint(ctx),
                              "product_id": _last_result(ctx, "build_product").get("product_id"),
                              "formats": list(ctx.cfg.export.formats), "style": STYLE})

    def outputs_exist(self, ctx):
        pid = _last_result(ctx, "build_product").get("product_id")
        return bool(pid) and any(ctx.project.export(pid).glob("*.qml"))

    def run(self, ctx):
        from geoeyes.export.vector import export_product
        pid = _last_result(ctx, "build_product")["product_id"]
        files = export_product(ctx.project.product(pid), ctx.project.export(pid), formats=ctx.cfg.export.formats)
        return {"product_id": pid, "files": [str(f) for f in files]}


class Report(Phase):
    """Scientific PDF report of the latest product (``products/<id>/report.pdf`` + ``report.json``)."""

    name = "report"

    def fingerprint(self, ctx):
        from geoeyes.core.hashing import sha256_file
        from geoeyes.report.render import TEMPLATE
        return sha256_params({"product": BuildProduct().fingerprint(ctx),
                              "product_id": _last_result(ctx, "build_product").get("product_id"),
                              "template": sha256_file(TEMPLATE)})

    def outputs_exist(self, ctx):
        pid = _last_result(ctx, "build_product").get("product_id")
        return bool(pid) and (ctx.project.product(pid) / "report.pdf").exists()

    def run(self, ctx):
        from geoeyes.report import build_report
        pid = _last_result(ctx, "build_product")["product_id"]
        pdf = build_report(ctx.project.product(pid), copy_to=ctx.cfg.report.copy_to)
        return {"product_id": pid, "report": str(pdf)}


PHASES: tuple[Phase, ...] = (Acquire(), BuildStack(),PhaseLinking(), PointEngine(), BuildProduct(), Export(), Report())
PHASE_NAMES = tuple(p.name for p in PHASES)


@dataclass
class Step:
    phase: Phase
    ctx: PhaseContext
    action: str            # run | up-to-date | disabled | blocked
    reason: str = ""

    @property
    def label(self) -> str:
        return f"{self.ctx.track_id}/{self.phase.name}"


@dataclass
class Plan:
    steps: list[Step] = field(default_factory=list)

    def to_run(self) -> list[Step]:
        return [s for s in self.steps if s.action == "run"]

    def __str__(self) -> str:
        w = max((len(s.label) for s in self.steps), default=10)
        return "\n".join(f"  {s.label:<{w}}  {s.action:<10}  {s.reason}" for s in self.steps)


def _select(names, from_, to, only) -> list[str]:
    for n in [x for x in (from_, to, *(only or ())) if x]:
        if n not in PHASE_NAMES:
            raise PhaseError(n, f"unknown phase (phases: {', '.join(PHASE_NAMES)})")
    if only:
        return [n for n in names if n in only]
    i = names.index(from_) if from_ else 0
    j = names.index(to) + 1 if to else len(names)
    return names[i:j]


def plan(cfg: ProjectConfig, project: ProjectLayout, workspace: WorkspaceLayout, *, tracks=None, from_=None,
         to=None, only=None, force=()) -> Plan:
    """What ``run`` would do; ``force``: phase names run even when up to date."""
    selected = _select(list(PHASE_NAMES), from_, to, only)
    out = Plan()
    for tr in cfg.tracks:
        if tracks and tr.track_id not in tracks:
            continue
        ctx = PhaseContext(cfg, project, workspace, tr)
        rerun = False                                # a phase that runs makes the following ones run too
        for ph in PHASES:
            if ph.name not in selected:
                continue
            if not ph.enabled(ctx):
                out.steps.append(Step(ph, ctx, "disabled", "off in the project configuration"))
                continue
            try:
                why = ph.problem(ctx)
                if why:
                    out.steps.append(Step(ph, ctx, "blocked", why))
                    rerun = True
                    continue
                done = not rerun and ph.name not in force and ph.is_done(ctx)
            except Exception as exc:                 # missing scenes, bad reference date...
                out.steps.append(Step(ph, ctx, "blocked", f"{type(exc).__name__}: {exc}"))
                rerun = True
                continue
            if done:
                out.steps.append(Step(ph, ctx, "up-to-date", "same parameters and inputs, outputs present"))
            else:
                why = ("forced" if ph.name in force else "an earlier phase runs" if rerun else
                       (ph.changes(ctx) if hasattr(ph, "changes") else "") or "not done with these parameters")
                out.steps.append(Step(ph, ctx, "run", why))
                rerun = True
    return out


def run(cfg: ProjectConfig, project: ProjectLayout, workspace: WorkspaceLayout, *, tracks=None, from_=None,
        to=None, only=None, force=(), log_level: str = "INFO") -> dict[str, Any]:
    """Execute the plan; stops at the first failing phase (later phases of that track are skipped)."""
    from geoeyes.core.logging import configure
    from geoeyes.workspace.lock import ProjectLock
    project.ensure()
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    rdir = project.run(run_id)
    configure(log_level, jsonl=rdir / "log.jsonl")
    p = plan(cfg, project, workspace, tracks=tracks, from_=from_, to=to, only=only, force=force)
    blocked = [s for s in p.steps if s.action == "blocked"]
    if blocked:
        raise PhaseError(blocked[0].phase.name, f"{blocked[0].label}: {blocked[0].reason}")
    state = ProjectState(project)
    man = Manifest(kind="run", id=run_id, run_id=run_id, extra={"project": cfg.project.name, "plan": str(p)})
    status = "ok"
    scope = sorted({s.ctx.track_id for s in p.steps}) or None
    with ProjectLock(project.locks, scope=scope), log_context(run_id=run_id):
        log.info("run %s: %d phase(s) to run\n%s", run_id, len(p.to_run()), p)
        failed_tracks: set[str] = set()
        for s in p.to_run():
            if s.ctx.track_id in failed_tracks:
                man.phases.append({"phase": s.phase.name, "track": s.ctx.track_id, "status": "skipped"})
                continue
            s.ctx.run_id = run_id
            t0 = time.time()
            fp = s.phase.fingerprint(s.ctx)
            with log_context(phase=s.phase.name, track=s.ctx.track_id), \
                    file_log(rdir / "logs" / f"{s.phase.name}_{s.ctx.track_id}.log"):
                event(log, "phase_start", f"{s.label}: start")
                state.set(s.ctx.track_id, s.phase.name, status="running", run_id=run_id, fingerprint=fp)
                try:
                    out = s.phase.run(s.ctx)
                except Exception as exc:
                    log.exception("%s failed", s.label)
                    state.set(s.ctx.track_id, s.phase.name, status="failed", run_id=run_id, fingerprint=fp,
                              error=f"{type(exc).__name__}: {exc}")
                    man.phases.append({"phase": s.phase.name, "track": s.ctx.track_id, "status": "failed",
                                       "seconds": round(time.time() - t0, 1), "error": str(exc)})
                    failed_tracks.add(s.ctx.track_id)
                    status = "failed"
                    continue
                state.set(s.ctx.track_id, s.phase.name, status="done", run_id=run_id, fingerprint=fp,
                          seconds=round(time.time() - t0, 1), result=_brief(out))
                man.phases.append({"phase": s.phase.name, "track": s.ctx.track_id, "status": "done",
                                   "seconds": round(time.time() - t0, 1), "result": _brief(out)})
                event(log, "phase_end", f"{s.label}: done in {time.time() - t0:.0f} s")
    man.metrics = {"status": status}
    man.write(rdir)
    if any(p.get("phase") == "build_product" and p.get("status") == "done" for p in man.phases):
        try:                                         # the workspace catalog lists the new product
            from geoeyes.catalog import build_catalog
            build_catalog(workspace)
        except Exception as exc:                 # the run itself succeeded; the catalog can be rebuilt
            log.warning("catalog not updated: %s (geoeyes catalog build)", exc)
    log.info("run %s %s -> %s", run_id, status, rdir)
    return {"run_id": run_id, "status": status, "run_dir": str(rdir), "phases": man.phases}


def _brief(out) -> Any:
    """A JSON-friendly summary of a phase result (the ps summary is already one)."""
    if isinstance(out, dict):
        return {k: v for k, v in out.items() if isinstance(v, (str, int, float, bool, dict, list, type(None)))}
    return str(out)
