"""geoeyes.workspace: layout paths, settings, project lock."""
import json

import pytest

from geoeyes.config.settings import load_settings
from geoeyes.core.errors import ConfigError, LockedError
from geoeyes.workspace import WorkspaceLayout
from geoeyes.workspace.lock import ProjectLock, list_locks


def test_layout_paths_and_ids(tmp_path):
    ws = WorkspaceLayout.at(tmp_path)
    p = ws.project("mexico").ensure()
    assert p.stack_store("capella-asc-ref20240711-ab12cd") == (
        tmp_path / "projects/mexico/stacks/capella-asc-ref20240711-ab12cd/stack.zarr")
    assert p.product("mexico_capella-asc_ps_lite_20240626_20240815_v1").parent.name == "products"
    assert ws.scene_dir("sentinel1", "sentinel1-asc-078", 2024, "S1A_IW_SLC__1SSV_20240503").parts[-2] == "2024"
    assert (tmp_path / "projects/mexico/.state/locks").is_dir()
    p.config.write_text("schema = 'geoeyes.project/1'\n")
    assert ws.list_projects() == ["mexico"]
    for bad in ("../etc", "a/b", ""):
        with pytest.raises(ConfigError):
            ws.project(bad)


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOEYES_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("GEOEYES_LOG_LEVEL", "DEBUG")
    s = load_settings()
    assert s.workspace == tmp_path and s.log_level == "DEBUG"
    assert s.workspace_layout().root == tmp_path.resolve()


def test_lock_scopes_and_stale_takeover(tmp_path):
    locks = tmp_path / "locks"
    with ProjectLock(locks, scope=["s1-asc"]):
        with ProjectLock(locks, scope=["s1-desc"]):            # disjoint scope: allowed
            assert len(list_locks(locks)) == 2
        with pytest.raises(LockedError):
            ProjectLock(locks, scope=["s1-asc", "s1-desc"]).acquire()
        with pytest.raises(LockedError):
            ProjectLock(locks).acquire()                       # unscoped conflicts with everything
    assert list_locks(locks) == []

    (locks / "_all.lock").write_text(json.dumps({"pid": 999_999_999, "scope": []}), encoding="utf-8")
    with ProjectLock(locks) as lk:                             # dead PID -> taken over
        assert lk.acquired
