"""Minimal Mapbox Vector Tile decoder for the tests (points only): [(id, x, y, {key: value})]."""
from __future__ import annotations

import struct


def _varint(b: bytes, i: int) -> tuple[int, int]:
    shift = out = 0
    while True:
        c = b[i]
        i += 1
        out |= (c & 0x7F) << shift
        if not c & 0x80:
            return out, i
        shift += 7


def _fields(b: bytes):
    i = 0
    while i < len(b):
        key, i = _varint(b, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 2:
            n, i = _varint(b, i)
            v, i = b[i:i + n], i + n
        elif wt == 5:
            v, i = b[i:i + 4], i + 4
        elif wt == 1:
            v, i = b[i:i + 8], i + 8
        else:
            raise ValueError(f"wire type {wt}")
        yield num, wt, v


def _packed(b: bytes) -> list[int]:
    out, i = [], 0
    while i < len(b):
        v, i = _varint(b, i)
        out.append(v)
    return out


def _unzig(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


def decode(tile: bytes) -> list[tuple[int, int, int, dict]]:
    out = []
    for num, _, layer in _fields(tile):
        if num != 3:
            continue
        keys, values, feats = [], [], []
        for f, wt, v in _fields(layer):
            if f == 3:
                keys.append(v.decode())
            elif f == 4:
                for vf, vwt, vv in _fields(v):
                    values.append(struct.unpack("<f", vv)[0] if vf == 2 else vv)
            elif f == 2:
                feats.append(v)
        for fb in feats:
            fid, tags, geom = None, [], []
            for f, wt, v in _fields(fb):
                if f == 1:
                    fid = v
                elif f == 2:
                    tags = _packed(v)
                elif f == 4:
                    geom = _packed(v)
            assert geom[0] == 9, geom
            props = {keys[tags[k]]: values[tags[k + 1]] for k in range(0, len(tags), 2)}
            out.append((fid, _unzig(geom[1]), _unzig(geom[2]), props))
    return out
