"""The site advisor as a local MCP server (site advisor, step V5): ``geoeyes mcp`` speaks the Model Context Protocol
(JSON-RPC 2.0, one message per line on stdin / stdout) so that Claude Code can look up the parameter catalogue,
a site profile and the advice in a session:

    claude mcp add geoeyes-advisor -- geoeyes mcp

The tools only read (catalogue, profile cache, rules, project.toml); nothing is written to a project — applying
stays with the settings form or ``geoeyes advise --apply``. The advisor itself never calls a language model: the
server only lets one read it. Written with the standard library (no MCP SDK dependency)."""
from __future__ import annotations

import json
import sys
from typing import Any

SERVER = {"name": "geoeyes-advisor", "version": "1.0"}
PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
_LANG = {"type": "string", "enum": ["en", "vi"], "description": "language of the texts (default en)"}
_WHERE = {"project": {"type": "string", "description": "a project of the workspace (its [aoi] bbox is used)"},
          "bbox": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
                   "description": "west, south, east, north (WGS84), instead of a project"}}
TOOLS = [
    {"name": "explain_param",
     "description": "What a GeoEyes processing parameter is for, its risk, usual values and related parameters "
                    "(the parameter catalogue). Query: section.key, a key, or words in English or Vietnamese.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "lang": _LANG},
                     "required": ["query"]}},
    {"name": "site_profile",
     "description": "Measured properties of an area: relief, slopes, land cover, geology, climate (Köppen), and "
                    "for a project the data of each track. Cached per area.",
     "inputSchema": {"type": "object", "properties": {**_WHERE, "lang": _LANG}}},
    {"name": "advise",
     "description": "Which rules apply to an area and the parameter values they suggest, each with its reason; for a "
                    "project, compared with its project.toml (changes, already as the rules say, values without a "
                    "rule). Read only.",
     "inputSchema": {"type": "object", "properties": {**_WHERE, "lang": _LANG}}},
    {"name": "list_rules",
     "description": "The site rules: id, conditions, values set, reason and source.",
     "inputSchema": {"type": "object", "properties": {"lang": _LANG}}},
]


def _ws():
    from geoeyes.config.settings import load_settings
    return load_settings().workspace_layout()


def _where(args: dict):
    """(bbox, dem, project, cfg, raw) from ``project`` or ``bbox``."""
    import tomllib

    from geoeyes.config.loader import load
    ws = _ws()
    if args.get("project"):
        project = ws.project(str(args["project"]))
        if not project.config.exists():
            raise ValueError(f"no project {args['project']!r} in {ws.root}")
        cfg = load(project.config)
        if not (cfg.aoi and cfg.aoi.bbox):
            raise ValueError("the project has no [aoi] bbox")
        raw = tomllib.loads(project.config.read_text(encoding="utf-8"))
        return ws, list(cfg.aoi.bbox), str(cfg.stack.dem or "srtm-1"), project, cfg, raw
    bbox = args.get("bbox")
    if not bbox or len(bbox) != 4:
        raise ValueError("give 'project' or 'bbox' [west, south, east, north]")
    return ws, [float(v) for v in bbox], "copernicus-30", None, None, None


def tool_explain_param(args: dict) -> str:
    from geoeyes.advisor import catalog
    lang = args.get("lang", "en")
    found = catalog.search(str(args.get("query", "")))
    if not found:
        return f"no parameter matches {args.get('query')!r}"
    if len(found) > 8:
        return "\n".join(f"{p.path}: {p.text[lang]['help']}" for p in found)
    return "\n\n".join(catalog.explain(p, lang) for p in found)


def tool_site_profile(args: dict) -> str:
    from geoeyes.advisor.profile import profile, summary
    ws, bbox, dem, project, cfg, _ = _where(args)
    p = profile(bbox, cache_root=ws.cache, dem=dem, project=project, cfg=cfg, progress=lambda m: None)
    return summary(p, args.get("lang", "en")) + "\n\n" + json.dumps(p, ensure_ascii=False, default=str)


def tool_advise(args: dict) -> str:
    from geoeyes.advisor import rules
    from geoeyes.advisor.profile import profile, summary
    ws, bbox, dem, project, cfg, raw = _where(args)
    lang = args.get("lang", "en")
    p = profile(bbox, cache_root=ws.cache, dem=dem, project=project, cfg=cfg, progress=lambda m: None)
    a = rules.evaluate(p)
    cmp = rules.compare(a, cfg, raw) if cfg is not None else None
    return summary(p, lang) + "\n\n" + rules.report(a, cmp, lang)


def tool_list_rules(args: dict) -> str:
    from geoeyes.advisor import rules
    lang = args.get("lang", "en")
    _, rs = rules.load()
    out = []
    for r in rs:
        out.append(f"[{r.id}] when {' and '.join(c.text for c in r.when) or 'always'}")
        if r.set:
            out.append("  set " + ", ".join(f"{k} = {v!r}" for k, v in r.set.items()))
        if r.note["en"]:
            out.append(f"  note: {r.note[lang]}")
        out.append(f"  why: {r.why[lang]}")
        out.append(f"  source: {r.source}")
    return "\n".join(out)


HANDLERS = {"explain_param": tool_explain_param, "site_profile": tool_site_profile, "advise": tool_advise,
            "list_rules": tool_list_rules}


def handle(msg: dict) -> dict | None:
    """One JSON-RPC message -> the response (None for a notification)."""
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:                                  # notifications (initialized, cancelled): no reply
        return None
    if method == "initialize":
        asked = params.get("protocolVersion")
        result: Any = {"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                       "capabilities": {"tools": {}}, "serverInfo": SERVER,
                       "instructions": "GeoEyes site advisor: parameter catalogue, site profile and rule-based "
                                       "advice. Read only."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if fn is None:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name!r}"}}
        try:
            result = {"content": [{"type": "text", "text": fn(args)}], "isError": False}
        except Exception as exc:                     # a tool error is a result, not a crash
            result = {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(stdin=None, stdout=None) -> int:
    """Read messages line by line until stdin closes. Logs go to stderr: stdout carries only the protocol."""
    import logging
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = handle(msg) if isinstance(msg, dict) else {
                "jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "batches are not supported"}}
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False, default=str) + "\n")
            stdout.flush()
    return 0
