"""Zenith hydrostatic and wet delays (m) at scatterers from one ERA5 pressure-level file (TRAIN
``aps_weather_model_SAR.m`` / ``aps_load_era.m``, Jolivet et al. 2011; NumPy port of the batched legacy path).

Per point: temperature, relative humidity and geopotential are interpolated (bilinear) from the grid at every
pressure level, geopotential is converted to geometric height, the profile is resampled to 15 m steps up to
15 km, the wet refractivity is integrated downward from the top and the hydrostatic delay follows from the
pressure; both are resampled to 5 m and taken at the point height (clipped at 0).
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import RegularGridInterpolator

RD, RV = 287.05, 461.495
K1, K2, K3 = 0.776, 0.716, 3.75e3
G0 = 9.80665
R_MAX, R_MIN = 6378137.0, 6356752.0
Z_TOP, DZ, DZ_OUT = 15000.0, 15.0, 5.0


def load_netcdf(path):
    """(T K, RH %, geopotential m²/s², levels hPa, lat, lon) with arrays (lat, lon, level), levels from the
    surface up, lat/lon increasing and lon in [-180, 180)."""
    import xarray as xr
    with xr.open_dataset(path) as ds:
        for extra in ("valid_time", "time", "number", "expver"):
            if extra in ds.dims:
                ds = ds.isel({extra: 0}, drop=True)

        def var(*names):
            for n in names:
                if n in ds:
                    return ds[n]
            raise KeyError(f"none of {names} in {path}")

        t, r, z = var("t", "temperature"), var("r", "relative_humidity"), var("z", "geopotential")
        lev = "level" if "level" in t.dims else "pressure_level"
        la = "latitude" if "latitude" in t.dims else "lat"
        lo = "longitude" if "longitude" in t.dims else "lon"
        arrs = [np.asarray(v.transpose(la, lo, lev).values, np.float64) for v in (t, r, z)]
        levels = np.asarray(t[lev].values, np.float64)
        lats = np.asarray(t[la].values, np.float64)
        lons = np.asarray(t[lo].values, np.float64)
    if levels[0] < levels[-1]:                       # surface (high pressure) first
        arrs, levels = [a[:, :, ::-1] for a in arrs], levels[::-1]
    lons = np.where(lons >= 180.0, lons - 360.0, lons)
    o_lat, o_lon = np.argsort(lats), np.argsort(lons)
    arrs = [a[o_lat][:, o_lon] for a in arrs]
    return arrs[0], arrs[1], arrs[2], levels, lats[o_lat], lons[o_lon]


def _svp_hpa(t):
    svpw = 6.1121 * np.exp((17.502 * (t - 273.16)) / (240.97 + t - 273.16))
    svpi = 6.1121 * np.exp((22.587 * (t - 273.16)) / (273.86 + t - 273.16))
    w = np.clip((t - 250.16) / (273.16 - 250.16), 0.0, 1.0)
    svp = svpi + (svpw - svpi) * w**2
    return np.where(t > 273.16, svpw, np.where(t < 250.16, svpi, svp))


def _interp_rows(x, xp, fp):
    """Row-wise linear interpolation (constant beyond the ends): x (m,), xp/fp (c, nl) with xp increasing."""
    c, nl = xp.shape
    idx = np.clip(np.array([np.searchsorted(xp[i], x) for i in range(c)]), 1, nl - 1)
    rows = np.arange(c)[:, None]
    x0, x1 = xp[rows, idx - 1], xp[rows, idx]
    w = np.clip((x[None, :] - x0) / (x1 - x0 + 1e-12), 0.0, 1.0)
    return fp[rows, idx - 1] * (1.0 - w) + fp[rows, idx] * w


def column_delays(z_geop, t, rh, p_hpa, lat_deg, h_m, chunk: int = 5000):
    """Zenith hydrostatic / wet delay (m) for points with level profiles (n, n_level)."""
    n = z_geop.shape[0]
    xi = np.arange(0.0, Z_TOP + DZ, DZ)
    out_z = np.arange(0.0, xi[-1] + DZ_OUT, DZ_OUT)
    i_top = min(int(round(Z_TOP / DZ)), xi.size - 1)
    zhd, zwd = np.empty(n), np.empty(n)
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        lat = np.radians(lat_deg[s:e])
        cos2 = np.cos(2 * lat)
        g = 9.80616 * (1 - 0.002637 * cos2 + 5.9e-6 * cos2**2)
        re = np.sqrt(1.0 / (np.cos(lat) ** 2 / R_MAX**2 + np.sin(lat) ** 2 / R_MIN**2))
        hgeo = z_geop[s:e] / G0
        zm = hgeo * re[:, None] / ((g / G0 * re)[:, None] - hgeo)
        tt = t[s:e]
        e_pa = rh[s:e] / 100.0 * _svp_hpa(tt) * 100.0
        yt, ye, yp = (_interp_rows(xi, zm, a) for a in (tt, e_pa, p_hpa[s:e] * 100.0))
        wet = (K2 - RD * K1 / RV) * ye / yt + K3 * ye / yt**2
        wf = wet[:, ::-1]
        cum = np.concatenate([np.zeros((e - s, 1)), np.cumsum(0.5 * (wf[:, :-1] + wf[:, 1:]) * -DZ, axis=1)], axis=1)
        lw = -1e-6 * cum[:, ::-1]
        ld = 1e-6 * (K1 * RD / g)[:, None] * (yp - yp[:, i_top:i_top + 1])
        k = np.clip(np.round(np.clip(h_m[s:e], 0.0, None) / DZ_OUT).astype(int), 0, out_z.size - 1)
        # the 5 m resampling is linear between the 15 m nodes: evaluate it at the chosen 5 m node only
        zk = out_z[k]
        j = np.clip((zk / DZ).astype(int), 0, xi.size - 2)
        w = np.clip((zk - xi[j]) / DZ, 0.0, 1.0)
        r = np.arange(e - s)
        zhd[s:e] = ld[r, j] * (1 - w) + ld[r, j + 1] * w
        zwd[s:e] = lw[r, j] * (1 - w) + lw[r, j + 1] * w
    return zhd, zwd


def column_profiles(z_geop, t, rh, p_hpa, lat_deg) -> tuple[np.ndarray, np.ndarray]:
    """Hydrostatic / wet zenith delay (m) of columns (c, n_level) at every 5 m height from 0 to 15 km: (c, n_z)."""
    xi = np.arange(0.0, Z_TOP + DZ, DZ)
    out_z = np.arange(0.0, xi[-1] + DZ_OUT, DZ_OUT)
    i_top = min(int(round(Z_TOP / DZ)), xi.size - 1)
    lat = np.radians(lat_deg)
    cos2 = np.cos(2 * lat)
    g = 9.80616 * (1 - 0.002637 * cos2 + 5.9e-6 * cos2**2)
    re = np.sqrt(1.0 / (np.cos(lat) ** 2 / R_MAX**2 + np.sin(lat) ** 2 / R_MIN**2))
    hgeo = z_geop / G0
    zm = hgeo * re[:, None] / ((g / G0 * re)[:, None] - hgeo)
    e_pa = rh / 100.0 * _svp_hpa(t) * 100.0
    yt, ye, yp = (_interp_rows(xi, zm, a) for a in (t, e_pa, p_hpa * 100.0))
    wet = (K2 - RD * K1 / RV) * ye / yt + K3 * ye / yt**2
    wf = wet[:, ::-1]
    cum = np.concatenate([np.zeros((zm.shape[0], 1)), np.cumsum(0.5 * (wf[:, :-1] + wf[:, 1:]) * -DZ, axis=1)],
                         axis=1)
    lw = -1e-6 * cum[:, ::-1]
    ld = 1e-6 * (K1 * RD / g)[:, None] * (yp - yp[:, i_top:i_top + 1])
    j = np.clip((out_z / DZ).astype(int), 0, xi.size - 2)
    w = np.clip((out_z - xi[j]) / DZ, 0.0, 1.0)
    return ld[:, j] * (1 - w) + ld[:, j + 1] * w, lw[:, j] * (1 - w) + lw[:, j + 1] * w


def delays_at_points(path, lon, lat, h_m) -> tuple[np.ndarray, np.ndarray]:
    """Zenith hydrostatic and wet delays (m) at points (lon, lat deg, height m above the geoid); NaN for points
    more than one degree outside the file's grid, clamped to the grid edge within it.

    As TRAIN: the delay profiles are computed once per weather-model column (every 5 m up to 15 km) around the
    points and interpolated bilinearly to each point at its height (the legacy code interpolated the level
    fields to every point first: same physics, ~1e3 times slower for dense PS)."""
    t, rh, z, levels, lats, lons = load_netcdf(path)
    lon = np.where(np.asarray(lon, np.float64) >= 180.0, np.asarray(lon, np.float64) - 360.0, lon)
    lat = np.asarray(lat, np.float64)
    far = (lat < lats[0] - 1) | (lat > lats[-1] + 1) | (lon < lons[0] - 1) | (lon > lons[-1] + 1)
    la_q, lo_q = np.clip(lat, lats[0], lats[-1]), np.clip(lon, lons[0], lons[-1])
    ia = np.clip(np.searchsorted(lats, la_q) - 1, 0, lats.size - 2)
    io = np.clip(np.searchsorted(lons, lo_q) - 1, 0, lons.size - 2)
    r0, r1 = ia.min(), ia.max() + 2                  # the columns around the points only
    c0, c1 = io.min(), io.max() + 2
    sub = (slice(r0, r1), slice(c0, c1))
    nr, nc = r1 - r0, c1 - c0
    lat_cols = np.repeat(lats[r0:r1], nc)
    flat = (lambda a: a[sub].reshape(nr * nc, -1))  # noqa: E731
    p = np.broadcast_to(levels[None, :], (nr * nc, levels.size))
    ld, lw = column_profiles(flat(z), flat(t), flat(rh), p, lat_cols)
    k = np.clip(np.round(np.clip(np.asarray(h_m, np.float64), 0.0, None) / DZ_OUT).astype(int), 0, ld.shape[1] - 1)
    wa = (la_q - lats[ia]) / (lats[ia + 1] - lats[ia])
    wo = (lo_q - lons[io]) / (lons[io + 1] - lons[io])
    out = []
    for prof in (ld, lw):
        g = prof.reshape(nr, nc, -1)
        a, b = ia - r0, io - c0
        v = (g[a, b, k] * (1 - wa) * (1 - wo) + g[a + 1, b, k] * wa * (1 - wo) +
             g[a, b + 1, k] * (1 - wa) * wo + g[a + 1, b + 1, k] * wa * wo)
        v[far] = np.nan
        out.append(v)
    return out[0], out[1]


def delays_at_points_exact(path, lon, lat, h_m) -> tuple[np.ndarray, np.ndarray]:
    """Legacy order (level fields interpolated to every point, then one column per point); for checks."""
    t, rh, z, levels, lats, lons = load_netcdf(path)
    lon = np.where(np.asarray(lon, np.float64) >= 180.0, np.asarray(lon, np.float64) - 360.0, lon)
    lat = np.asarray(lat, np.float64)
    far = (lat < lats[0] - 1) | (lat > lats[-1] + 1) | (lon < lons[0] - 1) | (lon > lons[-1] + 1)
    pts = np.column_stack([np.clip(lat, lats[0], lats[-1]), np.clip(lon, lons[0], lons[-1])])
    nl = levels.size
    prof = {}
    for name, a in (("t", t), ("rh", rh), ("z", z)):
        prof[name] = np.stack([RegularGridInterpolator((lats, lons), a[:, :, k])(pts) for k in range(nl)], axis=1)
    p = np.broadcast_to(levels[None, :], prof["t"].shape)
    zhd, zwd = column_delays(prof["z"], prof["t"], prof["rh"], p, lat, np.asarray(h_m, np.float64))
    zhd[far] = zwd[far] = np.nan
    return zhd, zwd
