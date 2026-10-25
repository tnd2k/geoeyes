"""Machine settings from ``GEOEYES_*`` environment variables (and a ``.env`` file). The only place
that reads the environment (ARCHITECTURE §14.2); everything else receives a ``Settings`` object."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GEOEYES_", env_file=".env", env_file_encoding="utf-8",
                                      extra="ignore", frozen=True)

    workspace: Path = Field(default=Path("~/geoeyes-workspace"))
    archive_uri: str = ""                 # optional external raw archive (fsspec URI)
    products_uri: str = ""                # optional external product store (fsspec URI)
    log_level: str = "INFO"
    log_retention_days: int = 365
    snap_gpt: str = ""                    # only for the transitional SNAP engine
    test_data: Path | None = None         # golden / test data root
    # NASA Earthdata token for precise S1 orbits (machine-wide EARTHDATA_TOKEN; never logged)
    earthdata_token: str = Field(default="", validation_alias="EARTHDATA_TOKEN", repr=False)
    # login token of `geoeyes serve` on a non-local address (random when unset)
    web_token: str = Field(default="", repr=False)

    def workspace_layout(self):
        from geoeyes.workspace import WorkspaceLayout
        return WorkspaceLayout.at(self.workspace)


def _windows_env(name: str) -> str:
    """``name`` from the persistent Windows environment (Machine, then User), "" if absent or not on Windows.
    A process only sees the variables set before it (or the editor / terminal it comes from) started: the
    EARTHDATA_TOKEN set machine-wide later is read here instead."""
    if os.name != "nt":
        return ""
    import winreg
    keys = ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, "Environment"))
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as k:
                value, _ = winreg.QueryValueEx(k, name)
        except OSError:
            continue
        if value:
            return os.path.expandvars(str(value))
    return ""


def load_settings(**overrides) -> Settings:
    s = Settings(**overrides)
    if not s.earthdata_token and "earthdata_token" not in overrides:
        token = _windows_env("EARTHDATA_TOKEN")
        if token:
            s = s.model_copy(update={"earthdata_token": token})
    return s
