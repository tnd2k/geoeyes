"""Minimal NITF 2.1 reader for SICD: segment table, image subheaders, the SICD XML (DES), complex pixel windows.

Works on a local file or an HTTP(S) URL (range requests: only the header, the XML and the pixels of a window are
read, so a 7 GB product can be cut to an AOI). SICD stores the complex image as uncompressed (IC = NC), pixel-
interleaved (IMODE = P) I / Q bands, big-endian, possibly in blocks and in several image segments stacked by rows
(ILOC) when larger than the 10 GB segment limit. Pixel types: RE32F_IM32F (PVTYPE R, 32 bits) and RE16I_IM16I
(PVTYPE SI, 16 bits); AMP8I_PHS8I (look-up table) is refused.
"""
from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from geoeyes.core.errors import SensorError


class _Source:
    """Byte ranges of a local file or a URL."""

    def __init__(self, src: str | Path):
        self.src = str(src)
        self.remote = self.src.startswith(("http://", "https://"))
        if self.remote:
            import requests
            self.http = requests.Session()
            self.http.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=32))
            self.http.headers["User-Agent"] = "geoeyes-sicd"

    def read(self, offset: int, size: int) -> bytes:
        if size <= 0:
            return b""
        if not self.remote:
            with open(self.src, "rb") as f:
                f.seek(offset)
                return f.read(size)
        for attempt in range(4):
            try:
                r = self.http.get(self.src, headers={"Range": f"bytes={offset}-{offset + size - 1}"}, timeout=120)
                r.raise_for_status()
                if len(r.content) != size:
                    raise OSError(f"short read {len(r.content)} / {size}")
                return r.content
            except Exception:
                if attempt == 3:
                    raise
                import time
                time.sleep(2 * (attempt + 1))
        raise AssertionError("unreachable")


@dataclass(frozen=True)
class ImageSegment:
    offset: int            # file offset of the pixel data
    rows: int
    cols: int
    row0: int              # first row of the segment in the whole image (ILOC / stacking)
    dtype: np.dtype        # of one band, big-endian
    blocks_per_row: int
    blocks_per_col: int
    block_cols: int        # pixels per block horizontally
    block_rows: int


class _Fields:
    def __init__(self, text: str, pos: int = 0):
        self.t, self.pos = text, pos

    def take(self, n: int) -> str:
        v = self.t[self.pos:self.pos + n]
        self.pos += n
        return v

    def int(self, n: int) -> int:
        return int(self.take(n))


def _image_subheader(text: str) -> dict:
    f = _Fields(text)
    if f.take(2) != "IM":
        raise SensorError("not a NITF image subheader")
    f.take(10 + 14 + 17 + 80 + 1 + 166 + 1 + 42)        # IID1 IDATIM TGTID IID2 ISCLAS security ENCRYP ISORCE
    out = {"rows": f.int(8), "cols": f.int(8), "pvtype": f.take(3).strip(), "irep": f.take(8).strip()}
    f.take(8)                                           # ICAT
    out["abpp"] = f.int(2)
    f.take(1)                                           # PJUST
    if f.take(1) != " ":                                # ICORDS -> IGEOLO
        f.take(60)
    for _ in range(f.int(1)):                           # NICOM
        f.take(80)
    out["ic"] = f.take(2)
    if out["ic"] not in ("NC", "NM"):
        f.take(4)
    nbands = f.int(1) or f.int(5)
    out["nbands"] = nbands
    for _ in range(nbands):
        f.take(2 + 6 + 1 + 3)                           # IREPBAND ISUBCAT IFC IMFLT
        nluts = f.int(1)
        if nluts:
            nelut = f.int(5)
            f.take(nluts * nelut)
    f.take(1)                                           # ISYNC
    out["imode"] = f.take(1)
    out["nbpr"], out["nbpc"], out["nppbh"], out["nppbv"] = f.int(4), f.int(4), f.int(4), f.int(4)
    out["nbpp"] = f.int(2)
    f.take(3 + 3)                                       # IDLVL IALVL
    iloc = f.take(10)
    out["iloc_row"], out["iloc_col"] = int(iloc[:5]), int(iloc[5:])
    return out


class Nitf:
    """Segments of a SICD NITF; ``xml`` = the SICD XML, ``read(r0, r1, c0, c1)`` = complex64 (rows, cols)."""

    def __init__(self, src: str | Path):
        self.io = _Source(src)
        head = self.io.read(0, 400).decode("latin-1")
        if not head.startswith("NITF02.10"):
            raise SensorError(f"{src}: not a NITF 2.1 file ({head[:9]!r})")
        hl = int(head[354:360])
        f = _Fields(self.io.read(0, hl).decode("latin-1"), 360)
        images = [(f.int(6), f.int(10)) for _ in range(f.int(3))]
        n_graphics = f.int(3)
        f.pos += n_graphics * 10
        f.int(3)                                            # NUMX (reserved)
        texts = [(f.int(4), f.int(5)) for _ in range(f.int(3))]
        des = [(f.int(4), f.int(9)) for _ in range(f.int(3))]
        off = hl
        self.segments: list[ImageSegment] = []
        row0 = 0
        for lish, li in images:
            sh = _image_subheader(self.io.read(off, lish).decode("latin-1"))
            if sh["ic"] not in ("NC", "NM") or sh["imode"] != "P" or sh["nbands"] != 2:
                raise SensorError(f"{src}: unsupported SICD image (IC {sh['ic']}, IMODE {sh['imode']}, "
                                  f"{sh['nbands']} bands)")
            kind = {("R", 32): ">f4", ("SI", 16): ">i2"}.get((sh["pvtype"], sh["nbpp"]))
            if kind is None:
                raise SensorError(f"{src}: pixel type {sh['pvtype']}/{sh['nbpp']} bits not supported "
                                  "(RE32F_IM32F, RE16I_IM16I)")
            self.segments.append(ImageSegment(off + lish, sh["rows"], sh["cols"], row0, np.dtype(kind),
                                              sh["nbpr"], sh["nbpc"], sh["nppbh"] or sh["cols"],
                                              sh["nppbv"] or sh["rows"]))
            row0 += sh["rows"]
            off += lish + li
        off += sum(a + b for a, b in texts)
        self.xml = ""
        for ldsh, ld in des:
            sub = self.io.read(off, ldsh).decode("latin-1")
            if sub[2:27].strip() in ("XML_DATA_CONTENT", "SICD_XML"):
                text = self.io.read(off + ldsh, ld).decode("utf-8", "replace")
                if "<SICD" in text:
                    self.xml = text[text.index("<SICD"):]
            off += ldsh + ld
        if not self.xml:
            raise SensorError(f"{src}: no SICD XML in the NITF")
        self.rows = row0
        self.cols = self.segments[0].cols

    def _segment_rows(self, seg: ImageSegment, r0: int, r1: int, c0: int, c1: int,
                      workers: int) -> np.ndarray:
        """Rows r0..r1 (segment coordinates), columns c0..c1 of one segment -> (rows, cols, 2) band values."""
        px = 2 * seg.dtype.itemsize
        bw, bh = seg.block_cols, seg.block_rows
        block_bytes = bw * bh * px
        out = np.empty((r1 - r0, c1 - c0, 2), seg.dtype.newbyteorder("="))

        def one_row(r: int) -> None:
            br, rr = divmod(r, bh)
            for bc in range(c0 // bw, (c1 - 1) // bw + 1):
                a, b = max(c0, bc * bw), min(c1, (bc + 1) * bw)
                start = seg.offset + (br * seg.blocks_per_row + bc) * block_bytes + (rr * bw + a - bc * bw) * px
                buf = np.frombuffer(self.io.read(start, (b - a) * px), seg.dtype).reshape(b - a, 2)
                out[r - r0, a - c0:b - c0] = buf

        if self.io.remote:
            with ThreadPoolExecutor(workers) as ex:
                list(ex.map(one_row, range(r0, r1)))
        elif bw == seg.cols and seg.blocks_per_row == 1:     # one block across: a memory map of the rows
            n = seg.rows if seg.blocks_per_col == 1 else seg.blocks_per_col * bh     # blocks are padded
            mm = np.memmap(self.io.src, seg.dtype, "r", seg.offset, (n, seg.cols, 2))
            out[:] = mm[r0:r1, c0:c1]
            del mm
        else:
            for r in range(r0, r1):
                one_row(r)
        return out

    def read(self, r0: int = 0, r1: int | None = None, c0: int = 0, c1: int | None = None, *,
             workers: int = 16, progress: Callable[[int, int], None] | None = None) -> np.ndarray:
        r1 = self.rows if r1 is None else r1
        c1 = self.cols if c1 is None else c1
        parts = []
        for k, seg in enumerate(self.segments):
            a, b = max(r0, seg.row0), min(r1, seg.row0 + seg.rows)
            if a < b:
                parts.append(self._segment_rows(seg, a - seg.row0, b - seg.row0, c0, c1, workers))
            if progress:
                progress(k + 1, len(self.segments))
        iq = np.concatenate(parts, axis=0).astype(np.float32)
        return (iq[..., 0] + 1j * iq[..., 1]).astype(np.complex64)
