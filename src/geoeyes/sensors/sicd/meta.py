"""SICD metadata and image projections (NGA SICD Volume 3, "Image Projections Description").

A pixel (row, col) of the full image has image coordinates xrow = (row - SCPPixel.Row) · Row.SS, ycol = (col -
SCPPixel.Col) · Col.SS (m). Its centre-of-aperture time is TimeCOAPoly(xrow, ycol); the aperture reference point
(ARP) at that time is ARPPoly(t). The image formation maps the pixel to a range R and range rate Rdot from the ARP
(the R / Rdot contour): implemented for PFA (polar format, Grid RGAZIM) and RMA / INCA (Grid RGZERO). A ground point
on a surface of given height is the intersection of that contour (a circle around the velocity) with the surface,
on the side of track; the inverse (ground -> pixel) is a Newton iteration on (xrow, ycol).

Phase: SICD images are referenced to the scene centre point (SCP). A scatterer at P has the phase
-2π · Row.KCtr · ΔR(P) (Row.Sgn = -1 convention; data of a +1 product are conjugated by the reader), with ΔR =
|ARP(t_coa) - P| - |ARP(t_coa) - SCP| for PFA and ΔR = xrow (= R_ca - R_CA_SCP) for RMA / INCA. ``phase_range``
gives ΔR; the interferometric geometric phase of a pair is 2π (KCtr_sec ΔR_sec - KCtr_ref ΔR_ref).

A chip (``ImageData.FirstRow / FirstCol``, ``NumRows / NumCols`` smaller than ``FullImage``) is addressed in its own
pixels: ``row_full = FirstRow + row``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from geoeyes.core.errors import SensorError
from geoeyes.core.geodesy import ecef_to_llh, llh_to_ecef

C = 299_792_458.0


# ----------------------------------------------------------------------------- polynomials
@dataclass(frozen=True)
class Poly1:
    c: np.ndarray                  # c[k] · t^k

    def __call__(self, t):
        return np.polynomial.polynomial.polyval(t, self.c)

    def deriv(self, t):
        return np.polynomial.polynomial.polyval(t, np.polynomial.polynomial.polyder(self.c)) if len(self.c) > 1 \
            else np.zeros_like(np.asarray(t, float))


@dataclass(frozen=True)
class Poly2:
    c: np.ndarray                  # c[i, j] · x^i · y^j

    def __call__(self, x, y):
        return np.polynomial.polynomial.polyval2d(x, y, self.c)


@dataclass(frozen=True)
class XyzPoly:
    x: Poly1
    y: Poly1
    z: Poly1

    def pos(self, t):
        return np.stack([self.x(t), self.y(t), self.z(t)], axis=-1)

    def vel(self, t):
        return np.stack([self.x.deriv(t), self.y.deriv(t), self.z.deriv(t)], axis=-1)


def _ns(root) -> dict:
    return {"s": root.tag.split("}")[0][1:]} if root.tag.startswith("{") else {"s": ""}


def _poly1(e) -> Poly1:
    c = np.zeros(int(e.get("order1")) + 1)
    for k in e:
        c[int(k.get("exponent1"))] = float(k.text)
    return Poly1(c)


def _poly2(e) -> Poly2:
    c = np.zeros((int(e.get("order1")) + 1, int(e.get("order2")) + 1))
    for k in e:
        c[int(k.get("exponent1")), int(k.get("exponent2"))] = float(k.text)
    return Poly2(c)


def _t(s: str) -> datetime:
    s = s.strip().rstrip("Z")
    if "." in s:
        head, frac = s.split(".")
        s = f"{head}.{frac[:6]}"
    return datetime.fromisoformat(s)


# ----------------------------------------------------------------------------- metadata
@dataclass
class Sicd:
    xml: str
    collector: str
    core_name: str
    collect_start: datetime
    polarization: str
    side: str                      # "R" | "L"
    ifa: str                       # PFA | RMA
    grid_type: str
    rows: int                      # this image (chip) size
    cols: int
    first_row: int
    first_col: int
    scp_row: int                   # SCP pixel, full image
    scp_col: int
    row_ss: float
    col_ss: float
    row_uvect: np.ndarray
    col_uvect: np.ndarray
    row_kctr: float
    row_sgn: int
    delta_kcoa_zero: bool
    scp: np.ndarray                # ECF
    scp_llh: tuple[float, float, float]
    time_coa: Poly2
    arp: XyzPoly
    # PFA
    polar_ang: Poly1 | None = None
    spatial_freq_sf: Poly1 | None = None
    # RMA / INCA
    time_ca: Poly1 | None = None
    r_ca_scp: float = 0.0
    drate_sf: Poly2 | None = None

    @property
    def wavelength(self) -> float:
        return 2.0 / self.row_kctr

    @property
    def scp_time(self) -> float:
        return float(self.time_coa(0.0, 0.0))

    # ---------------------------------------------------------------- image coordinates
    def xy(self, row, col) -> tuple[np.ndarray, np.ndarray]:
        """Image coordinates (m) of chip pixels."""
        return ((np.asarray(row, float) + self.first_row - self.scp_row) * self.row_ss,
                (np.asarray(col, float) + self.first_col - self.scp_col) * self.col_ss)

    def pixel(self, x, y) -> tuple[np.ndarray, np.ndarray]:
        return (np.asarray(x) / self.row_ss + self.scp_row - self.first_row,
                np.asarray(y) / self.col_ss + self.scp_col - self.first_col)

    def r_rdot(self, x, y):
        """(t_coa, ARP, VARP, R, Rdot) of image coordinates (SICD Vol. 3)."""
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        t = self.time_coa(x, y)
        arp, varp = self.arp.pos(t), self.arp.vel(t)
        if self.ifa == "PFA":
            d = arp - self.scp
            r_scp = np.linalg.norm(d, axis=-1)
            rdot_scp = np.einsum("...i,...i->...", varp, d) / r_scp
            theta = self.polar_ang(t)
            dtheta = self.polar_ang.deriv(t)
            ksf = self.spatial_freq_sf(theta)
            dksf = self.spatial_freq_sf.deriv(theta)
            dphi_dka = x * np.cos(theta) + y * np.sin(theta)
            dphi_dkc = -x * np.sin(theta) + y * np.cos(theta)
            r = r_scp + ksf * dphi_dka
            rdot = rdot_scp + (dksf * dphi_dka + ksf * dphi_dkc) * dtheta
        else:                      # RMA / INCA
            t_ca = self.time_ca(y)
            r_ca = self.r_ca_scp + x
            vm = np.linalg.norm(self.arp.vel(t_ca), axis=-1)
            dt = t - t_ca
            drsf = self.drate_sf(x, y)
            r = np.sqrt(r_ca ** 2 + drsf * vm ** 2 * dt ** 2)
            rdot = drsf / r * vm ** 2 * dt
        return t, arp, varp, r, rdot

    # ---------------------------------------------------------------- image -> ground
    def _side_sign(self) -> float:
        t = self.scp_time
        arp, varp = self.arp.pos(t), self.arp.vel(t)
        return float(np.sign(np.dot(np.cross(varp, self.scp - arp), arp)))

    def contour_to_height(self, arp, varp, r, rdot, h) -> np.ndarray:
        """Point at ellipsoidal height ``h`` on the R / Rdot contour, on the image's side of track (ECF)."""
        arp, varp = np.atleast_2d(arp), np.atleast_2d(varp)
        r, rdot, h = (np.atleast_1d(np.asarray(v, float)) for v in (r, rdot, h))
        vn = np.linalg.norm(varp, axis=-1)
        uv = varp / vn[:, None]
        a = -r * rdot / vn                                 # (P - ARP) · uv
        rho = np.sqrt(np.maximum(r ** 2 - a ** 2, 0.0))
        down = -arp / np.linalg.norm(arp, axis=-1, keepdims=True)
        e1 = down - np.einsum("ij,ij->i", down, uv)[:, None] * uv
        e1 /= np.linalg.norm(e1, axis=-1, keepdims=True)
        e2 = np.cross(uv, e1)                              # quarter turn from straight down, toward the image side
        e2 *= np.sign(np.einsum("ij,ij->i", np.cross(varp, e2), arp))[:, None] * self._side_sign()
        lo, hi = np.zeros_like(r), np.full_like(r, np.pi / 2)   # from straight down (below ground) to horizontal

        def point(psi):
            return arp + a[:, None] * uv + rho[:, None] * (np.cos(psi)[:, None] * e1 + np.sin(psi)[:, None] * e2)

        for _ in range(60):
            mid = 0.5 * (lo + hi)
            above = ecef_to_llh(point(mid))[2] > h
            hi = np.where(above, mid, hi)
            lo = np.where(above, lo, mid)
        return point(0.5 * (lo + hi))

    def image_to_ground(self, row, col, h=None, dem=None, iterations: int = 4):
        """Ground points (lat, lon, h, xyz) of chip pixels on the surface of height ``h`` (default: the SCP height),
        or on the DEM (ellipsoidal heights) when ``dem`` is given."""
        x, y = self.xy(row, col)
        shape = np.shape(x)
        _, arp, varp, r, rdot = self.r_rdot(x.ravel(), y.ravel())
        hh = np.full(r.shape, self.scp_llh[2] if h is None else 0.0) + (0.0 if h is None else h)
        p = self.contour_to_height(arp, varp, r, rdot, hh)
        if dem is not None:
            for _ in range(iterations):
                lat, lon, _ = ecef_to_llh(p)
                hh = np.asarray(dem.ellipsoidal(lat, lon), float)
                p = self.contour_to_height(arp, varp, r, rdot, hh)
        lat, lon, hgt = ecef_to_llh(p)
        return lat.reshape(shape), lon.reshape(shape), hgt.reshape(shape), p.reshape(*shape, 3)

    # ---------------------------------------------------------------- ground -> image
    def ground_to_image(self, xyz, iterations: int = 8, tol: float = 1e-4):
        """Chip (row, col) of ECF points: Newton on (xrow, ycol) matching their R / Rdot from the ARP at t_coa."""
        p = np.atleast_2d(np.asarray(xyz, float)).reshape(-1, 3)
        d = p - self.scp
        basis = np.stack([self.row_uvect, self.col_uvect], axis=1)            # (3, 2)
        xy = np.linalg.lstsq(basis, d.T, rcond=None)[0].T                     # first guess: in the image plane
        x, y = xy[:, 0].copy(), xy[:, 1].copy()

        def resid(x, y):
            _, arp, varp, r, rdot = self.r_rdot(x, y)
            dp = arp - p
            rg = np.linalg.norm(dp, axis=-1)
            return rg - r, np.einsum("ij,ij->i", varp, dp) / rg - rdot

        for _ in range(iterations):
            f1, f2 = resid(x, y)
            e = 0.5
            a1, a2 = resid(x + e, y)
            b1, b2 = resid(x, y + e)
            j11, j21, j12, j22 = (a1 - f1) / e, (a2 - f2) / e, (b1 - f1) / e, (b2 - f2) / e
            det = j11 * j22 - j12 * j21
            dx = (j22 * f1 - j12 * f2) / det
            dy = (-j21 * f1 + j11 * f2) / det
            x, y = x - dx, y - dy
            if np.nanmax(np.abs(dx)) < tol and np.nanmax(np.abs(dy)) < tol:
                break
        row, col = self.pixel(x, y)
        shape = np.shape(xyz)[:-1]
        return row.reshape(shape), col.reshape(shape)

    # ---------------------------------------------------------------- phase reference
    def phase_range(self, xyz, row=None, col=None) -> np.ndarray:
        """ΔR of ground points (m) w.r.t. the SCP reference (see the module doc); ``row, col``: their pixels in
        this image when known (else projected)."""
        p = np.asarray(xyz, float)
        if row is None:
            row, col = self.ground_to_image(p)
        x, y = self.xy(row, col)
        if self.ifa != "PFA":
            return x
        t = self.time_coa(x, y)
        arp = self.arp.pos(t)
        return np.linalg.norm(arp - p, axis=-1) - np.linalg.norm(arp - self.scp, axis=-1)

    # ---------------------------------------------------------------- summary
    @property
    def look_side(self) -> str:
        return "right" if self.side == "R" else "left"

    @property
    def pass_direction(self) -> str:
        t = self.scp_time
        arp, varp = self.arp.pos(t), self.arp.vel(t)
        lat, lon, _ = ecef_to_llh(arp[None])
        from geoeyes.core.geodesy import enu_basis
        n = enu_basis(lat, lon)[0][1]
        return "ascending" if float(np.dot(n, varp)) > 0 else "descending"

    @property
    def heading_deg(self) -> float:
        from geoeyes.core.geodesy import enu_basis
        t = self.scp_time
        arp, varp = self.arp.pos(t), self.arp.vel(t)
        lat, lon, _ = ecef_to_llh(arp[None])
        b = enu_basis(lat, lon)[0]
        return float(np.degrees(np.arctan2(b[0] @ varp, b[1] @ varp)))

    @property
    def scp_utc(self) -> datetime:
        return self.collect_start + timedelta(seconds=self.scp_time)


def parse(xml: str) -> Sicd:
    root = ET.fromstring(xml)
    ns = _ns(root)

    def f(path: str):
        e = root.find("s:" + path.replace("/", "/s:") if ns["s"] else path, ns)
        if e is None:
            raise SensorError(f"SICD: missing {path}")
        return e

    def num(path: str) -> float:
        return float(f(path).text)

    def vec(path: str) -> np.ndarray:
        e = f(path)
        return np.array([float(e.find(f"s:{k}", ns).text) for k in "XYZ"])

    ifa = f("ImageFormation/ImageFormAlgo").text.strip()
    grid_type = f("Grid/Type").text.strip()
    if (ifa, grid_type) not in (("PFA", "RGAZIM"), ("RMA", "RGZERO")):
        raise SensorError(f"SICD: image formation {ifa} / grid {grid_type} not supported (PFA RGAZIM, RMA RGZERO)")
    arp = f("Position/ARPPoly")
    kw = {}
    if ifa == "PFA":
        kw = {"polar_ang": _poly1(f("PFA/PolarAngPoly")), "spatial_freq_sf": _poly1(f("PFA/SpatialFreqSFPoly"))}
    else:
        if root.find("s:RMA/s:INCA", ns) is None:
            raise SensorError("SICD: RMA without INCA not supported")
        kw = {"time_ca": _poly1(f("RMA/INCA/TimeCAPoly")), "r_ca_scp": num("RMA/INCA/R_CA_SCP"),
              "drate_sf": _poly2(f("RMA/INCA/DRateSFPoly"))}
    dk = [root.find(f"s:Grid/s:{a}/s:DeltaKCOAPoly", ns) for a in ("Row", "Col")]
    dk_zero = all(e is None or not np.any(_poly2(e).c) for e in dk)
    first_row = root.find("s:ImageData/s:FirstRow", ns)
    first_col = root.find("s:ImageData/s:FirstCol", ns)
    pol = root.find("s:ImageFormation/s:TxRcvPolarizationProc", ns)
    core = root.find("s:CollectionInfo/s:CoreName", ns)
    return Sicd(
        xml=xml, collector=f("CollectionInfo/CollectorName").text.strip(),
        core_name=core.text.strip() if core is not None else "",
        collect_start=_t(f("Timeline/CollectStart").text),
        polarization=(pol.text or "").replace(":", "").strip() if pol is not None else "",
        side=f("SCPCOA/SideOfTrack").text.strip(), ifa=ifa, grid_type=grid_type,
        rows=int(num("ImageData/NumRows")), cols=int(num("ImageData/NumCols")),
        first_row=int(first_row.text) if first_row is not None else 0,
        first_col=int(first_col.text) if first_col is not None else 0,
        scp_row=int(num("ImageData/SCPPixel/Row")), scp_col=int(num("ImageData/SCPPixel/Col")),
        row_ss=num("Grid/Row/SS"), col_ss=num("Grid/Col/SS"),
        row_uvect=vec("Grid/Row/UVectECF"), col_uvect=vec("Grid/Col/UVectECF"),
        row_kctr=num("Grid/Row/KCtr"), row_sgn=int(num("Grid/Row/Sgn")), delta_kcoa_zero=dk_zero,
        scp=vec("GeoData/SCP/ECF"),
        scp_llh=(num("GeoData/SCP/LLH/Lat"), num("GeoData/SCP/LLH/Lon"), num("GeoData/SCP/LLH/HAE")),
        time_coa=_poly2(f("Grid/TimeCOAPoly")),
        arp=XyzPoly(_poly1(arp.find("s:X", ns)), _poly1(arp.find("s:Y", ns)), _poly1(arp.find("s:Z", ns))),
        **kw)


def corners(sicd: Sicd) -> np.ndarray:
    """GeoData/ImageCorners (lat, lon) in the order FRFC, FRLC, LRLC, LRFC."""
    root = ET.fromstring(sicd.xml)
    ns = _ns(root)
    icp = root.findall("s:GeoData/s:ImageCorners/s:ICP", ns)
    return np.array([[float(e.find("s:Lat", ns).text), float(e.find("s:Lon", ns).text)] for e in icp])


__all__ = ["Sicd", "corners", "llh_to_ecef", "parse"]
