"""QGIS styles (QML) for point products: graduated LOS velocity.

Classification: QGIS "Pretty Breaks", 10 classes requested, over the full value range (min–max, no clipping);
the breaks are those QGIS computes (``pretty_breaks`` ports ``QgsSymbolLayerUtils::prettyBreaks``), so
reclassifying in QGIS gives the same classes. Colours: jet reversed (red = away from the satellite, e.g.
subsidence; blue = toward it). Markers: circles without stroke, sized in metres on the ground from the point
spacing so neighbours do not cover each other at any zoom, kept between ``MIN_MM`` and ``MAX_MM`` on screen.
"""
from __future__ import annotations

import math
from xml.sax.saxutils import quoteattr

import numpy as np

STYLE = "pretty10-jet_r-ground/2"  # in the export fingerprint: a new style re-runs the export
CLASSES = 10
MIN_MM, MAX_MM = 0.3, 3.0          # on-screen size limits of the ground-sized markers
FILL = 0.9                         # marker diameter / median nearest-neighbour distance


def pretty_breaks(minimum: float, maximum: float, classes: int = CLASSES) -> list[float]:
    """Upper class bounds of QGIS Pretty Breaks (R's ``pretty``); the first class starts at ``minimum``."""
    if classes < 1:
        return [maximum]
    minimum_count = classes // 3
    shrink, high_bias = 0.75, 1.5
    adjust_bias = 0.5 + 1.5 * high_bias
    h = high_bias
    dx = maximum - minimum
    if math.isclose(dx, 0.0, abs_tol=1e-12) and math.isclose(maximum, 0.0, abs_tol=1e-12):
        cell, small = 1.0, True
    else:
        cell = max(abs(minimum), abs(maximum))
        u = int(1 + (1.0 / (1 + h))) if adjust_bias >= 1.5 * h + 0.5 else int(1 + 1.5 / (1 + adjust_bias))
        small = dx < cell * u * max(1, classes) * 1e-07 * 3.0
    if small:
        if cell > 10:
            cell = 9 + cell / 10
        cell *= shrink
        if minimum_count > 1:
            cell /= minimum_count
    else:
        cell = dx / classes if classes > 1 else dx
    cell = max(cell, 20 * 1e-07)
    base = 10.0 ** math.floor(math.log10(cell))
    unit = base
    if 2 * base - cell < h * (cell - unit):
        unit = 2.0 * base
        if 5 * base - cell < adjust_bias * (cell - unit):
            unit = 5.0 * base
            if 10.0 * base - cell < h * (cell - unit):
                unit = 10.0 * base
    start = math.floor(minimum / unit + 1e-07)
    end = math.ceil(maximum / unit - 1e-07)
    while start * unit > minimum + 1e-07 * unit:
        start -= 1
    while end * unit < maximum - 1e-07 * unit:
        end += 1
    k = math.floor(0.5 + end - start)
    if k < minimum_count:
        k = minimum_count - k
        if start >= 0:
            end += k // 2
            start = start - k // 2 + k % 2
        else:
            start -= k // 2
            end = end + k // 2 + k % 2
    breaks = [start * unit + i * unit for i in range(1, end - start + 1)]
    if not breaks:
        return breaks
    breaks[0] = max(breaks[0], minimum)
    breaks[-1] = min(breaks[-1], maximum)
    if minimum < 0.0 < maximum:                      # the break near zero is exactly zero (as QGIS)
        pos = 0
        for i in range(1, len(breaks)):
            if abs(breaks[i]) < abs(breaks[i - 1]):
                pos = i
        breaks[pos] = 0.0
    return breaks


def jet_r(n: int) -> list[str]:
    """``n`` colours of the reversed jet ramp, as QGIS "r,g,b"."""
    import matplotlib
    cmap = matplotlib.colormaps["jet_r"]
    return [",".join(str(int(round(c * 255))) for c in cmap(x)[:3]) for x in np.linspace(0, 1, n)]


def marker_size_m(lon, lat) -> float:
    """Marker diameter (m on the ground): ``FILL`` × median distance to the nearest neighbour."""
    from scipy.spatial import cKDTree
    lon, lat = np.asarray(lon, np.float64), np.asarray(lat, np.float64)
    ok = np.isfinite(lon) & np.isfinite(lat)
    if ok.sum() < 2:
        return 10.0
    lat0 = np.radians(np.mean(lat[ok]))
    xy = np.column_stack([lon[ok] * 111_320.0 * np.cos(lat0), lat[ok] * 110_540.0])
    d, _ = cKDTree(xy).query(xy, k=2)
    nn = d[:, 1][d[:, 1] > 0]
    return float(round(FILL * np.median(nn), 2)) if nn.size else 10.0


def _options(opts: dict[str, str]) -> str:
    return "".join(f"<Option name={quoteattr(k)} value={quoteattr(v)} type=\"QString\"/>" for k, v in opts.items())


def _symbol(name: str, color: str, size_m: float) -> str:
    opts = {"angle": "0", "color": f"{color},255", "name": "circle", "outline_color": "0,0,0,0",
            "outline_style": "no", "outline_width": "0", "outline_width_unit": "MM", "scale_method": "diameter",
            "size": f"{size_m:g}", "size_unit": "RenderMetersInMapUnits",
            # minScale, maxScale, min size enabled, min size (mm), max size enabled, max size (mm)
            "size_map_unit_scale": f"3x:0,0,1,{MIN_MM:g},1,{MAX_MM:g}"}
    props = "".join(f"<prop k={quoteattr(k)} v={quoteattr(v)}/>" for k, v in opts.items())
    return (f'<symbol type="marker" name={quoteattr(name)} alpha="1" clip_to_extent="1" force_rhr="0">'
            f'<layer class="SimpleMarker" enabled="1" pass="0" locked="0"><Option type="Map">{_options(opts)}'
            f"</Option>{props}</layer></symbol>")


def _ramp() -> str:
    stops = jet_r(11)
    opts = {"color1": f"{stops[0]},255", "color2": f"{stops[-1]},255", "discrete": "0", "rampType": "gradient",
            "stops": ":".join(f"{i / 10:g};{c},255" for i, c in enumerate(stops[1:-1], start=1))}
    return f'<colorramp type="gradient" name="[source]"><Option type="Map">{_options(opts)}</Option></colorramp>'


def velocity_qml(values, field: str = "vel_los_mm_yr", size_m: float = 10.0) -> str:
    """Graduated QML for ``field``: Pretty Breaks (10 classes) over min–max, jet_r, ground-sized markers."""
    v = np.asarray(values, np.float64)
    lo_v, hi_v = float(np.nanmin(v)), float(np.nanmax(v))
    uppers = pretty_breaks(lo_v, hi_v, CLASSES)
    lowers = [lo_v, *uppers[:-1]]
    colors = jet_r(len(uppers))
    step = (uppers[1] - uppers[0]) if len(uppers) > 2 else (hi_v - lo_v) or 1.0
    prec = max(0, 1 - math.floor(math.log10(abs(step)))) if step else 1     # step 50 -> 0 decimals, 2 -> 1
    ranges, symbols = [], []
    for k, (lo, hi, color) in enumerate(zip(lowers, uppers, colors, strict=True)):
        label = f"{lo:.{prec}f} - {hi:.{prec}f}"
        ranges.append(f'<range lower="{lo:.6f}" upper="{hi:.6f}" symbol="{k}" label={quoteattr(label)} '
                      f'render="true"/>')
        symbols.append(_symbol(str(k), color, size_m))
    method = ('<classificationMethod id="Pretty"><symmetricMode enabled="0" symmetrypoint="0" astride="0"/>'
              f'<labelFormat format="%1 - %2" trimtrailingzeroes="0" labelprecision="{prec}"/>'
              "<parameters><Option/></parameters><extraInformation/></classificationMethod>")
    return ("<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
            '<qgis version="3.28.0" styleCategories="Symbology">'
            f'<renderer-v2 type="graduatedSymbol" attr={quoteattr(field)} graduatedMethod="GraduatedColor" '
            'symbollevels="0" enableorderby="0" forceraster="0">'
            f"<ranges>{''.join(ranges)}</ranges><symbols>{''.join(symbols)}</symbols>"
            f"<source-symbol>{_symbol('0', colors[len(colors) // 2], size_m)}</source-symbol>"
            f'{_ramp()}<mode name="pretty"/>{method}<rotation/><sizescale/></renderer-v2>'
            "<layerGeometryType>0</layerGeometryType></qgis>\n")
