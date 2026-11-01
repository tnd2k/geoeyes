"""The shared archive: a second project downloading other bursts of the same acquisition adds them to the scene's
``bursts.json`` instead of replacing the first project's records."""
import json
from datetime import UTC, datetime

from geoeyes.core.types import OrbitDirection
from geoeyes.processing.acquire import s1_bursts
from geoeyes.sensors.sentinel1.asf import BurstRef
from geoeyes.workspace import WorkspaceLayout

SLC = "S1A_SLC_20251001"           # short: the pytest temp path plus a real name exceeds MAX_PATH


def _ref(sw: str, idx: int) -> BurstRef:
    return BurstRef(file_id=f"S1_19426{idx}_{sw}_20251001T225115_VV_8A88-BURST", full_burst_id=f"091_19426{idx}_{sw}",
                    relative_burst_id=194260 + idx, subswath=sw, burst_index=idx, polarization="VV",
                    start=datetime(2025, 10, 1, 22, 51, 16, tzinfo=UTC), slc_name=SLC, relative_orbit=91,
                    absolute_orbit=61238, direction=OrbitDirection.DESCENDING, platform="SENTINEL-1A",
                    data_url="https://x/data", metadata_url="https://x/meta", bytes=10, footprint_wkt="")


def test_second_download_merges_bursts_json(tmp_path):
    ws = WorkspaceLayout.at(tmp_path / "ws")
    for refs in ([_ref("IW2", 3), _ref("IW2", 4)], [_ref("IW1", 4), _ref("IW2", 4)]):
        for r in refs:                                       # files already complete: nothing to fetch
            for p in s1_bursts.burst_paths(ws, r):
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"x")
                p.with_name(p.name + ".done").write_text("ok")
        s1_bursts.download(refs, ws, token=None, session=object())
    listed = json.loads((s1_bursts.scene_dir(ws, _ref("IW2", 3)) / "bursts.json").read_text(encoding="utf-8"))
    assert [(b["subswath"], b["burst_index"]) for b in listed] == [("IW1", 4), ("IW2", 3), ("IW2", 4)]
