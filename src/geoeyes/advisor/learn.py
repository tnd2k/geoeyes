"""Rules against the projects (site advisor, step V4): run the advisor on every project of the workspace and report
where the rules agree with what was actually used, where they differ, which values recur without a rule (candidate
rules) and which rules never apply. A finished project (one with a product) is the owner's reviewed choice and
counts as evidence; a project still in progress is listed but not counted. Nothing is fitted: the report is read
and the rules are edited by hand (too few projects for any statistics)."""
from __future__ import annotations

import json
import logging
import tomllib
from collections import defaultdict
from datetime import date

log = logging.getLogger(__name__)


def collect(ws, progress=None) -> list[dict]:
    """Per project: name, finished, metrics, matched rules, comparison; a project that cannot be read is kept with
    its error."""
    from geoeyes.advisor import rules
    from geoeyes.advisor.profile import profile
    from geoeyes.config.loader import load
    say = progress or log.info
    out = []
    for cfg_file in sorted(ws.projects.glob("*/project.toml")):
        name = cfg_file.parent.name
        project = ws.project(name)
        say(f"advisor learn: {name}")
        row = {"project": name, "finished": any((project.root / "products").glob("*/manifest.json"))}
        try:
            cfg = load(project.config)
            if not (cfg.aoi and cfg.aoi.bbox):
                raise ValueError("no [aoi] bbox")
            raw = tomllib.loads(project.config.read_text(encoding="utf-8"))
            p = profile(list(cfg.aoi.bbox), cache_root=ws.cache, dem=str(cfg.stack.dem or "srtm-1"),
                        project=project, cfg=cfg)
            a = rules.evaluate(p)
            row.update({"metrics": a.metrics, "matched": a.matched, "skipped": a.skipped,
                        "compare": rules.compare(a, cfg, raw), "profile_errors": p.get("errors", {})})
        except Exception as exc:                                    # one project never stops the rest
            row["error"] = f"{type(exc).__name__}: {exc}"
        out.append(row)
    return out


def summarise(rows: list[dict]) -> dict:
    from geoeyes.advisor import rules
    _, rs = rules.load()
    per_rule = {r.id: {"fired": [], "agree": 0, "differ": 0, "sets": bool(r.set)} for r in rs}
    differ, recurring = [], defaultdict(list)
    for row in rows:
        if "error" in row:
            continue
        for rid in row["matched"]:
            per_rule[rid]["fired"].append(row["project"])
        if not row["finished"]:
            continue
        cmp = row["compare"]
        for r in cmp["agree"]:
            per_rule[r["rule"]]["agree"] += 1
        for r in cmp["changes"]:
            per_rule[r["rule"]]["differ"] += 1
            differ.append({"project": row["project"], **r})
        for u in cmp["unexplained"]:
            recurring[(u["path"], json.dumps(u["value"]))].append(row["project"])
    candidates = [{"path": p, "value": json.loads(v), "projects": ps} for (p, v), ps in recurring.items()
                  if len(ps) >= 2]
    return {"per_rule": per_rule, "differ": differ, "candidates": candidates,
            "never": [rid for rid, x in per_rule.items() if not x["fired"]]}


def report(rows: list[dict], lang: str = "en") -> str:
    vi = lang == "vi"
    L = (lambda en, v: v if vi else en)                            # noqa: E731
    s = summarise(rows)
    n_done = sum(1 for r in rows if r["finished"] and "error" not in r)
    out = [L(f"# Site rules against the projects ({date.today()})",
             f"# Luật khu vực so với các dự án ({date.today()})"),
           "",
           L(f"{len(rows)} project(s), {n_done} finished (with a product): only finished projects count as evidence.",
             f"{len(rows)} dự án, {n_done} đã xong (có sản phẩm): chỉ dự án đã xong mới được tính là bằng chứng."),
           "", L("## Projects", "## Các dự án"), "",
           L("| project | finished | rules that apply | changes suggested |",
             "| dự án | đã xong | luật áp dụng | đề xuất đổi |"), "|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            out.append(f"| {r['project']} | {'✓' if r['finished'] else ''} | ! {r['error']} | |")
            continue
        ch = ", ".join(f"`{c['path']}` {c['current']!r}→{c['suggested']!r}" for c in r["compare"]["changes"]) or "—"
        out.append(f"| {r['project']} | {'✓' if r['finished'] else ''} | {', '.join(r['matched']) or '—'} | {ch} |")
    out += ["", L("## Rules", "## Các luật"), "",
            L("| rule | applies to | values kept in finished projects | values changed by the owner |",
              "| luật | áp dụng cho | giá trị dự án đã xong giữ đúng | giá trị chủ dự án đã đặt khác |"),
            "|---|---|---|---|"]
    for rid, x in s["per_rule"].items():
        kept = str(x["agree"]) if x["sets"] else L("(note only)", "(chỉ ghi chú)")
        out.append(f"| {rid} | {', '.join(x['fired']) or '—'} | {kept} | {x['differ'] if x['sets'] else ''} |")
    out += ["", L("## Where a finished project differs from a rule", "## Chỗ dự án đã xong khác với luật"), ""]
    if s["differ"]:
        for d in s["differ"]:
            out.append(L(f"- {d['project']}: `{d['path']}` = {d['current']!r}, rule [{d['rule']}] says "
                         f"{d['suggested']!r}: fix the rule, or the project",
                         f"- {d['project']}: `{d['path']}` = {d['current']!r}, luật [{d['rule']}] nói "
                         f"{d['suggested']!r}: sửa luật, hoặc sửa dự án"))
    else:
        out.append(L("None: every finished project is as the rules say.",
                     "Không có: mọi dự án đã xong đều đúng như luật."))
    ign = [(r["project"], i) for r in rows if "error" not in r for i in r["compare"].get("ignored", [])]
    out += ["", L("## [ps] keys the engine does not read (silently ignored)",
                  "## Khoá [ps] mà engine không đọc (bị bỏ qua không báo)"), ""]
    if ign:
        for proj, i in ign:
            hint = (L(f" (did you mean `{i['did_you_mean']}`?)", f" (có phải ý là `{i['did_you_mean']}`?)")
                    if i["did_you_mean"] else "")
            out.append(f"- {proj}: `[ps] {i['path'][3:]}` = {i['value']!r}{hint}")
    else:
        out.append(L("None.", "Không có."))
    out += ["", L("## Values set in two or more finished projects without a rule (candidate rules)",
                  "## Giá trị đặt ở từ hai dự án đã xong trở lên mà chưa có luật (ứng viên luật mới)"), ""]
    if s["candidates"]:
        for c in s["candidates"]:
            out.append(f"- `{c['path']}` = {c['value']!r}: {', '.join(c['projects'])}")
    else:
        out.append(L("None.", "Không có."))
    out += ["", L("## Rules that apply to no project yet", "## Luật chưa áp dụng cho dự án nào"), "",
            ", ".join(s["never"]) or "—"]
    return "\n".join(out) + "\n"
