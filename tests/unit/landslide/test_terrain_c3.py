"""L3c C3 terrain layers on synthetic surfaces: geomorphons of a peak and a pit, convergence of a cone, slope
length, relative position, roughness."""
import numpy as np

from geoeyes.landslide import terrain as tr


def _cone(n=41, d=30.0, up=True):
    y, x = np.mgrid[0:n, 0:n].astype(float)
    r = np.hypot(y - n // 2, x - n // 2) * d
    return (1000 - 0.3 * r) if up else (500 + 0.3 * r)


def test_geomorphons_peak_and_pit():
    c = 20
    p, m, code = tr.geomorphons(_cone(), 30.0, 150.0)
    assert m[c, c] == 8 and p[c, c] == 0 and code[c, c] == tr.GEOMORPHON_CODES["PK"]
    p, m, code = tr.geomorphons(_cone(up=False), 30.0, 150.0)
    assert p[c, c] == 8 and code[c, c] == tr.GEOMORPHON_CODES["PT"]
    flat = np.full((21, 21), 100.0)
    _, _, code = tr.geomorphons(flat, 30.0, 150.0)
    assert (code == tr.GEOMORPHON_CODES["FL"]).all()


def test_convergence_ridge_and_hollow():
    z = tr.zevenbergen_thorne(_cone(), 30.0)
    ci = tr.convergence_index(z["aspect_sin"], z["aspect_cos"])
    assert ci[20, 20] > 80                                    # the top of a cone: every neighbour flows away
    assert abs(ci[20, 30]) < 20                               # on its flank, nearly parallel flow
    z = tr.zevenbergen_thorne(_cone(up=False), 30.0)
    assert tr.convergence_index(z["aspect_sin"], z["aspect_cos"])[20, 20] < -80    # a pit: all flow in


def test_flow_length_position_roughness():
    y, x = np.mgrid[0:5, 0:30].astype(float)
    h = 1000 - 10 * x                                         # a plane falling east
    zf = tr.fill_depressions(h)
    rec = tr.d8_receivers(zf, 30.0)
    L = tr.flow_length_up(zf, rec, 30.0)
    assert np.isclose(L[2, 20], 600.0)                        # 20 cells from the western divide
    rp = tr.relative_position(h, 30.0, 300.0)
    assert rp[2, 15] == 0.5 and rp[2, 0] == 1.0
    s = tr.zevenbergen_thorne(h, 30.0)
    assert np.allclose(tr.vrm(s["slope_deg"], s["aspect_sin"], s["aspect_cos"], 5)[2, 10:20], 0, atol=1e-9)
