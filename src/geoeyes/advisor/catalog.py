"""Parameter catalogue (site advisor, step V0): ``params.toml`` next to this module, one entry per field of the
settings form, in English and Vietnamese. The form help and ``geoeyes params`` read it; nothing else keeps these
texts."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).with_name("params.toml")
TEXTS = ("help", "use", "risk", "typical")
LABELS = {"en": {"use": "Use", "risk": "Risk", "typical": "Typical", "related": "Related"},
          "vi": {"use": "Dùng để", "risk": "Rủi ro", "typical": "Thường dùng", "related": "Liên quan"}}


@dataclass(frozen=True)
class Param:
    section: str
    key: str
    text: dict[str, dict[str, str]]          # lang -> {help, use, risk, typical}
    related: tuple[str, ...]

    @property
    def path(self) -> str:
        return f"{self.section}.{self.key}"

    @property
    def help(self) -> str:
        return self.text["en"]["help"]

    def info(self) -> dict:
        """JSON for the web app: the texts per language and the related fields."""
        return {"en": dict(self.text["en"]), "vi": dict(self.text["vi"]), "related": list(self.related)}


@lru_cache(maxsize=1)
def load() -> dict[str, Param]:
    """``{"section.key": Param}`` in file order."""
    raw = tomllib.loads(PATH.read_text(encoding="utf-8"))
    out: dict[str, Param] = {}
    for section, entries in raw.items():
        for key, e in entries.items():
            missing = [f for t in TEXTS for f in (t, f"{t}_vi") if not isinstance(e.get(f), str)]
            if missing:
                raise ValueError(f"{PATH.name} [{section}.{key}]: missing {', '.join(missing)}")
            text = {"en": {t: e[t] for t in TEXTS}, "vi": {t: e[f"{t}_vi"] for t in TEXTS}}
            out[f"{section}.{key}"] = Param(section, key, text, tuple(e.get("related", ())))
    return out


def get(section: str, key: str) -> Param | None:
    return load().get(f"{section}.{key}")


def help_of(section: str, key: str) -> str:
    p = get(section, key)
    return p.help if p else ""


def search(words: str) -> list[Param]:
    """Entries whose path matches exactly, else those containing every word (path or text, either language)."""
    cat = load()
    q = words.strip().lower()
    if not q:
        return list(cat.values())
    if q in cat:
        return [cat[q]]
    exact = [p for p in cat.values() if p.key.lower() == q]
    if exact:
        return exact
    terms = q.split()

    def blob(p: Param) -> str:
        return " ".join([p.path, *p.text["en"].values(), *p.text["vi"].values()]).lower()

    return [p for p in cat.values() if all(t in blob(p) for t in terms)]


def explain(p: Param, lang: str = "en") -> str:
    """Plain text of one entry."""
    t, lab = p.text[lang], LABELS[lang]
    lines = [f"[{p.section}] {p.key}", f"  {t['help']}"]
    for f in ("use", "risk", "typical"):
        lines.append(f"  {lab[f]}: {t[f]}")
    if p.related:
        lines.append(f"  {lab['related']}: {', '.join(p.related)}")
    return "\n".join(lines)
