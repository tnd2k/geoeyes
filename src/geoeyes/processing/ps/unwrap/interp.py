"""Edge network for unwrapping (legacy ``_uw_interp``): every grid cell is mapped to its nearest occupied
cell; 4-connected neighbours mapped to different cells define the edges. ``rowix``/``colix`` give, for each
grid step, the 1-based signed edge number (0 = both sides map to the same cell)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree


@dataclass
class UwInterp:
    edgs: np.ndarray      # (n_edge, 3) [id, node_a, node_b], node_a < node_b
    rowix: np.ndarray     # (n_i - 1, n_j) signed edge number between rows
    colix: np.ndarray     # (n_i, n_j - 1) signed edge number between columns
    Z: np.ndarray         # (n_i, n_j) nearest occupied cell

    @property
    def n_edge(self) -> int:
        return self.edgs.shape[0]


def interp(nzix: np.ndarray) -> UwInterp:
    nrow, ncol = nzix.shape
    y, x = np.where(nzix)
    gx, gy = np.meshgrid(np.arange(ncol), np.arange(nrow))
    _, z = cKDTree(np.column_stack([x, y])).query(np.column_stack([gx.ravel(), gy.ravel()]))
    Z = z.reshape(nrow, ncol).astype(np.int32, copy=False)

    zc = Z.ravel(order="F")                                   # column-major as uw_interp.m
    edges = np.column_stack((zc[:-nrow], zc[nrow:]))
    zr = Z.T.ravel(order="F")
    edges = np.vstack((edges, np.column_stack((zr[:-ncol], zr[ncol:]))))
    sign = np.where(edges[:, 0] <= edges[:, 1], 1, -1)
    alledges, j2 = np.unique(np.sort(edges, axis=1), axis=0, return_inverse=True)
    same = alledges[:, 0] == alledges[:, 1]
    alledges[same] = 0
    uniq, j3 = np.unique(alledges, axis=0, return_inverse=True)
    j2, j3 = np.ravel(j2), np.ravel(j3)
    if np.any(same):
        uniq, edge_no = uniq[1:], j3
    else:
        edge_no = j3 + 1
    gidx = edge_no[j2] * sign
    colix = gidx[:nrow * (ncol - 1)].reshape((nrow, ncol - 1), order="F")
    rowix = gidx[nrow * (ncol - 1):].reshape((ncol, nrow - 1), order="F").T
    return UwInterp(edgs=np.column_stack((np.arange(len(uniq)), uniq)), rowix=rowix, colix=colix, Z=Z)
