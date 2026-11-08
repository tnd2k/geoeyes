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
from geoeyes.core.errors import PhaseError, PhasePaused
from geoeyes.core.hashing import sha256_params
from geoeyes.core.logging import event, file_log, log_context
from geoeyes.io.manifest import Manifest
from geoeyes.workspace import ProjectLayout, WorkspaceLayout

log = logging.getLogger(__name__)

MIN_FREE_GB = 5.0           # floor of free disk before a phase starts; GEOEYES_MIN_FREE_GB overrides it (0: off)


def check_disk(path, phase: str) -> float:
    """Free space (GB) on the disk of ``path``; a phase is refused below the floor, before it writes anything (a
    full disk in the middle of a run broke the run and its logs on 2026-11-03)."""
    import os
    import shutil
    need = float(os.environ.get("GEOEYES_MIN_FREE_GB", MIN_FREE_GB))
    free = shutil.disk_usage(path).free / 1e9
    if free < need:
        raise PhaseError(phase, f"{free:.1f} GB free on the disk of {path}, at least {need:g} GB needed: free space "
                                "first (GEOEYES_MIN_FREE_GB sets the floor)")
    log.info("disk: %.1f GB free", free)
    return free


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
        out = acq.run(ctx)
        # the plan listed the scenes of the archive before the download: build_stack lists them again (new dates)
        ctx.cache.pop("stack", None)
        return out


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
    """``ps`` engine, ``ps_lite`` or ``sbas`` (project method), output ``ps_runs/<track_id>/``."""

    name = "ps"

    def out_dir(self, ctx) -> Path:
        return ctx.project.ps_run(ctx.track_id)

    def fingerprint(self, ctx):
        return sha256_params({"stack": bs.fingerprint(ctx), **self._settings(ctx)})

    def config_fingerprint(self, ctx) -> str:
        """The fingerprint without the stack's scenes (its reference only): equal when only new dates came."""
        return sha256_params({"stack": bs.target(ctx)["stack_id"], **self._settings(ctx)})

    def _settings(self, ctx) -> dict:
        from geoeyes.processing.ps.params import DEFAULTS
        from geoeyes.processing.ps.runner import ENGINE, UNCHANGED_WITHOUT_WEATHER
        from geoeyes.processing.ps_lite.runner import ENGINE as LITE_VERSION
        c = ctx.cfg
        engine = psp.engine_of(c)
        # ps/3 only changes runs with a weather-model APS: a run with the linear APS is not repeated for it
        PS_VERSION = ENGINE if psp.weather_params(c, ctx.workspace.cache) is not None else UNCHANGED_WITHOUT_WEATHER
        # [ps] merged with the engine defaults: writing a default value explicitly does not change the result;
        # the engine version: a fix that changes the output re-runs the phase
        if engine == "sbas":                    # its own keys only: the fingerprints of ps / ps_lite runs unchanged
            from geoeyes.processing.sbas.runner import ENGINE as SBAS_VERSION
            return {"engine": engine, "version": SBAS_VERSION, "sbas": c.sbas.model_dump(mode="json"),
                    "network": c.network.model_dump(mode="json"),
                    "phase_linking": c.phase_linking.model_dump(mode="json") if c.phase_linking.enabled else None}
        return {"engine": engine, "version": LITE_VERSION if engine == "ps_lite" else PS_VERSION,
                # [ps] (with its defaults) only for the ps engine: a [ps] default change does not re-run ps_lite
                "ps": {**DEFAULTS, **c.ps} if engine == "ps" else None,
                "ps_lite": c.ps_lite.model_dump(mode="json"),
                "selection": c.selection.model_dump(mode="json"),
                "atmosphere": c.atmosphere.model_dump(mode="json"),
                "phase_linking": c.phase_linking.model_dump(mode="json") if c.phase_linking.enabled else None}

    def outputs_exist(self, ctx):
        return (self.out_dir(ctx) / "points.parquet").exists()

    def update_plan(self, ctx, store=None) -> tuple[list[str], str]:
        """(dates an incremental update would add, '') or ([], why a full run)."""
        from geoeyes.processing.ps import update as pu
        c = ctx.cfg
        if not c.ps_update.enabled:
            return [], "incremental updates off ([ps_update] enabled = false)"
        if psp.engine_of(c) != "ps" or c.phase_linking.enabled:
            return [], "incremental updates need the ps engine without phase linking"
        if "ps" in ctx.cache.get("forced", ()):
            return [], "forced"
        return pu.plan(self.out_dir(ctx), store or _store(ctx), self.config_fingerprint(ctx), c.ps_update.full_every)

    def note(self, ctx) -> str:
        """For the plan: whether the run will be an incremental update (from the scenes, before the stack is
        extended)."""
        import h5py

        from geoeyes.io.manifest import Manifest
        c = ctx.cfg
        run = self.out_dir(ctx)
        if not c.ps_update.enabled or psp.engine_of(c) != "ps" or c.phase_linking.enabled or \
                "ps" in ctx.cache.get("forced", ()) or not (run / "state.h5").exists():
            return ""
        try:
            pm = Manifest.read(run)
            if (pm.extra or {}).get("config_fingerprint") != self.config_fingerprint(ctx):
                return ""
            with h5py.File(run / "state.h5", "r") as f:
                old = [d.decode() for d in f["time/epoch_dates"][()]]
        except Exception:                            # an old or partial run: the plan says nothing
            return ""
        now = [str(d) for d in bs.target(ctx)["scenes"]]
        new = sorted(set(now) - set(old))
        done = int((pm.metrics.get("update") or {}).get("dates_since_full", 0))
        if not new or not set(old) <= set(now) or new[0] < old[-1] or done + len(new) > c.ps_update.full_every:
            return ""
        return f"incremental update: {len(new)} new date(s)"

    def run(self, ctx):
        from geoeyes.processing.ps import update as pu
        from geoeyes.processing.ps.params import DEFAULTS
        store = _store(ctx)
        new, why = self.update_plan(ctx, store)
        if new:
            log.info("incremental update: %d new date(s) %s added to the previous run", len(new), ", ".join(new))
            return pu.update(store, self.out_dir(ctx), new, weather=psp.weather_params(ctx.cfg, ctx.workspace.cache),
                             grid_size=float({**DEFAULTS, **ctx.cfg.ps}["unwrap_grid_size"]), run_id=ctx.run_id,
                             track_id=ctx.track_id, config_fingerprint=self.config_fingerprint(ctx))
        log.info("full ps run: %s", why)
        ps_from, ps_to = ctx.cache.get("ps_steps", (None, None))
        out = psp.run(ctx.cfg, store, self.out_dir(ctx), run_id=ctx.run_id, track_id=ctx.track_id,
                      psrun_id=ctx.track_id, cache_root=ctx.workspace.cache, from_step=ps_from, stop_after=ps_to)
        if psp.engine_of(ctx.cfg) == "ps":
            pu.mark_full(self.out_dir(ctx), store, self.config_fingerprint(ctx))
        return out


def _last_result(ctx, phase: str) -> dict:
    rec = ProjectState(ctx.project).get(ctx.track_id, phase) or {}
    return (rec.get("result") or {}) if rec.get("status") == "done" else {}


class BuildProduct(Phase):
    """Immutable product ``products/<project>_<track>_<first>_<last>_v<N>/`` from the track's PS run."""

    name = "build_product"

    def fingerprint(self, ctx):
        from geoeyes.products.builder import ENGINE
        from geoeyes.products.schema import SCHEMA
        return sha256_params({"ps": PointEngine().fingerprint(ctx), "schema": SCHEMA, "builder": ENGINE,
                              "product": ctx.cfg.product.model_dump()})

    def outputs_exist(self, ctx):
        pid = _last_result(ctx, self.name).get("product_id")
        return bool(pid) and (ctx.project.product(pid) / "manifest.json").exists()

    def run(self, ctx):
        from geoeyes.products.builder import build_product
        from geoeyes.products.spatial_filter import SpatialFilter
        pc = ctx.cfg.product
        spatial = SpatialFilter(enabled=pc.spatial_filter, radius_m=pc.spatial_filter_radius_m, k=pc.spatial_filter_k,
                                min_neighbours=pc.spatial_filter_min_neighbours, dv_min=pc.spatial_filter_dv_min,
                                z=pc.spatial_filter_z)
        return build_product(PointEngine().out_dir(ctx), ctx.project.root / "products", project=ctx.cfg.project.name,
                             track_id=ctx.track_id, run_id=ctx.run_id, spatial=spatial)


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
    action: str            # run | up-to-date | disabled | skipped | blocked
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


def _skipped(skip, track_id: str, phase: str) -> bool:
    """``skip`` entries: a phase name (every track) or ``track/phase``."""
    return phase in skip or f"{track_id}/{phase}" in skip


def plan(cfg: ProjectConfig, project: ProjectLayout, workspace: WorkspaceLayout, *, tracks=None, from_=None,
         to=None, only=None, force=(), skip=(), ps_from: int | None = None, ps_to: int | None = None) -> Plan:
    """What ``run`` would do; ``force``: phase names run even when up to date; ``skip``: phases (``phase`` or
    ``track/phase``) left as they are, not even checked (no data-server search for a skipped acquire), and
    their state does not make the following phases run. ``ps_from`` / ``ps_to``: the steps of the ps engine
    computed again from / stopped after (``ps_from`` makes the ps phase run)."""
    selected = _select(list(PHASE_NAMES), from_, to, only)
    if ps_from:
        force = (*force, "ps")
    for s in skip:
        if s.rsplit("/", 1)[-1] not in PHASE_NAMES:
            raise PhaseError(s, f"unknown phase (phases: {', '.join(PHASE_NAMES)})")
    out = Plan()
    for tr in cfg.tracks:
        if tracks and tr.track_id not in tracks:
            continue
        ctx = PhaseContext(cfg, project, workspace, tr)
        ctx.cache["ps_steps"] = (ps_from, ps_to)
        rerun = False                               # a phase that runs makes the following ones run too
        for ph in PHASES:
            if ph.name not in selected:
                continue
            if _skipped(skip, tr.track_id, ph.name):
                out.steps.append(Step(ph, ctx, "skipped", "skipped for this run"))
                continue
            if not ph.enabled(ctx):
                out.steps.append(Step(ph, ctx, "disabled", "off in the project configuration"))
                continue
            # scenes the acquire phase of this track downloads first: a phase that has none yet waits for it
            acquiring = any(s.ctx is ctx and s.phase.name == "acquire" and s.action == "run" for s in out.steps)
            try:
                why = ph.problem(ctx)
                if why:
                    out.steps.append(Step(ph, ctx, "run" if acquiring else "blocked",
                                          f"after acquire ({why})" if acquiring else why))
                    rerun = True
                    continue
                done = not rerun and ph.name not in force and ph.is_done(ctx)
            except Exception as exc:                 # missing scenes, bad reference date...
                msg = f"{type(exc).__name__}: {exc}"
                out.steps.append(Step(ph, ctx, "run" if acquiring else "blocked",
                                      f"after acquire ({msg})" if acquiring else msg))
                rerun = True
                continue
            if ph.name in force:
                ctx.cache.setdefault("forced", set()).add(ph.name)
            if done:
                out.steps.append(Step(ph, ctx, "up-to-date", "same parameters and inputs, outputs present"))
            else:
                why = ("forced" if ph.name in force else "an earlier phase runs" if rerun else
                       (ph.changes(ctx) if hasattr(ph, "changes") else "") or "not done with these parameters")
                note = ph.note(ctx) if hasattr(ph, "note") else ""
                why = f"{why}; {note}" if note else why
                out.steps.append(Step(ph, ctx, "run", why))
                rerun = True
    return out


def run(cfg: ProjectConfig, project: ProjectLayout, workspace: WorkspaceLayout, *, tracks=None, from_=None,
        to=None, only=None, force=(), skip=(), ps_from: int | None = None, ps_to: int | None = None,
        log_level: str = "INFO") -> dict[str, Any]:
    """Execute the plan; stops at the first failing phase (later phases of that track are skipped)."""
    from geoeyes.core.logging import configure
    from geoeyes.workspace.lock import ProjectLock, check_free
    project.ensure()
    # another run on these tracks: refused before this run makes its folder (the web page shows the newest one)
    check_free(project.locks, [t.track_id for t in cfg.tracks if not tracks or t.track_id in tracks] or None)
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    rdir = project.run(run_id)
    configure(log_level, jsonl=rdir / "log.jsonl")
    from geoeyes.core import netrate
    netrate.watch(project.state_dir / "net.json")
    log.info("run %s: checking what has to run (new scenes on the data servers, changed parameters)...", run_id)
    try:
        p = plan(cfg, project, workspace, tracks=tracks, from_=from_, to=to, only=only, force=force, skip=skip,
                 ps_from=ps_from, ps_to=ps_to)
    except Exception as exc:                         # in the run log (the web page shows it), not only on stderr
        log.exception("run %s: planning failed (%s: %s)", run_id, type(exc).__name__, exc)
        Manifest(kind="run", id=run_id, run_id=run_id, extra={"project": cfg.project.name, "error": str(exc)},
                 metrics={"status": "failed"}).write(rdir)
        raise
    blocked = [s for s in p.steps if s.action == "blocked"]
    if blocked:
        raise PhaseError(blocked[0].phase.name, f"{blocked[0].label}: {blocked[0].reason}")
    state = ProjectState(project)
    man = Manifest(kind="run", id=run_id, run_id=run_id, extra={"project": cfg.project.name, "plan": str(p)})
    status = "ok"
    scope = sorted({s.ctx.track_id for s in p.steps}) or None
    from geoeyes.core import compute
    backend = compute.resolve(cfg.compute.backend)    # "cupy" without a usable GPU fails here, before any phase
    man.extra["compute"] = backend.describe()
    with ProjectLock(project.locks, scope=scope, info={"run_id": run_id}), log_context(run_id=run_id), \
            compute.use(backend):
        log.info("run %s: %d phase(s) to run, compute on %s\n%s", run_id, len(p.to_run()), backend.describe(), p)
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
                    check_disk(project.root, s.phase.name)
                    out = s.phase.run(s.ctx)
                except PhasePaused as exc:               # stopped after a step as asked: resumed by the next run
                    log.info("%s", exc)
                    state.set(s.ctx.track_id, s.phase.name, status="paused", run_id=run_id, fingerprint=fp,
                              step=exc.step, error=str(exc))
                    man.phases.append({"phase": s.phase.name, "track": s.ctx.track_id, "status": "paused",
                                       "seconds": round(time.time() - t0, 1), "step": exc.step})
                    failed_tracks.add(s.ctx.track_id)    # the following phases need its output
                    event(log, "phase_end", f"{s.label}: paused after step {exc.step}")
                    continue
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
