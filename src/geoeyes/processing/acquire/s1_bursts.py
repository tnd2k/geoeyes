"""Download Sentinel-1 burst SLCs from ASF into the workspace archive (ADR-023).

Archive layout (one folder per source SLC; the metadata XML is shared by all its bursts)::

    archive/sentinel1/<track_id>/<YYYY>/<SLC name>/
        <SLC name>_<POL>.xml            combined annotation / calibration / noise / manifest
        <IWx>_<POL>_<burstIndex>.tiff   one burst, CInt16
        bursts.json                     the BurstRef records (provenance)

The ASF burst extractor builds bursts on demand and answers 202 while doing so; requests are
retried until the file is served. Files are written to a temporary name, checked against the
response ``Content-Length`` (the catalogue ``bytes`` is the raw burst size, not the GeoTIFF size)
and renamed when complete; a ``.done`` marker records completed files for resumption.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from geoeyes.core.errors import DataError
from geoeyes.core.logging import event
from geoeyes.sensors.sentinel1.asf import BurstRef, group_by_acquisition
from geoeyes.workspace.layout import WorkspaceLayout

log = logging.getLogger(__name__)

CHUNK = 1 << 20


@dataclass(frozen=True)
class BurstFiles:
    ref: BurstRef
    tiff: Path
    xml: Path


def scene_dir(ws: WorkspaceLayout, ref: BurstRef) -> Path:
    return ws.scene_dir("sentinel1", ref.track_id, ref.start.year, ref.slc_name)


def burst_paths(ws: WorkspaceLayout, ref: BurstRef) -> tuple[Path, Path]:
    d = scene_dir(ws, ref)
    return d / f"{ref.subswath}_{ref.polarization}_{ref.burst_index}.tiff", d / f"{ref.slc_name}_{ref.polarization}.xml"


def make_session(token: str | None) -> requests.Session:
    from geoeyes.sensors.sentinel1.earthdata import EarthdataSession
    return EarthdataSession(token)              # also sets the ASF login cookie the burst extractor expects


def _complete(dest: Path) -> bool:
    return dest.exists() and dest.with_name(dest.name + ".done").exists()


def _fetch(session: requests.Session, url: str, dest: Path, *, max_wait_s: float = 600, attempts: int = 3) -> Path:
    if _complete(dest):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            t0 = time.monotonic()
            while True:
                resp = session.get(url, stream=True, timeout=300)
                if resp.status_code != 202:
                    break
                resp.close()
                if time.monotonic() - t0 > max_wait_s:
                    raise DataError(f"{url}: still being prepared after {max_wait_s:.0f} s")
                time.sleep(2)
            resp.raise_for_status()
            expected = int(resp.headers.get("Content-Length") or 0)
            with open(tmp, "wb") as fh:
                for block in resp.iter_content(CHUNK):
                    fh.write(block)
            got = tmp.stat().st_size
            if (expected and got != expected) or got == 0:
                raise DataError(f"{url}: got {got} bytes, expected {expected or '> 0'}")
            os.replace(tmp, dest)
            dest.with_name(dest.name + ".done").write_text(str(got), encoding="ascii")
            return dest
        except (requests.RequestException, DataError) as exc:
            last_exc = exc
            tmp.unlink(missing_ok=True)
            log.warning("download %s failed (attempt %d/%d): %s", dest.name, attempt, attempts, exc)
            time.sleep(5 * attempt)
    raise DataError(f"could not download {url}: {last_exc}")


def download(refs: Iterable[BurstRef], ws: WorkspaceLayout, *, token: str | None, workers: int = 4,
             session: requests.Session | None = None) -> list[BurstFiles]:
    """Download bursts (and their shared metadata XML) into the archive; skips complete files."""
    refs = list(refs)
    http = session or make_session(token)
    jobs: dict[Path, tuple[str, int]] = {}
    out: list[BurstFiles] = []
    for slc, group in group_by_acquisition(refs).items():
        for r in group:
            tiff, xml = burst_paths(ws, r)
            jobs.setdefault(tiff, (r.data_url, r.bytes))       # catalogue size, for the estimate only
            jobs.setdefault(xml, (r.metadata_url, 0))
            out.append(BurstFiles(r, tiff, xml))
        d = scene_dir(ws, group[0])
        d.mkdir(parents=True, exist_ok=True)
        (d / "bursts.json").write_text(json.dumps([asdict(r) for r in group], default=str, indent=1),
                                       encoding="utf-8")
        log.debug("queued %s: %d bursts", slc, len(group))
    todo = {p: v for p, v in jobs.items() if not _complete(p)}
    total = sum(v[1] for v in todo.values())
    log.info("bursts: %d files to download (~%.1f GB), %d already in the archive",
             len(todo), total / 1e9, len(jobs) - len(todo))
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {pool.submit(_fetch, http, url, path): path for path, (url, _size) in todo.items()}
        for fut in as_completed(futs):
            fut.result()
            done += 1
            event(log, "progress", f"downloaded {futs[fut].name}", stage="acquire", done=done, total=len(todo))
    return out
