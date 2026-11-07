"""SICD scenes for the stack builder: a NITF as delivered, or a cut (complex GeoTIFF + chip XML) written by
``geoeyes.opendata.fetch``.

GeoEyes convention: lines = SICD columns (azimuth), samples = SICD rows (range): ``read_slc`` transposes. Data of
a product with Row.Sgn = +1 are conjugated so that every scene has the -2π·KCtr·ΔR phase convention. A cut keeps
the SICD chip convention: ``ImageData/NumRows, NumCols`` = the cut, ``FirstRow, FirstCol`` = its place in the full
image (the SCP pixel stays in full-image coordinates).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from geoeyes.core.errors import SensorError
from geoeyes.sensors.sicd.meta import Sicd, parse


def find_files(scene_dir: str | Path) -> tuple[Path, Path | None]:
    """(data, xml): a cut ``*_SICD.tif`` + ``*_SICD.xml``, else a ``*SICD*.nitf`` (XML inside: None)."""
    d = Path(scene_dir)
    tifs = sorted(d.glob("*SICD*.tif"))
    if tifs:
        xml = tifs[0].with_suffix(".xml")
        if not xml.exists():
            raise SensorError(f"{d}: {tifs[0].name} without its SICD XML")
        return tifs[0], xml
    nitf = sorted(d.glob("*SICD*.nitf")) or sorted(d.glob("*.ntf"))
    if not nitf:
        raise SensorError(f"{d}: no SICD (NITF, or cut GeoTIFF + XML)")
    return nitf[0], None


def read_metadata(data: str | Path, xml: str | Path | None = None) -> Sicd:
    if xml is not None:
        return parse(Path(xml).read_text(encoding="utf-8"))
    from geoeyes.sensors.sicd.nitf import Nitf
    return parse(Nitf(data).xml)


def read_slc(data: str | Path, meta: Sicd, window: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Complex64 (lines = SICD cols, samples = SICD rows); ``window`` (l0, l1, s0, s1) in that convention."""
    l0, l1, s0, s1 = window if window is not None else (0, meta.cols, 0, meta.rows)
    if str(data).lower().endswith(".tif"):
        import rasterio
        from rasterio.windows import Window
        with rasterio.open(data) as src:
            a = src.read(1, window=Window(l0, s0, l1 - l0, s1 - s0))      # TIFF rows = SICD rows
        if not np.iscomplexobj(a):
            raise SensorError(f"{data}: expected complex data, got {a.dtype}")
    else:
        from geoeyes.sensors.sicd.nitf import Nitf
        a = Nitf(data).read(s0, s1, l0, l1)
    a = a.T.astype(np.complex64, copy=False)
    return np.conj(a) if meta.row_sgn > 0 else a


def chip_xml(xml: str, row0: int, col0: int, rows: int, cols: int) -> str:
    """The SICD XML of a cut of the image at (row0, col0) of size (rows, cols), in its own pixels."""
    m = re.search(r"<(\w+:)?ImageData>.*?</(\w+:)?ImageData>", xml, re.S)
    if m is None:
        raise SensorError("SICD XML without ImageData")
    block = m.group(0)
    first_row = int(re.search(r"<(?:\w+:)?FirstRow>(\d+)<", block).group(1))
    first_col = int(re.search(r"<(?:\w+:)?FirstCol>(\d+)<", block).group(1))
    full = re.search(r"<(\w+:)?FullImage>.*?</(\w+:)?FullImage>", block, re.S).group(0)
    head, tail = block[:block.index(full)], block[block.index(full):]       # FullImage keeps its sizes
    for tag, val in (("NumRows", rows), ("NumCols", cols), ("FirstRow", first_row + row0),
                     ("FirstCol", first_col + col0)):
        head = re.sub(rf"(<(?:\w+:)?{tag}>)\d+(<)", rf"\g<1>{val}\g<2>", head, count=1)
    return xml[:m.start()] + head + tail + xml[m.end():]


__all__ = ["chip_xml", "find_files", "read_metadata", "read_slc"]
