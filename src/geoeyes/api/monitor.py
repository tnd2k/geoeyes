"""Monitoring helpers of the web app: next Sentinel-1 acquisitions of a track, a scheduled ``geoeyes run`` (Windows
Task Scheduler), and deformation alerts evaluated on the latest product.

Alert rules live in ``project.toml``::

    [postprocess.alerts]
    rules = [
      { name = "subsidence > 20 mm/yr", kind = "velocity_below", threshold = -20.0, min_points = 20 },
      { name = "airport uplift", kind = "velocity_above", threshold = 10.0, bbox = [105.80, 21.20, 105.82, 21.22] },
    ]
"""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import tomlkit

from geoeyes.config.loader import load
from geoeyes.config.schema import Sensor
from geoeyes.core.errors import ConfigError
from geoeyes.workspace import ProjectLayout, WorkspaceLayout

REPEAT_DAYS = 12                 # Sentinel-1 repeat cycle of one satellite
ACTIVE_DAYS = 60                 # a satellite not seen for longer is not forecast
_SCENE_RE = re.compile(r"^(S1[A-D])_IW_SLC__\w{4}_(\d{8})T")


# ---------------------------------------------------------------- next acquisitions
def next_acquisitions(ws: WorkspaceLayout, name: str, today: date | None = None, count: int = 4,
                      with_plan: bool = True) -> list[dict]:
    """Per Sentinel-1 track: the last acquisition of each satellite in the archive + 12-day steps, checked against
    ESA's acquisition plan (planned / not planned within the published period)."""
    cfg = load(ws.project(name).config)
    today = today or date.today()
    out = []
    for tr in cfg.tracks:
        if tr.sensor is not Sensor.SENTINEL1:
            continue
        root = Path(cfg.acquire.archive) if cfg.acquire.archive else ws.archive / "sentinel1" / tr.track_id
        last: dict[str, date] = {}
        for p in root.glob("*/*") if root.exists() else []:
            m = _SCENE_RE.match(p.name)
            if m:
                d = datetime.strptime(m.group(2), "%Y%m%d").date()
                last[m.group(1)] = max(last.get(m.group(1), d), d)
        nxt = []
        for sat, d in last.items():
            if (today - d).days > ACTIVE_DAYS:
                continue
            k = max(1, -(-(today - d).days // REPEAT_DAYS))
            nxt += [(d + timedelta(days=REPEAT_DAYS * (k + i)), sat) for i in range(count)]
        nxt = sorted(x for x in nxt if x[0] >= today)[:count]
        entry = {"track": tr.track_id, "last": {s: d.isoformat() for s, d in sorted(last.items())},
                 "next": [{"date": d.isoformat(), "platform": s, "status": "predicted"} for d, s in nxt],
                 "plan_until": {}, "note": ""}
        if cfg.aoi.bbox and with_plan:
            _confirm_with_plan(entry, ws, list(cfg.aoi.bbox), tr.relative_orbit, today)
        out.append(entry)
    return out


def _confirm_with_plan(entry: dict, ws: WorkspaceLayout, bbox: list[float], relative_orbit: int | None,
                       today: date) -> None:
    """Mark each predicted pass planned / not planned from ESA's acquisition plan; add planned-only passes."""
    from datetime import UTC
    from datetime import datetime as dt

    from geoeyes.sensors.sentinel1.plan import planned
    try:
        takes, until = planned(ws.cache_dir("s1plan"), bbox, relative_orbit=relative_orbit,
                               start=dt.combine(today, dt.min.time(), UTC))
    except Exception as exc:                 # the plan is a refinement; without it the forecast stays
        entry["note"] = f"ESA acquisition plan unavailable ({exc}); repeat-cycle forecast only"
        return
    entry["plan_until"] = {s: t.date().isoformat() for s, t in until.items()}
    by_key = {(t.platform, t.start.date()): t for t in takes}
    used = set()
    for n in entry["next"]:
        d = date.fromisoformat(n["date"])
        hit = by_key.get((n["platform"], d)) or by_key.get((n["platform"], d + timedelta(days=1)))
        if hit:
            used.add((hit.platform, hit.start.date()))
            n.update(status="planned", time=hit.start.strftime("%H:%M UTC"), mode=hit.mode,
                     polarisation=hit.polarisation)
        elif n["platform"] in until and d <= until[n["platform"]].date():
            n["status"] = "not planned"
    for t in takes:
        if (t.platform, t.start.date()) not in used:
            entry["next"].append({"date": t.start.date().isoformat(), "platform": t.platform, "status": "planned",
                                  "time": t.start.strftime("%H:%M UTC"), "mode": t.mode,
                                  "polarisation": t.polarisation})
    entry["next"].sort(key=lambda n: n["date"])


# ---------------------------------------------------------------- schedule (Windows Task Scheduler)
def _task(name: str) -> str:
    return f"GeoEyes\\{name}"


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, creationflags=0x08000000)


def get_schedule(name: str) -> dict:
    if sys.platform != "win32":
        return {"supported": False}
    r = _schtasks("/Query", "/TN", _task(name), "/FO", "LIST", "/V")
    if r.returncode != 0:
        return {"supported": True, "enabled": False}
    info = {}
    for line in r.stdout.splitlines():
        k, sep, v = line.partition(":")
        if sep:
            info.setdefault(k.strip(), v.strip())
    return {"supported": True, "enabled": True, "next_run": info.get("Next Run Time"),
            "last_run": info.get("Last Run Time"), "last_result": info.get("Last Result"),
            "schedule": info.get("Schedule Type"), "time": info.get("Start Time"), "days": info.get("Days"),
            "status": info.get("Status")}


def set_schedule(ws: WorkspaceLayout, name: str, frequency: str, at: str = "02:00", day: str = "MON") -> dict:
    """``frequency``: daily | weekly | off. The task runs ``geoeyes run <project>`` while the user is logged on."""
    if sys.platform != "win32":
        raise ConfigError("scheduled runs are only set up from the web app on Windows (use cron elsewhere)")
    ws.project(name)
    if frequency == "off":
        _schtasks("/Delete", "/TN", _task(name), "/F")
        return get_schedule(name)
    if frequency not in ("daily", "weekly") or not re.fullmatch(r"[0-2]\d:[0-5]\d", at):
        raise ConfigError("frequency daily | weekly | off, time HH:MM")
    if day not in ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"):
        raise ConfigError("day: MON..SUN")
    cmd = f'"{sys.executable}" -m geoeyes.cli.main --workspace "{ws.root}" run {name}'
    args = ["/Create", "/TN", _task(name), "/TR", cmd, "/SC", frequency.upper(), "/ST", at, "/F"]
    if frequency == "weekly":
        args += ["/D", day]
    r = _schtasks(*args)
    if r.returncode != 0:
        raise ConfigError(f"Task Scheduler: {(r.stderr or r.stdout).strip()}")
    return get_schedule(name)


# ---------------------------------------------------------------- alerts
KINDS = ("velocity_below", "velocity_above")


def rules(project: ProjectLayout) -> list[dict]:
    return list(dict(load(project.config).postprocess.alerts).get("rules", []))


def check_rules(raw: list) -> list[dict]:
    out = []
    for r in raw:
        name = str(r.get("name", "")).strip()
        kind = r.get("kind")
        if not name or kind not in KINDS:
            raise ConfigError(f"alert rule {r!r}: name and kind ({', '.join(KINDS)}) are required")
        rule = {"name": name, "kind": kind, "threshold": float(r["threshold"]),
                "min_points": int(r.get("min_points") or 10)}
        if r.get("bbox"):
            b = [float(v) for v in r["bbox"]]
            if len(b) != 4 or b[0] >= b[2] or b[1] >= b[3]:
                raise ConfigError(f"alert rule {name!r}: bbox = [west, south, east, north]")
            rule["bbox"] = b
        out.append(rule)
    return out


def save_rules(project: ProjectLayout, raw: list) -> list[dict]:
    from geoeyes.api.settings import _write
    clean = check_rules(raw)
    doc = tomlkit.parse(project.config.read_text(encoding="utf-8"))
    if "postprocess" not in doc:
        doc.add(tomlkit.nl())
        doc["postprocess"] = tomlkit.table()
    alerts = doc["postprocess"].get("alerts")
    if alerts is None:
        alerts = tomlkit.table()
        doc["postprocess"]["alerts"] = alerts
    arr = tomlkit.array()
    arr.multiline(True)
    for r in clean:
        t = tomlkit.inline_table()
        t.update(r)
        arr.append(t)
    alerts["rules"] = arr
    _write(project, tomlkit.dumps(doc))
    tomllib.loads(project.config.read_text(encoding="utf-8"))
    return clean


def evaluate(project: ProjectLayout, product: Path, cache_root: Path,
             rule_list: list[dict] | None = None) -> list[dict]:
    """Each rule on a product: points beyond the threshold (inside the bbox), triggered when at least
    ``min_points``; their centroid and the most extreme velocity."""
    from geoeyes.api import points
    rule_list = rules(project) if rule_list is None else rule_list
    if not rule_list:
        return []
    attrs = points._arrays(str(points.ensure(product, cache_root)))[0]
    lon, lat, vel = attrs["lon"], attrs["lat"], attrs["vel"].astype(np.float64)
    out = []
    for r in rule_list:
        m = np.isfinite(vel)
        if r.get("bbox"):
            w, s, e, n = r["bbox"]
            m &= (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
        hit = m & ((vel <= r["threshold"]) if r["kind"] == "velocity_below" else (vel >= r["threshold"]))
        k = int(hit.sum())
        res = {**r, "product": product.name, "n": k, "of": int(m.sum()), "triggered": k >= r["min_points"]}
        if k:
            res.update({"worst": round(float(vel[hit].min() if r["kind"] == "velocity_below" else vel[hit].max()), 2),
                        "lon": round(float(np.mean(lon[hit])), 5), "lat": round(float(np.mean(lat[hit])), 5)})
        out.append(res)
    return out
