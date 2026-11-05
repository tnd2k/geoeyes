"""HTTP session for NASA Earthdata (URS) bearer-token downloads (ASF bursts, orbits).

``requests`` drops the Authorization header on redirects to another host; ASF data hosts redirect
to ``urs.earthdata.nasa.gov`` and back, so the token is kept for Earthdata/ASF hosts only.
"""
from __future__ import annotations

from urllib.parse import urlparse

import requests

from geoeyes.core.errors import DataError

TRUSTED_SUFFIXES = (".earthdata.nasa.gov", ".asf.alaska.edu")
# Any small file on sentinel1.asf.alaska.edu: that host accepts the bearer token and sets the ASF login
# cookie, which other ASF hosts (burst extractor, s1qc orbit server) then accept — their own URS
# OAuth redirect does not take bearer tokens.
ASF_COOKIE_URL = ("https://sentinel1.asf.alaska.edu/METADATA_RAW/SA/"
                  "S1A_IW_RAW__0SSV_20141229T072718_20141229T072750_003931_004B96_B79F.iso.xml")


URS_HOST = "urs.earthdata.nasa.gov"


def netrc_basic(host: str = URS_HOST) -> str | None:
    """``Basic`` header from the user's ``.netrc`` / ``_netrc`` entry for ``host`` (None when absent)."""
    import base64

    from requests.utils import get_netrc_auth
    auth = get_netrc_auth(f"https://{host}")
    if not auth:
        return None
    return "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()


class EarthdataSession(requests.Session):
    """Bearer token on the Earthdata / ASF hosts. ASF does not accept tokens for the burst extractor (its URS OAuth
    redirect wants a login): the old work-around took the ASF cookie from a small file on sentinel1.asf.alaska.edu,
    which answers 400 to every request since 2026-11. When the URS login page is reached, the Earthdata user name
    and password of the user's ``_netrc`` / ``.netrc`` (``machine urs.earthdata.nasa.gov``) are used instead."""

    def __init__(self, token: str | None, *, asf_cookie: bool = True):
        super().__init__()
        if not token:
            raise DataError("EARTHDATA_TOKEN is required for this download")
        self._auth_header = f"Bearer {token}"
        self._urs_basic = netrc_basic()
        self.headers["Authorization"] = self._auth_header
        if asf_cookie:
            try:
                self.get(ASF_COOKIE_URL, timeout=120).raise_for_status()
            except requests.RequestException as exc:
                if not self._urs_basic:
                    raise DataError(
                        "ASF login failed: the token work-around (a file on sentinel1.asf.alaska.edu) is refused "
                        f"({exc}) and no Earthdata login is set. Add to %USERPROFILE%\\_netrc: 'machine "
                        f"{URS_HOST} login <user> password <password>'") from exc

    def rebuild_auth(self, prepared_request, response):
        host = urlparse(prepared_request.url).hostname or ""
        if host == URS_HOST and self._urs_basic:
            prepared_request.headers["Authorization"] = self._urs_basic
        elif host.endswith(TRUSTED_SUFFIXES):
            prepared_request.headers["Authorization"] = self._auth_header
        else:
            prepared_request.headers.pop("Authorization", None)
