import numpy as np

from geoeyes.processing.ps.geometry import geolocate


def test_point_above_the_dem_lies_away_from_the_sensor():
    lat, lon, inc, dh = np.array([0.0]), np.array([0.0]), np.array([45.0]), np.array([10.0])
    # flying north, looking right (east): a 10 m high scatterer is 10 m farther east than the DEM-height pixel
    la, lo = geolocate(lat, lon, inc, 0.0, "right", dh)
    assert abs(lo[0] * 111_320.0 - 10.0) < 1e-6 and abs(la[0]) < 1e-12
    la, lo = geolocate(lat, lon, inc, 0.0, "left", dh)                 # looking west
    assert abs(lo[0] * 111_320.0 + 10.0) < 1e-6
    la, lo = geolocate(lat, lon, inc, 180.0, "right", -dh)             # flying south, looking west; below DEM
    assert abs(lo[0] * 111_320.0 - 10.0) < 1e-6                        # -> toward the sensor (east)
