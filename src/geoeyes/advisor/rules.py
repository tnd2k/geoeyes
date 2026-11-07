"""Site rules (site advisor, step V2): from a site profile (``advisor.profile``) to a recipe of parameter values,
each with the rule that set it and why, compared with a project's configuration. ``rules.toml`` next to this
module holds the rules; this module only reads and evaluates them (plain comparisons, no language model)."""
from __future__ import annotations

import math
import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

PATH = Path(__file__).with_name("rules.toml")
_COND = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(<=|>=|==|!=|<|>|\bin\b|\bcontains\b)\s*(.+?)\s*$")
OPS = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
       "==": lambda a, b: a == b, "!=": lambda a, b: a != b, "in": lambda a, b: a in b,
       "contains": lambda a, b: b in a}
# keys of project.toml that name the project rather than set how it is processed: never "unexplained"
IDENTITY = {"project.name", "project.description", "aoi.bbox", "acquire.date_range", "acquire.archive",
            "acquire.opendata"}


@dataclass(frozen=True)
class Condition:
    text: str
    metric: str
    op: str
    value: Any


@dataclass(frozen=True)
class Rule:
    id: str
    when: tuple[Condition, ...]
    set: dict[str, Any]
    note: dict[str, str]                 # lang -> text ("" when the rule only sets)
    why: dict[str, str]
    source: str


@dataclass
class Suggestion:
    path: str
    value: Any
    rule: str
    why: dict[str, str]
    replaced: list[tuple[str, Any]] = field(default_factory=list)    # (rule, value) set earlier, overridden


@dataclass
class Advice:
    metrics: dict[str, Any]
    matched: list[str]
    skipped: dict[str, list[str]]        # rule -> metrics the profile has no value for
    recipe: dict[str, Suggestion]
    notes: list[tuple[str, dict[str, str]]]          # (rule, {lang: note})


def parse_condition(text: str) -> Condition:
    m = _COND.match(text)
    if not m:
        raise ValueError(f"condition {text!r}: expected '<metric> <op> <value>'")
    metric, op, raw = m.groups()
    try:
        value = tomllib.loads(f"v = {raw}")["v"]
    except tomllib.TOMLDecodeError:
        value = tomllib.loads(f"v = {raw.replace(chr(39), chr(34))}")["v"]     # 'text' as well as "text"
    return Condition(text, metric, op.strip(), value)


@lru_cache(maxsize=1)
def load() -> tuple[dict[str, list[float]], tuple[Rule, ...]]:
    """(regions {name: bbox}, rules in file order); checks ids and that every parameter is in the catalogue."""
    from geoeyes.advisor import catalog
    raw = tomllib.loads(PATH.read_text(encoding="utf-8"))
    regions = {r["name"]: [float(v) for v in r["bbox"]] for r in raw.get("region", [])}
    rules, seen = [], set()
    cat = catalog.load()
    for r in raw.get("rule", []):
        rid = r["id"]
        if rid in seen:
            raise ValueError(f"{PATH.name}: rule id {rid!r} twice")
        seen.add(rid)
        bad = [p for p in r.get("set", {}) if p not in cat]
        if bad:
            raise ValueError(f"{PATH.name} [{rid}]: not form parameters: {bad}")
        if not r.get("set") and not r.get("note"):
            raise ValueError(f"{PATH.name} [{rid}]: a rule sets something or gives a note")
        rules.append(Rule(rid, tuple(parse_condition(c) for c in r.get("when", [])), dict(r.get("set", {})),
                          {"en": r.get("note", ""), "vi": r.get("note_vi", r.get("note", ""))},
                          {"en": r.get("why", ""), "vi": r.get("why_vi", r.get("why", ""))}, r.get("source", "")))
    return regions, tuple(rules)


def metrics(profile: dict, regions: dict[str, list[float]] | None = None) -> dict[str, Any]:
    """The flat metrics the rules read (names in the header of rules.toml); absent values are left out."""
    if regions is None:
        regions = load()[0]
    out: dict[str, Any] = {}
    t = profile.get("terrain") or {}
    for k in ("relief_m", "slope_median_deg", "steep_share", "very_steep_share"):
        out[f"terrain.{k}"] = t.get(k)
    lc = profile.get("land_cover") or {}
    shares = lc.get("shares") or {}
    for k, v in shares.items():
        out[f"land_cover.{k}"] = v
    if shares:
        out["land_cover.vegetation"] = round(sum(shares.get(k) or 0.0 for k in ("tree", "crop", "grass", "wetland")),
                                             3)
        out["land_cover.dominant"] = lc.get("dominant")
    g = profile.get("geology") or {}
    out["geology.soft_share"], out["geology.dominant"] = g.get("soft_share"), g.get("dominant")
    c = profile.get("climate") or {}
    out["climate.koppen"] = c.get("koppen")
    out["climate.zone"] = c["koppen"][0] if c.get("koppen") else None
    out["climate.rain_annual_mm"], out["climate.rh_mean_pct"] = c.get("rain_annual_mm"), c.get("rh_mean_pct")
    tracks = [d for d in ((profile.get("data") or {}).get("tracks") or {}).values() if "dates" in d]
    if tracks:
        d = max(tracks, key=lambda x: x["dates"])
        for k in ("sensor", "band", "dates", "span_years", "revisit_median_days", "max_gap_days", "coherence_median",
                  "bperp_spread_m"):
            out[f"data.{k}"] = d.get(k)
        if d.get("warning"):                                       # a QC value known to be wrong is not used
            out["data.coherence_median"] = None
    out["site.area_km2"] = profile.get("area_km2")
    lon, lat = profile.get("centre") or (None, None)
    out["site.regions"] = [n for n, (w, s, e, nn) in regions.items()
                           if lon is not None and w <= lon <= e and s <= lat <= nn]
    return {k: v for k, v in out.items() if v is not None}


def evaluate(profile: dict) -> Advice:
    regions, rules = load()
    m = metrics(profile, regions)
    matched, skipped, recipe, notes = [], {}, {}, []
    for r in rules:
        missing = [c.metric for c in r.when if c.metric not in m]
        if missing:
            skipped[r.id] = missing
            continue
        try:
            ok = all(OPS[c.op](m[c.metric], c.value) for c in r.when)
        except TypeError:                                          # e.g. a number compared with a word
            ok = False
        if not ok:
            continue
        matched.append(r.id)
        for path, value in r.set.items():
            old = recipe.get(path)
            s = Suggestion(path, value, r.id, r.why)
            if old is not None:
                s.replaced = [*old.replaced, (old.rule, old.value)]
            recipe[path] = s
        if r.note["en"]:
            notes.append((r.id, r.note))
    return Advice(m, matched, skipped, recipe, notes)


# ---------------------------------------------------------------- against a project
def _norm(v: Any) -> Any:
    if hasattr(v, "value"):
        v = v.value
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    return str(v).strip().lower()


def same(a: Any, b: Any) -> bool:
    a, b = _norm(a), _norm(b)
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    return a == b


def compare(advice: Advice, cfg, raw: dict) -> dict:
    """``changes`` (the recipe differs from the effective value), ``agree`` (it already holds), ``unexplained``
    (values written in project.toml that no rule sets: project-specific choices, or rules still to write)."""
    from geoeyes.api.settings import _get, _json
    changes, agree = [], []
    for path, s in advice.recipe.items():
        section, key = path.split(".", 1)
        try:
            current = _json(_get(cfg, section, key))
        except AttributeError:
            current = None
        own = key in (raw.get(section) or {})
        row = {"path": path, "current": current, "suggested": s.value, "rule": s.rule, "own": own}
        (agree if same(current, s.value) else changes).append(row)
    unexplained = []
    for section, table in raw.items():
        if not isinstance(table, dict):
            continue
        for key, value in table.items():
            path = f"{section}.{key}"
            if path in IDENTITY or path in advice.recipe or isinstance(value, dict):
                continue
            unexplained.append({"path": path, "value": _json(value)})
    return {"changes": changes, "agree": agree, "unexplained": unexplained}


def report(advice: Advice, cmp: dict | None = None, lang: str = "en") -> str:
    vi = lang == "vi"
    L = (lambda en, v: v if vi else en)                            # noqa: E731
    _, rules = load()
    by_id = {r.id: r for r in rules}
    out = [L("Rules that apply: ", "Luật áp dụng: ") + (", ".join(advice.matched) or "-")]
    if advice.skipped:
        out.append(L("Not evaluated (no value in the profile): ", "Không đánh giá (hồ sơ thiếu giá trị): ")
                   + "; ".join(f"{k} ({', '.join(v)})" for k, v in advice.skipped.items()))
    out.append("")
    if cmp is None:
        out.append(L("Recipe:", "Công thức:"))
        for s in advice.recipe.values():
            out.append(f"  {s.path} = {s.value!r}   [{s.rule}]")
    else:
        out.append(L("To change:", "Cần đổi:") if cmp["changes"] else L("To change: none", "Cần đổi: không có"))
        for r in cmp["changes"]:
            out.append(f"  {r['path']}: {r['current']!r} -> {r['suggested']!r}   [{r['rule']}]")
        if cmp["agree"]:
            out.append(L("Already as the rules say:", "Đã đúng như luật:"))
            for r in cmp["agree"]:
                out.append(f"  {r['path']} = {r['suggested']!r}   [{r['rule']}]")
        if cmp["unexplained"]:
            out.append(L("Set in project.toml, no rule (project-specific, or a rule to write):",
                         "Đặt trong project.toml nhưng không có luật (riêng của dự án, hoặc cần viết luật):"))
            for r in cmp["unexplained"]:
                out.append(f"  {r['path']} = {r['value']!r}")
    for path, s in advice.recipe.items():
        for rid, v in s.replaced:
            out.append(L(f"  ({path}: {rid} said {v!r}, {s.rule} wins)",
                         f"  ({path}: {rid} đặt {v!r}, {s.rule} thắng)"))
    out.append("")
    out.append(L("Why:", "Vì sao:"))
    for rid in advice.matched:
        r = by_id[rid]
        out.append(f"  [{rid}] {r.why[lang]}")
        if r.source:
            out.append(f"      {L('source', 'nguồn')}: {r.source}")
    if advice.notes:
        out.append("")
        out.append(L("Notes:", "Ghi chú:"))
        for rid, note in advice.notes:
            out.append(f"  [{rid}] {note[lang]}")
    return "\n".join(out)
