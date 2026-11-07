"""Sentinel-1 SLC bursts from the Copernicus Data Space Ecosystem (CDSE): the fallback of the ASF burst extractor.

* token: OpenID Connect password grant (client ``cdse-public``) with the user's CDSE login from ``.netrc`` /
  ``_netrc`` (``machine identity.dataspace.copernicus.eu``), refreshed before it expires;
* search: ``catalogue.dataspace.copernicus.eu/odata/v1/Bursts`` by relative burst id, subswath, polarisation and
  parent SLC — the same burst as an ASF ``BurstRef``;
* download: POST ``Bursts(<Id>)/$value`` (on-demand extraction; the answer redirects to
  ``bursts.dataspace.copernicus.eu``), a ``.zip``.

The layout of that zip is not documented (2026-11): ``probe`` downloads a few bursts, lists their members and times
them, so that the conversion to the archive layout of ``processing.acquire.s1_bursts`` (ASF combined XML + burst
GeoTIFF) is written against real files.
"""
from __future__ import annotations

import logging
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from geoeyes.core.errors import DataError

log = logging.getLogger(__name__)

IDENTITY_HOST = "identity.dataspace.copernicus.eu"
TOKEN_URL = f"https://{IDENTITY_HOST}/auth/realms/CDSE/protocol/openid-connect/token"
CATALOGUE = "https://catalogue.dataspace.copernicus.eu/odata/v1/Bursts"
CLIENT_ID = "cdse-public"


def _login() -> tuple[str, str]:
    from requests.utils import get_netrc_auth
    auth = get_netrc_auth(f"https://{IDENTITY_HOST}")
    if not auth:
        raise DataError(f"no CDSE login: add to %USERPROFILE%\\_netrc 'machine {IDENTITY_HOST} login <user> password "
                        "<password>' (a free account at dataspace.copernicus.eu)")
    return auth


@dataclass
class _Token:
    value: str = ""
    expires: float = 0.0


class CdseSession(requests.Session):
    """A session that carries a fresh CDSE access token."""

    def __init__(self):
        super().__init__()
        self._tok = _Token()
        self.headers["User-Agent"] = "GeoEyes (InSAR; Sentinel-1 bursts)"

    def token(self) -> str:
        if time.time() > self._tok.expires - 60:
            user, pw = _login()
            r = requests.post(TOKEN_URL, data={"client_id": CLIENT_ID, "username": user, "password": pw,
                                               "grant_type": "password"}, timeout=60)
            if r.status_code != 200:
                raise DataError(f"CDSE login refused ({r.status_code}): check the _netrc entry for {IDENTITY_HOST}")
            j = r.json()
            self._tok = _Token(j["access_token"], time.time() + float(j.get("expires_in", 600)))
        return self._tok.value


def find(session: requests.Session, ref) -> dict:
    """The CDSE burst record of an ASF ``BurstRef`` (same relative burst id, subswath, polarisation, parent SLC)."""
    parent = ref.slc_name if ref.slc_name.endswith(".SAFE") else f"{ref.slc_name}.SAFE"
    flt = (f"BurstId eq {int(ref.relative_burst_id)} and SwathIdentifier eq '{ref.subswath.upper()}' and "
           f"PolarisationChannels eq '{ref.polarization.upper()}' and ParentProductName eq '{parent}'")
    r = session.get(CATALOGUE, params={"$filter": flt, "$top": 5}, timeout=120)
    r.raise_for_status()
    vals = r.json().get("value", [])
    if not vals:
        raise DataError(f"CDSE: no burst for {ref.file_id} ({flt})")
    return vals[0]


def download(session: CdseSession, burst_id: str, dest_dir: Path, *, attempts: int = 4) -> Path:
    """POST ``Bursts(<Id>)/$value``, following the redirect with the token; the zip is written to ``dest_dir``."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = f"{CATALOGUE}({burst_id})/$value"
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            hdr = {"Authorization": f"Bearer {session.token()}"}
            r = session.post(url, headers=hdr, allow_redirects=False, stream=True, timeout=600)
            hops = 0
            while r.status_code in (301, 302, 303, 307, 308) and hops < 5:
                r = session.post(r.headers["Location"], headers=hdr, allow_redirects=False, stream=True, timeout=600)
                hops += 1
            r.raise_for_status()
            cd = r.headers.get("Content-Disposition", "")
            name = cd.split("filename=")[1].strip('"; ') if "filename=" in cd else f"{burst_id}.zip"
            part = dest_dir / (name + ".part")
            with open(part, "wb") as fh:
                for block in r.iter_content(1 << 20):
                    fh.write(block)
            out = dest_dir / name
            part.replace(out)
            return out
        except (requests.RequestException, DataError) as exc:
            last = exc
            log.warning("CDSE burst %s, attempt %d/%d: %s", burst_id, attempt, attempts, exc)
            time.sleep(min(5 * 3 ** (attempt - 1), 120))
    raise DataError(f"CDSE burst {burst_id} not downloaded: {last}")


def probe(refs, dest_dir: Path, n: int = 2) -> list[dict]:
    """Download ``n`` bursts, time them and list the members of each zip (to write the archive conversion)."""
    s = CdseSession()
    out = []
    for ref in list(refs)[:n]:
        t0 = time.time()
        rec = find(s, ref)
        t1 = time.time()
        z = download(s, rec["Id"], Path(dest_dir))
        t2 = time.time()
        with zipfile.ZipFile(z) as zf:
            members = [(i.filename, i.file_size) for i in zf.infolist()]
        out.append({"burst": ref.file_id, "cdse_id": rec["Id"], "search_s": round(t1 - t0, 1),
                    "download_s": round(t2 - t1, 1), "zip_mb": round(z.stat().st_size / 1e6, 1),
                    "mb_per_s": round(z.stat().st_size / 1e6 / max(t2 - t1, 1e-3), 2), "members": members})
    return out
