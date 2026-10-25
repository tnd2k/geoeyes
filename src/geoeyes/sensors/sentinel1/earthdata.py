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


class EarthdataSession(requests.Session):
    def __init__(self, token: str | None, *, asf_cookie: bool = True):
        super().__init__()
        if not token:
            raise DataError("EARTHDATA_TOKEN is required for this download")
        self._auth_header = f"Bearer {token}"
        self.headers["Authorization"] = self._auth_header
        if asf_cookie:
            r = self.get(ASF_COOKIE_URL, timeout=120)
            r.raise_for_status()

    def rebuild_auth(self, prepared_request, response):
        host = urlparse(prepared_request.url).hostname or ""
        if host.endswith(TRUSTED_SUFFIXES):
            prepared_request.headers["Authorization"] = self._auth_header
        else:
            prepared_request.headers.pop("Authorization", None)
