"""Parameter catalogue (site advisor V0): every field of the settings form has a complete entry in both languages,
and the form reads its help from it."""
from geoeyes.advisor import catalog
from geoeyes.api import settings
from geoeyes.processing.ps.params import DEFAULTS


def _form_keys() -> list[tuple[str, str]]:
    return [(s, k) for s, k, _ in settings.FIELDS] + \
        [("ps", k) for k, v in DEFAULTS.items() if settings._ps_kind(v, k)]


def test_every_form_field_has_an_entry():
    cat = catalog.load()
    missing = [f"{s}.{k}" for s, k in _form_keys() if f"{s}.{k}" not in cat]
    assert not missing, f"add these to advisor/params.toml: {missing}"


def test_no_entry_without_a_field():
    form = {f"{s}.{k}" for s, k in _form_keys()}
    assert not [p for p in catalog.load() if p not in form]


def test_entries_are_complete_and_related_exist():
    cat = catalog.load()
    for p in cat.values():
        for lang in ("en", "vi"):
            for t in catalog.TEXTS:
                assert p.text[lang][t].strip(), f"{p.path}: empty {t} ({lang})"
        for r in p.related:
            assert r in cat, f"{p.path}: related {r} is not in the catalogue"
            assert r != p.path


def test_form_help_comes_from_the_catalogue():
    for s, k, h in settings.FIELDS:
        assert h == catalog.get(s, k).help
    assert all(h for _, _, h in settings.FIELDS)


def test_search_and_explain():
    assert [p.path for p in catalog.search("ps.unwrap_grid_size")] == ["ps.unwrap_grid_size"]
    assert [p.path for p in catalog.search("unwrap_grid_size")] == ["ps.unwrap_grid_size"]
    assert "atmosphere.method" in {p.path for p in catalog.search("weather")}
    assert "ps.subtr_tropo" in {p.path for p in catalog.search("đồng bằng")}      # Vietnamese words too
    text = catalog.explain(catalog.get("ps", "unwrap_grid_size"), "vi")
    assert "Rủi ro" in text and "50 m" in text


def test_cli_params(capsys):
    from geoeyes.cli.main import main
    assert main(["params", "unwrap_grid_size", "--lang", "vi"]) == 0
    assert "[ps] unwrap_grid_size" in capsys.readouterr().out
    assert main(["params", "no_such_parameter_xyz"]) == 1
